# Local Device Queue MVP · Codex 实施任务

状态：Ready for implementation（2026-11-07）。本工作包只实现本地设备执行控制面；不代表真实手机驱动已经接入。

关联决策：[ADR-004](../adr/0004-local-device-execution-queue.md)。遵循 [AGENTS.md](../../AGENTS.md)、[03 架构](../rebuild/03_ARCHITECTURE.md)、[08 Runtime 合同](../rebuild/08_SKILLS_RUNTIME_AND_PIPELINE.md)、[ROADMAP](../ROADMAP.md) 和 [当前验收状态](../ACCEPTANCE.md)。

## 1. 目标与停止条件

在 EvoNext 内建立最小可用的本地手机任务领取与交接链：

- API/CLI 可以提交一个冻结的本地 TrialRequest。
- 一个 LocalExecutionHost 管理多台已配置手机，每台手机有独立串行队列；不同手机并行。
- 领取任务时同时取得设备租约；两者由一个 PostgreSQL 事务提交。
- 外部 Agent 和内置助手通过同一个 LeasedDevice 操作入口。
- 执行、取消、停止、清理、证据引用、起态验证、完成/隔离具有可恢复状态。
- 宿主崩溃、租约过期或设备断连不会让手机自动重新可领取。

完成以上控制面、API/CLI 和测试后停止扩展。真实设备驱动接入、跨宿主 HA、优先级调度不属于本工作包。

## 2. 现有代码事实与约束

Codex 开始前必须重新读取当前分支，不以本文件代替代码核对：

1. RuntimeRequest 和 ExecutionGrant 位于 src/evonext/contracts/runtime.py。
2. PreparedTrial、prepare_trial、verify_usage 位于 src/evonext/runtime/context.py。PreparedTrial 的 plan_json/context_json 已冻结；其 id/context_hash 是计划与上下文身份。prepared_not_executed 不能被改写为已执行。
3. Runtime 当前没有真实设备执行实现。不要将 prepare-trial 命令或 verify_usage 当成执行器。
4. PostgreSQL 的现有 schema 是 evonext；当前迁移为 0001_receipts、0002_model_calls。新增迁移使用 0003，不修改旧集合或旧表。
5. src/evonext/operations/ledger.py 已有 SQLAlchemy Engine/事务使用方式。新 Store 必须复用每进程一个 Engine 的原则，不得每次 claim/renew 都新建 Engine。
6. src/evonext/app/worker.py 与 compose.yaml 中 Celery/Redis 是现有 bulk/校验任务链路。本工作包不改造或替换它。
7. tests/test_architecture.py 明确限制 contracts、app/api 和 Runtime 的依赖方向。新增本地执行 API 应放独立 app router/adapter，不能让 evidence API 直接导入设备执行实现。
8. Mongo 保存轨迹事实，MinIO 保存媒体字节，PG 只保存本地执行控制记录和小型回执/引用。禁止跨库分布式事务。

若上述事实在当前分支已变化，先对齐实际代码并在交付中说明；不要覆盖或回退其他工作。

## 3. MVP 设计边界

### 3.1 请求与冻结计划

新增 TrialRequest（可按项目命名约定使用 LocalTrialRequest），它只包装已有 PreparedTrial，不重新定义一套 Runtime 计划：

- frozen plan：PreparedTrial.plan_json 解码后的原样 JSON 对象。
- frozen context：PreparedTrial.context_json 解码后的原样 JSON 对象。
- driver_id：稳定的驱动标识。
- allowed_device_ids：非空、去重的物理设备 ID 列表。
- request_hash：覆盖 plan、context、driver_id、allowed_device_ids 的规范化内容 hash。

