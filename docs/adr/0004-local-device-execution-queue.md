# ADR-004 · 本地设备执行采用 PostgreSQL 事务领取与设备租约

状态：Accepted（架构决策；实现待开始，2026-11-07）

范围：仅覆盖 Runtime 的 local_device 执行入口、任务领取、物理设备独占、收尾和恢复。不改变 cloud_batch、现有 Celery 任务或 Mongo/MinIO 证据格式。

本 ADR 细化 [目标架构](../rebuild/03_ARCHITECTURE.md)，并对 [ADR-001](0001-aihot-openclaw.md) 中“保留 Celery、不引入 pg-boss”的决定作局部说明：**通用后台任务继续使用 Celery/Redis；本地物理设备执行使用 PostgreSQL 事务控制任务领取和设备租约。它不是第二个通用 Broker。**

## 1. 背景

当前 Runtime 已有 RuntimeRequest、PreparedTrial、ExecutionGrant 和消费回执校验，但没有本地物理设备执行器。PreparedTrial 仅表示冻结计划，不代表已执行。

本地设备任务与普通后台任务不同：

- 一项任务在一台物理手机上执行，动作有外部副作用，不能因消息重新投递就假设可以安全重跑。
- 同一台手机必须串行；不同手机可以并行。
- 任务领取和设备占用必须同时成功或同时失败。
- 外部 Agent 与内置助手只是不同驱动，不能拥有两套手机锁、队列或交接流程。
- 租约超时只能证明持有者失去控制权，不能证明旧 Agent 或在途 ADB 操作已经停止。

因此，Broker 的 ACK、Redis 锁或消息 visibility timeout 都不能作为物理设备已安全释放的证明。

## 2. 决策

### 2.1 采用 PostgreSQL 事务队列，不引入新 Broker

使用现有 PostgreSQL 的 evonext schema 保存两类控制记录：

| 表 | MVP 核心字段 | 职责 |
|---|---|---|
| local_trials | trial_id、request_hash、request_payload、status、cancel_requested、execution_receipt、cleanup_receipt、created_at、started_at、finished_at | 冻结的本地执行请求及其控制状态 |
| device_slots | device_id、host_id、state、trial_id、holder_id、lease_id、generation、expires_at、quarantine_reason、last_recovery、updated_at | 每台物理手机当前唯一占用槽 |

request_payload 保存冻结的 plan/context、driver_id 和 allowed_device_ids。大体积轨迹、截图和媒体仍由现有 Evidence/Mongo/MinIO 管理；PG 只存小型回执和证据引用。

不新增 lease_history、attempt_events、outbox、scheduler、通用 job 表或第二套任务数据库。MVP 不为每个动作建立一张事件表。

### 2.2 保留现有 Celery/Redis 的职责

- Celery/Redis 继续承担现有 bulk、完整性校验及其他普通后台任务。
- 本地设备任务直接写入 PostgreSQL，由 LocalExecutionHost 轮询领取。
- 不把设备任务先投递到 Celery，再由 Celery Worker 竞争手机。
- 不引入 pg-boss、Redis device lock 或新的消息队列服务。
- 后续若需要降低轮询延迟，可增加 PostgreSQL LISTEN/NOTIFY；通知只是唤醒提示，数据库状态仍是唯一事实来源。

### 2.3 四个 Protocol，两个持久化表，一个 PG Adapter

保留四个接口边界：

1. LocalTaskQueue：submit、get、claim_next、cancel、finish。
2. DeviceLeaseManager：renew、check、begin_cleanup、quarantine、reconcile。
3. AgentDriver：run、stop_and_wait。
4. LocalExecutionHost：run_device_queue、recover_device。

PostgresLocalExecutionStore 同时实现 LocalTaskQueue 和 DeviceLeaseManager，共享同一个 SQLAlchemy Engine 和事务边界。它们是两个职责接口，不是两个独立服务或两套 Repository。

将原草案中的 finish_and_release 收敛为 LocalTaskQueue.finish：它在一个 PG 事务中保存执行/收尾回执、结束任务，并根据 cleanup 结果把设备置为 READY 或 QUARANTINED。这样不会出现“任务已结束但设备释放失败”或“设备已释放但任务仍显示运行”的中间状态。

