# 05 · 空目录重写实施协议、迁移与退出计划

> 修订：2026-11-06 / 0.2。保留原全量需求与验收编号；这是目标合同，不是已实现清单。当前交付见 [实施状态](../ACCEPTANCE.md)，目录与存储以 [03](03_ARCHITECTURE.md) 为准。

**实施决策**：接受最新明确要求——可以在一个全新的目录编写 EvoNext，不沿袭旧 Flywheel 的内部类、目录、路由写法或旧服务依赖。**不同意“完全不看任何旧系统证据”**：实现者与旧代码隔离，审计者必须先做黑盒行为合同及数据迁移盘点。当前已授权在 EvoNext 新仓库搭建并调整框架；这不授予旧库迁移、生产数据修改、付费模型、设备执行或部署权限。

## 1. 独立实现为何不等于盲写

Clean-room 的对象是**旧实现方式**，不是业务真实需求。若无真实合同，Codex 很容易发明一个漂亮的 Task/Evaluation/Dataset 原型，但漏掉 fixed version、Case reviewer、外部 backflow、媒体、训练 manifest、权限和运维。最佳组织是：

```text
旧仓库/旧服务（只读）
     │
     ▼
独立审计者（可读旧代码/行为/用户流程）
     │ 输出：需求合同、黑盒 fixtures、API 现状、来源/权限矩阵、故障证据
     ▼
经负责人审核的 clean-room spec/fixtures（无旧内部实现代码）
     │
     ▼
新实现 Agent（只读新规格/官方依赖文档）
     │ 输出：新源代码 + 新测试 + 迁移工具
     ▼
独立验收者（对照旧/新真实外部行为、契约、新目标）
```

不能让实现者自己宣称“旧代码不好，所以我不测试旧行为”，也不要求旧系统所有偶然错误都永久兼容。**目标行为**和**可接受的有意 breaking change**由负责人/审计者确认。

## 2. 三个工作空间及信息隔离

**A · Audit workspace（旧系统只读）**：查现有入口、实际消费方、版本/Case/导出、数据分布和可执行回归；固定 baseline commit；输出经脱敏的 request/response fixtures、数据字典、历史边界样例、消费者依赖和迁移脚本测试数据。不得拷贝旧服务内部源代码给新实现。若受版权/敏感数据约束，只给规范化的 contract 和 synthetic fixtures。

**B · Greenfield workspace（新实现）**：本仓库 `src/evonext/`，实现者使用本规格包 `README/01–08/examples`、官方库文档与审计方批准的稳定 schema/测试文件，且明确禁止导入 `src/flywheel`、`src/evaluation`、旧 ORM、旧 Task/Case Service 类、旧 migrations、旧 tests 的内部模块。允许对外 API 的独立契约测试，并允许复用成熟第三方技术组件/协议，但不能因复用而偷带历史写逻辑。

**C · Integration workspace（联通验证）**：只有在新域端到端可演示后，把双方请求/数据经公开 adapter 接通，在隔离环境/影子流量做一致性和权限对照。可以读取旧平台帮助迁移，但不得倒灌旧内部类或强行设计一套平行写系统。真实接入有独立 MR/PR、审阅与可回退记录。

独立 EvoNext 仓库及 `src/evonext/` 包已经确定。上述 workspace 是责任隔离，不要求另建三个长期工程或三套数据权威；旧生产系统仍保持不变。

## 3. M0：冻结现状，形成“功能去向/活跃接口”台账

在实现前，审计者逐项记录：

| 核对项 | 最小输出 | 验收方式 |
|---|---|---|
| 使用中的用户流程 | 搜索→Task/Step→review→Case；导入/回流→Eval；Dataset→Publisher 等分解为动作 | 有真实/脱敏连续操作录像或可执行请求 |
| 现役 HTTP/CLI/Worker | 调用者、版本/参数、权限、是否真被使用、平均/峰值、错误语义 | API 日志/真实消费者确认，不仅 grep |
| 数据规模与类别 | raw/latest/history、任务家族、Step 规模/图片、Case/review、Eval/Job、导出与孤儿 refs | 读取计数、hash sampling、schema exception report |
| 权限与敏感性 | user/service/admin、source/tenant、历史 data scopes、媒体签名、人工审阅归属 | 未授权读/写/导出负测 |
| 历史状态与瑕疵 | Known defects、退役入口、真实用户仍依赖的行为 | 标注 `preserve / intentionally_change / retire / unresolved` |
| 黑盒对照样本 | 正常、失败、unknown、长轨迹、重复、部分写、旧版本、冲突、缺图 | 固定输入、预期输出/失败码、证据来源和 checksum |

如果本地那份“新文件夹文档”后来可访问，应先与 `00/01/02/06` 逐条 diff，归入 `adopt / adapt / reject / unresolved`，不要直接用其目录替换本包。由不同审计者交叉检查是否漏真实业务能力，特别是分布、训练和生产账号/媒体。