验证要求：
- plan 必须来自已完成 prepare_trial 的结果，schema_version/status 合法，status 必须为 prepared_not_executed。
- plan 中的 target.kind 必须是 local_device；cloud_batch 不得进入本地队列。
- trial_id、plan_id、context_hash 从冻结计划中读取并核对，不由客户端另行覆盖。
- 如果 target.resource_id 被当前合同定义为具体设备，allowed_device_ids 必须包含该设备；不得静默改写原 plan 的 target。
- 同 trial_id + 同 request_hash 幂等；同 trial_id + 不同 request_hash 返回明确冲突。
- 不在 claim 时重新生成 plan/context，也不在执行过程中读取 Skill latest。

### 3.2 PostgreSQL 持久化

只新增两张表，位于 evonext schema：

**local_trials**
- trial_id：主键。
- request_hash：固定请求身份。
- request_payload：冻结 plan/context、driver_id、allowed_device_ids 的 JSONB。
- status：QUEUED/RUNNING/CLEANING/SUCCEEDED/FAILED/CANCELLED/INTERRUPTED。
- cancel_requested：独立布尔值。
- execution_receipt、cleanup_receipt：小型 JSONB 回执，包含证据引用，不存截图/轨迹大字节。
- created_at、started_at、finished_at、updated_at。

**device_slots**
- device_id：物理设备主键。
- host_id：配置归属的本地宿主。
- state：READY/LEASED/CLEANING/QUARANTINED。
- trial_id、holder_id、lease_id。
- generation：单调递增 BIGINT。
- expires_at、quarantine_reason、last_recovery、updated_at。

不新增 lease_history、job_attempts、worker_heartbeat、outbox、priority、queue_name 或 scheduler 表。device_slots 在宿主启动时可 INSERT ON CONFLICT DO NOTHING 初始化；绝不能把已有 LEASED/CLEANING/QUARANTINED 状态重置为 READY。

### 3.3 Store 与事务

实现一个 PostgresLocalExecutionStore，同时实现 LocalTaskQueue 和 DeviceLeaseManager；不要分别实现两套重复 SQL 的 Repository。

claim_next：
1. 事务内锁定指定 host/device 的 READY device_slots 行。
2. 选取 QUEUED 且 allowed_device_ids 命中当前设备的最早任务，FOR UPDATE SKIP LOCKED。
3. 同一事务更新任务 RUNNING、设备 LEASED、generation + 1、lease_id/holder_id/expires_at。
4. 无任务时不改变设备状态，返回 None。

finish：
1. 使用与 claim 一致的锁顺序（先 device slot，后 trial），核对 lease_id、generation、holder_id、trial_id 和有效期。
2. 幂等保存 ExecutionReceipt/CleanupReceipt 并结束任务。
3. cleanup 全 PASS 时设备转 READY；否则设备转 QUARANTINED，任务转 INTERRUPTED。
4. 旧 generation 或迟到回执不得清除、覆盖新租约。

其他方法：
- submit：幂等插入；冲突时返回明确错误。
- get：返回任务状态和 cancel_requested。
- cancel：QUEUED 直接 CANCELLED；RUNNING/CLEANING 只设置 cancel_requested，由 Host 执行停止。
- renew/check：核对完整 Lease 身份和 PostgreSQL 服务端时间。
- begin_cleanup：LEASED → CLEANING，阻止 Agent 新动作。
- quarantine：超期、断连、stop 未确认或执行状态未知时隔离；不自动释放。
- reconcile：expected_generation 必须匹配；只有 RecoveryReceipt 全部 PASS 才能清除租约并恢复 READY。

事务只覆盖 PG 状态更新，不得跨 Agent 调用、ADB、Mongo 或 MinIO 持锁。使用现有 SQLAlchemy 依赖和 Alembic；不新增 Redis/pg-boss 依赖。

### 3.4 Host、LeasedDevice 与 Driver

保留四个 Protocol：LocalTaskQueue、DeviceLeaseManager、AgentDriver、LocalExecutionHost。