## 3. 领取与租约事务

### 3.1 claim_next

一次 claim_next 使用一个短 PostgreSQL 事务完成：

1. 锁定指定 host_id/device_id 的 device_slots 行；仅 READY 设备可领取。
2. 从 QUEUED 且 allowed_device_ids 包含该设备的任务中，按 created_at、trial_id 选择最早可领取项，使用 FOR UPDATE SKIP LOCKED。
3. 将任务改为 RUNNING。
4. 将设备改为 LEASED，generation 单调递增，写入 lease_id、holder_id、trial_id 和 expires_at。
5. 一起提交并返回 ClaimedTask。

任一步失败，事务整体回滚。领取事务不跨越实际 Agent 执行时间，不在模型调用或手机操作期间持有数据库行锁。

SKIP LOCKED 提供并发消费者下的可领取任务选择，不承诺严格全局 FIFO：较早任务被其他事务锁定时，后续任务可能先被领取。MVP 接受“当前可领取任务中的尽力 FIFO”，不实现优先级、老化或复杂公平调度。

submit 使用 trial_id + request_hash 幂等：相同 trial_id、相同内容返回原收据；相同 trial_id、不同内容返回冲突。request_hash 必须覆盖冻结 plan/context、driver_id 和 allowed_device_ids。

### 3.2 Lease 与 fencing

Lease 至少绑定 device_id、trial_id、host_id、holder_id、lease_id、generation、expires_at。

renew/check/begin_cleanup/finish/quarantine/reconcile 均核对当前租约身份；时间判断使用 PostgreSQL 服务端时间，不依赖宿主机时钟。generation 在每次成功领取时递增，旧 generation 不能续租、派发动作、结束任务或释放新租约。

**租约过期绝不自动把设备改成 READY。** 过期、宿主失联、执行状态未知时，设备进入 QUARANTINED。claim_next 只领取 READY 设备。恢复核验通过后，可信宿主携带 expected_generation 调用 reconcile，才可以重新置为 READY。

fencing token 由唯一设备操作网关执行。Android/ADB 本身不会识别数据库 generation，因此驱动不得获得可绕过 LeasedDevice 的原始 ADB/USB 控制入口。若未来引入跨宿主接管，必须先撤销旧宿主的物理控制通道并完成恢复核验；不能仅凭 generation 变化就把手机交给另一宿主。

## 4. 设备与任务状态

设备状态：

~~~text
READY → LEASED → CLEANING → READY
                  │
                  └────────→ QUARANTINED

LEASED / CLEANING --租约过期、断连、状态未知--> QUARANTINED
QUARANTINED --可信宿主 reconcile 通过--> READY
~~~

任务状态：

~~~text
QUEUED → RUNNING → CLEANING → SUCCEEDED / FAILED / CANCELLED
                              └────────→ INTERRUPTED
~~~

cancel_requested 是独立标志，不把运行任务直接改成 CANCELLED。排队任务可以立即取消；运行任务由宿主收到停止请求后执行停止与收尾。任务业务失败不等于设备不可用；设备能否释放只取决于旧执行是否停止、在途动作是否收束以及起态是否通过。

## 5. 统一设备句柄与执行监督

外部 Agent 和内置助手分别实现 AgentDriver，但只能通过宿主交付的 LeasedDevice 操作同一台手机。

LeasedDevice 是受控动作网关，不是原始 ADB client 的别名：

- 每台设备只有一个串行派发通道；不同设备的通道可以并行。
- 每次派发在同一 per-device dispatch lock 内完成租约校验、动作发送和该动作的收束等待；不把原始 ADB 通道交给驱动。
- begin_cleanup 先取得同一把 dispatch lock，等待当前动作结束，再提交 CLEANING 并关闭 Agent action gate；不在 PG 事务中等待 ADB。宿主保留独立的停止/清理能力，驱动拿不到该能力。
- CLEANING 后禁止 Agent 发起新动作；只有宿主的停止、清理和恢复逻辑可继续。
- 动作预算和截止时间由宿主/网关执行，不能只依赖驱动自觉。
- 不允许驱动绕过句柄直接操作 ADB、shell、USB 或另一个自动化服务。