## 4. ADR-001：更改原迁移决定

**过去记载的方案**：`docs/contracts/agent-engineering-migration.md`（2026-10）明确在现有 `src/flywheel/` 渐进替换，退役独立 clean-room 工程。**最新用户选择**：要求完整新功能文档、空目录重写、不要借鉴旧内部代码；本包承接已授权的新仓库实现；仅修改 EvoNext，不以此授权切换旧生产系统。

**新决定**：重写时实现者不导入或复制旧 Flywheel 内部模块；新旧系统可通过数据和公开 API 并存一段时间；旧业务的强约束由审计方以规范和黑盒测试提供。**保留**旧方案中依然正确的要求：单一写 owner、版本与审计、权限/Scope、数据核对、真实消费者、按切片验收、切换/回退，以及不自动执行生产外部动作。

**不保证**：一次性“大爆炸”切流一定更快；重写后的代码量一定更少；不看旧代码就可以恢复未写明的旧 API 语义。复杂度目标必须在 M2 之后实测。

## 5. M1–M4：分期交付与退出 Gate

| 阶段 | 核心产物 | 验收/停止条件 |
|---|---|---|
| **M0 · 规格和基线** | 当前 API/消费者/数据去向清单、hash-pinned fixtures、旧系统行为金样例、现有存储隔离接入验证 | 需求覆盖签署；P0 合同无明显自相矛盾；独立审计不将旧错误当新要求 |
| **M1 · 可信资产纵向切片** | 单/批 ingest → 固定 Task/Step/media → 搜索 → Review/Case → Outcome Eval → Snapshot/Manifest；API/React/Worker 端到端 | 合成和允许的真实脱敏源可连续重开，重启/冲突/权限/长轨迹验收通过；技术质量与模型语义分开报告 |
| **M2 · 自进化证明切片** | reviewed Case → diagnosis/route → simple candidate or no-op → authorized new trial → independent grader → paired readout → guard or stop | 使用一组经授权真实来源，至少一项可否证实验完成；无增益/回退也算完成；不可将旧轨迹静态续接当 trial |
| **M3 · 活跃消费者切换** | ORM/Query/Runtime/Workshop/Trainer/Case 等确认仍使用路径的 adapter、历史只读/迁移、增量对账 | 每个确认活跃者已能调用新路由/读取新权威；兼容去向清单无无主读写方 |
| **M4 · 生产签署** | staging 迁移演练、影子/小流量校验、最终 watermark、单写切换、回退/演练、运维手册与责任人 | 实际数据/媒体/ACL、作业状态、成本/延迟、故障恢复、数据回滚和监控均有签署证据，才放旧系统退役 |

并行实施允许，但**切换门不能借用早期阶段的测试通过**。若 M0 就发现核心历史合同无法获得，则先产出风险列表/无法兼容项并缩小上线范围，不能虚构通过。

## 6. 数据迁移：避免“复制完库，含义丢了”

### 6.1 核对的单元

必须逐类映射和对账：

- Task raw / latest / history、revision parent、source key、task_id 的字符串化、step count、源 step order 与 ID、有效改令、tool call 的真实来源。
- 图片/媒体 object key、内容哈希/大小/格式、step 与 frame relation、缺失/坏图，旧 NAS 或路径 fallback 不自动变成永久引用。
- 人工 Review/QA、annotator/reviewer 身份、审阅/字段 patch 历史、Case locator/revision/membership/failure facet。
- 机器 Evaluation 的原生标签、模型/政策身份、旧不完整记录、运行/技术失败与业务结果，不能补造缺失 provenance。
- 导入/Query/ORM Job/Attempt/回填状态，避免旧系统在切换后继续对旧数据新增失踪任务。
- Dataset、导出 manifest/成员、training/benchmark/contamination、训练/发布使用回执；历史只读不声称完整新格式。

### 6.2 推荐四步流程

1. **Snapshot/Read-only extract**：固定旧系统快照时间与内容水位，输出每类对象数量、大小、hash、orphan 数和选择/排除规则，保留可信原始备份。
2. **Transform into staging**：独立 ETL 到隔离区，标准化新身份/来源 mapping；不猜 human review、未给的 trial、未知结果和未验证图片，标 `legacy_unverified`，留下转换错误报告。
3. **Validate then publish**：原始/新源样本、版本图/Case 引用、hash 与源 Scope 的全量计数和分层抽样核对；通过后将 staging 对象注册到新 canonical，未通过保留隔离，不让新版本假装真源。
4. **Incremental catch-up + cutover**：用单调 source watermark、source revision+hash 去重同步增量；切换前冻结/阻断旧写入口或转发到新唯一 owner，确认没有双写竞争和未结束 consumer；切换后监控及回退窗口。