- 一个 Host 进程管理其配置的设备；每台手机一个 run_device_queue。设备 A/B 可并行，同设备不可并行。
- LeasedDevice 是唯一设备操作入口。AgentDriver 不能取得原始 ADB client、shell、USB handle 或绕过网关的自动化连接。
- 每次动作派发在设备串行通道内校验当前 Lease/generation；动作预算和截止时间由 Host/网关执行。
- Host 必须在独立监督路径中完成续租和取消检查，不能同步阻塞在 AgentDriver.run 上。run 在独立执行单元中运行；stop_and_wait 由监督路径触发。
- 收尾顺序必须是 begin_cleanup（先禁止 Agent 新动作）→ stop_and_wait → 收束在途动作 → 保存证据引用/清理 → 验证起态 → finish。
- CLEANING 期间持续续租。租约丢失后不再派发普通动作；旧执行无法确认停止时 QUARANTINED。
- 任务业务失败但设备 cleanup PASS，可以释放设备；cleanup FAIL/UNKNOWN 必须隔离。
- 不对超时/未知动作自动重放。手机动作可能已产生外部副作用，不能按普通任务消息重试。

当前 main 没有可直接复用的真实本地手机驱动。只定义 AgentDriver Protocol 和显式注入/注册边界；测试可使用 FakeDriver/FakeDeviceTransport，但生产路径不能有返回成功的空实现。外部 Agent 和内置助手的具体接入必须使用其真实执行器并单独验收，不得凭空编造命令或接口。

### 3.5 轮询、宿主和 API

MVP 使用简单轮询，不引入消息通知组件：
- 每设备空闲轮询间隔可配置，初始默认约 1 秒。
- 租约 TTL/续租间隔可配置，初始建议 60 秒/20 秒；Host 在 RUNNING 与 CLEANING 阶段持续续租。
- 所有有效期判断使用 PG 时间。
- 一个 Host 进程通过多设备执行循环实现并行，不新增 Celery worker queue 或 Docker Compose 服务。物理设备连接留在能访问设备的本机进程。
- 设备列表由本机配置提供；启动初始化只插入缺失 slot，不自动重置已有状态。
- 后续可以用 LISTEN/NOTIFY 唤醒轮询，但 claim_next 事务不变。

提供最小受认证 API：
- POST /api/v1/local-trials：提交 TrialRequest，只写队列，不等待执行。
- GET /api/v1/local-trials/{trial_id}：读取状态。
- POST /api/v1/local-trials/{trial_id}/cancel：请求取消。

提供 CLI Host 入口，例如 evonext local-worker --devices A,B。CLI 只负责启动本机 Host，不绕过 Store 直接执行。不要为了 MVP 加管理 UI。

## 4. 建议代码落点

按当前源码核对后可微调，但保持小范围：

~~~text
src/evonext/runtime/local_execution/
  __init__.py
  contracts.py       # TrialRequest、Lease、Receipts、四个 Protocol
  postgres.py        # PostgresLocalExecutionStore；唯一 PG 实现
  device.py          # LeasedDevice 与串行派发/租约校验
  host.py            # LocalExecutionHost、run_device_queue、recover_device

migrations/versions/0003_local_device_execution.py

src/evonext/app/local_execution_api.py   # 独立 Router/adapter
src/evonext/app/cli.py                   # local-worker 命令入口
src/evonext/config.py                   # 最小必要的 host/device/poll/lease 配置

tests/test_local_execution.py
tests/test_local_execution_postgres.py  # 真实隔离 PostgreSQL，多进程并发
~~~

不要提前建立 devices、scheduler、drivers/plugin marketplace、queue adapters 等空目录。若某个模块不足以独立承载职责，优先合并文件，而不是增加层级。

## 5. 必须覆盖的测试