AgentDriver.run 不得占住负责续租、取消和停止的宿主监督循环。MVP 使用最简单的独立执行单元承载 run；宿主在外部监督续租与取消。如果 stop_and_wait 在截止时间内不能确认旧执行和在途动作已经收束，设备进入 QUARANTINED。不得因为线程超时就推断手机已停止。

MVP 以一个 LocalExecutionHost 进程管理其配置的多台手机，每台手机一个 run_device_queue。手机 A/B 可并行，同一手机始终串行。host_id 和设备归属先由本机配置确定，不实现跨宿主自动调度或 HA 接管。

## 6. 收尾、回执与恢复

正常顺序：

~~~text
claim_next
  → AgentDriver.run
  → begin_cleanup（先禁止 Agent 新动作）
  → stop_and_wait
  → 保存执行证据 / 收尾
  → 验证设备起态
  → LocalTaskQueue.finish（原子结束任务并释放或隔离设备）
  → claim_next
~~~

宿主在运行和 CLEANING 期间持续续租。finish 只有在租约仍匹配当前 generation 时才能提交，并且对同一租约及相同回执幂等。迟到的旧 finish 不能清除新租约。

- cleanup 全部 PASS：根据 ExecutionReceipt 结束任务；设备转 READY。任务可以是 SUCCEEDED、FAILED 或 CANCELLED，业务结果不决定设备能否释放。
- cleanup 任一项 FAIL/UNKNOWN：任务记为 INTERRUPTED，设备转 QUARANTINED，不领取下一项。
- 租约丢失、断连、宿主崩溃或旧执行无法确认停止：先隔离，不能自动重跑或释放。
- reconcile 必须核验物理身份、旧执行/旧通道已停止、在途动作已收束、证据引用与设备起态；任何 UNKNOWN 都不能恢复 READY。

证据字节继续通过现有 Evidence/Mongo/MinIO 路径保存，PG 事务只保存回执和引用，不跨 Mongo/MinIO/PG 做分布式事务。证据上传不确定不能被报告为成功；但设备是否可释放仍由物理清理结果决定。若证据未知而清理已 PASS，可以结束为 INTERRUPTED/UNKNOWN 并释放安全设备，不能为了等证据上传而无限占住手机。

## 7. 明确不做

MVP 不做：pg-boss、第二 Broker、Celery device queue、Redis 锁、通用 Scheduler/DAG、严格 FIFO、优先级/公平性系统、跨宿主 HA、动态设备发现、设备农场管理 UI、cloud_batch 调度、执行自动重试、自动恢复手机状态、模型调用或训练平台。

MVP 不实现真实 Agent 驱动的占位成功版本。当前 EvoNext main 有 RuntimeRequest/PreparedTrial 合同，但没有可直接复用的真实本地手机驱动；本 ADR 先固定接入边界，真实外部 Agent/内置助手适配需由对应执行器提供方单独接入和验收。

## 8. 验收底线

- 两个宿主线程/进程竞争同一设备时，最多一个获得租约。
- 两台设备可以同时执行不同任务；同一任务最多被一个设备领取。
- 旧 generation、过期 lease、错误 holder 无法续租、派发或结束新任务。
- 运行中取消能由宿主监督循环处理；停止未确认时必须隔离。
- CLEANING 阶段禁止 Agent 新动作；在途动作未收束不得释放。
- 收尾 PASS 才能 READY；FAIL/UNKNOWN 必须 QUARANTINED。
- 宿主崩溃或租约过期后不能自动领取；reconcile 必须核对 expected_generation。
- submit、finish 的响应丢失后重试幂等；不同内容复用 trial_id 必须冲突。
- 上述并发/行锁性质必须用隔离真实 PostgreSQL 多进程测试证明，不能只用内存 Fake 或 SQLite 代替。

本 ADR 只批准设计和实现范围，不代表本地手机驱动、真实设备恢复或生产运行已经验收。