对 Mongo 与 MinIO/PG 跨库不做虚假的分布式原子承诺：如果媒体已上传而 DB 插入失败，保留可回收或可核对的对象登记；如果 DB 状态已 accepted 而媒体不存在，暴露 needs_reconcile、阻断下游。不得悄悄把“图片占位”视为成功入库。

### 6.3 增量窗口与对账指标

每类对象须有 `source_count / imported_count / skipped(reason) / failed / quarantined / duplicate / orphan / latest_pointer_mismatch` 的计数，支持按 source/app/月份/schema/review 维度钻取。**总量相同不等于语义相同**：还需比较若干固定 Task/Step/Case、同一次重试结果、媒体 checksum、审核权限与并发冲突行为。每次迁移留输入 watermark、工具版本、manifest hash、校验报告与责任人。

## 7. 消费者切换：一次一个写入权威

不采用长期无治理的“旧 API 写旧库、新 API 写新库、双向同步 latest”模式。可使用：

- **Shadow read / compare**：新 API 只读返回候选结果，对同一 fixed source binding 比对，不写回旧系统。
- **Single-owner write**：一个业务对象在任一时刻只由旧 owner 或新 owner 接受正式写；另一个若保留接口，必须明确代理/只读/拒绝。
- **Conditional dual-produced projection**：若 legacy UI 还必须展示新评估结果，仅允许由新 Record 派生一个可重建 legacy summary，并有幂等/失败补扫；不能两边独立承认结果为权威。
- **Consumer drain**：执行中消息、旧 Worker 处理、历史重投与回执失联需要按 request ID/hash 核对并排空或安全重定向；同源旧结果迟到不能覆盖新结果。

完全移除某个旧入口前，检查其流量、团队 owner、兼容期限、数据消费者、回滚可行性；退役后的读取/导出历史可保留最窄只读 adapter，不必永久保留旧平台。

## 8. 回滚方案是切换方案的一部分

- 回滚旧页面/旧路由不等于可回滚新数据；新系统在切换后形成的 TaskRevision/Case/Review/records 可能无法被旧 schema 无损表达。
- 如要具备真实**写入回滚**，切换前证明反向转换对所有允许的新写类型可无损还原，或明确在回滚窗口暂停这些新写类型；否则回滚动作只能回滚读/路由并保留新系统的唯一写 owner。
- 在切换前保留旧系统只读、数据备份、增量对账与独立应急查询端；任何恢复不得把较新的人工审核从旧备份静默覆盖。
- 一旦发生未知双写冲突、source content hash mismatch、Case ACL 失效、缺媒体大面积增加、认证绕过或不可恢复导入，就停止扩大流量，依据预注册计划 HOLD/ROLLBACK。

## 9. 独立验收与职责分离

| 角色 | 能做 | 不能代替 |
|---|---|---|
| 业务/规格负责人 | 决定范围、优先级、有意改动、实验预算、上线许可 | 不以“代码漂亮”代替业务签署 |
| 旧系统审计者 | 抽取稳定合同、来源/权限/消费者/迁移样例、判断已退役范围 | 不把旧实现直接复制为新内部架构 |
| Greenfield 实现者 | 依据冻结 PRD/Contract/Acceptance 独立写源码、工程测试、页面 | 不能自称独立 oracle 或未经授权部署/调用设备 |
| 独立测试者/Reviewer | 使用盲测 fixtures、故障注入、真实匿名/授权试验、回归与全链路报告 | 不把合成标签当真实 Gold |
| 系统 owner/运维 | 审核数据水位、队列/权限、运行日志/成本、单写切换和回退 | 不在测试不足时默认发布 |

**原则**：一次完整 clean-room 方案的成功，必须可以由另一个不知道旧内部代码的人按黑盒合同验证，并由知道实际历史数据的人确认不会丢业务事实。

## 10. 各切片实施与切换清单（具体完成范围见实施状态）

- 冻结用户最新的 Greenfield ADR 与实施权限；没有获得生产写入或付费模型授权时从纯 fixture/local 开始。
- 读取 `01–08`，先做 `M0` 消费者与数据基线；发现新旧冲突列出 decision log，而不是擅自按旧代码实现。
- 选一条 25 步、有错/缺图/Case 的脱敏任务与 2000 步长任务作第一批测试，固定 source/version/hash。
- 验证保留的 Mongo/MinIO/PG 在隔离命名空间中的读写、故障和可观测指标；不再把替换 Mongo 作为开工前置。
- 先交付 J1→J3→J6 的纵向闭环，再扩展 Skill/Recovery/训练；每条路径验收后只做必要横切抽象。
- 运行独立测试、输出真实通过/失败/未测矩阵，维护 consumer cutover / rollback 表。仅当本文件的 M4 有可信证据才讨论旧系统删除。