| ID | 测试场景 | 通过条件 |
|---|---|---|
| LE-01 | submit 幂等 | 同 ID/同 hash 返回原收据；同 ID/不同 hash 冲突 |
| LE-02 | 同一设备并发领取 | 多进程竞争时最多一个任务获得该设备租约 |
| LE-03 | 两设备并行 | A/B 可同时领取不同任务；一个 trial 不会被领取两次 |
| LE-04 | 设备 allowlist | 不允许的设备不能领取该任务 |
| LE-05 | Lease fencing | 旧 generation、错 holder、过期 lease 无法 renew/check/finish |
| LE-06 | cancel | 排队任务直接取消；运行任务只置 cancel_requested，Host 负责停止 |
| LE-07 | CLEANING gate | begin_cleanup 后 Agent 新动作被拒绝；在途动作未收束不能释放 |
| LE-08 | cleanup 异常 | PASS 才 READY；FAIL/UNKNOWN 必须 QUARANTINED |
| LE-09 | 断连/宿主重启 | 过期不自动 READY；未 reconcile 不能领取 |
| LE-10 | reconcile | expected_generation 不匹配或物理身份/旧通道/起态 UNKNOWN 时拒绝恢复 |
| LE-11 | finish 幂等 | 完成响应丢失后重复提交返回原状态，不影响下一代租约 |
| LE-12 | 证据边界 | PG 只存小型回执/引用；Evidence 字节仍走 Mongo/MinIO，未知不冒充成功 |
| LE-13 | PG 竞争语义 | 使用隔离真实 PostgreSQL、多进程验证行锁；SQLite/内存 Fake 不计入此项 |

FakeDriver 仅用于确定性测试，不能代替 PostgreSQL 并发测试，也不能证明物理设备已停止。真实设备 smoke test 需要显式授权、隔离手机和实际 Driver adapter；不放进普通 CI。

## 6. 交付顺序

1. **Contracts + migration + Store**：定义冻结请求与回执，创建 0003 迁移，实现 submit/get/cancel/claim/renew/check/finish/quarantine/reconcile；先让 LE-01 至 LE-05、LE-08、LE-11、LE-13 通过。
2. **LeasedDevice + Host**：实现串行动作 gate、续租/取消监督、收尾状态机和恢复核验；覆盖 LE-06 至 LE-10。
3. **API + CLI**：接入受认证提交/查询/取消和本机 Host 启动；保持 evidence API 不直接依赖执行实现；补齐 LE-12。
4. **回归与交付**：运行 pytest、compileall、Ruff；前端未改则无需为此引入前端改动，但仍报告现有 CI 状态。真实 PG 测试必须说明 DSN/隔离 schema/进程数；未配置时明确标为未验，不得用 mock 冒充通过。

每阶段结束检查 diff，删除无用抽象。不要一次顺手重构 Ledger、Celery、Evidence、Runtime 全部模块。

## 7. 明确禁止与最终交付

- 不引入 pg-boss、Redis 锁、第二 Broker、第二 Scheduler 或通用工作流框架。
- 不把 Celery ACK、任务状态或 lease timeout 当作物理手机已停止的证据。
- 不在数据库事务中执行 Agent、模型、ADB、Mongo 或 MinIO 操作。
- 不把租约过期自动改为 READY；不自动重放不确定的手机动作。
- 不让 Driver 绕过 LeasedDevice；不把原始 ADB 句柄交给外部 Agent。
- 不创建假成功的生产 Driver；不在普通测试、CI 或未授权环境中操作真实手机。
- 不修改 OpenCUA 原始 JSON、旧平台集合、历史轨迹或旧 EvoLoop。
- 不因完成基础设施测试就宣称真实 Agent、设备恢复、独立任务成功率或生产可用性已验收。

交付 PR 必须包含：改动范围、迁移/回滚策略、API/CLI 示例、并发测试命令与环境、LE-01..13 逐项证据、真实设备适配缺口、未验项目和明确的 HOLD/ACCEPTED 结论。达到本工作包验收后停止扩展，等待真实 Driver 接入的单独授权。