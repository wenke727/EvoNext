# 07 · 交给 Codex / Claude 的独立重写实施任务书

> 修订：2026-11-06 / 0.2。保留原全量需求与验收编号；这是目标合同，不是已实现清单。当前交付见 [实施状态](../ACCEPTANCE.md)，目录与存储以 [03](03_ARCHITECTURE.md) 为准。

> **当前已授权在独立 EvoNext 仓库实施框架、文档和本地合同测试。** 在现有新仓库上继续开发，不重复初始化另一套 clean-room 工程。没有额外环境与副作用授权时，不修改旧仓库/生产数据，不调用付费模型、不执行真机、训练或部署。完整目标不等于本轮全部实施。

## 任务目标

你要在独立新仓库实现 **EvoNext**：可信 GUI Agent 轨迹资产、人工/机器判断与 Case 治理、冻结数据集/正式出口，以及支撑受控干预→新 trial→独立评估的实验控制面。首个目标是最小可演示的连续业务链：

```
Import → immutable Task/Step/Media → Search/Workbench → Review/Case
 → Outcome Evaluation → sealed Dataset Snapshot + Manifest
```

随后实现：

```
Reviewed Case → Diagnosis/Intervention → Candidate/External Trial Receipt
 → Independent Evaluation → Paired Comparison → Guard or STOP
```

**首要衡量**：外部行为正确、来源与审核可信、历史可恢复、单一写入事实来源、实现足够简单。不是复刻旧类、让所有测试命中一个模拟器、写尽可能多的 framework 或造一套通用 Agent 平台。

## 你可以读的材料

- 本包 `README.md`、`01_PRODUCT_PRD.md`、`02_DOMAIN_CONTRACTS.md`、`03_ARCHITECTURE.md`、`04_API_AND_WORKBENCH.md`、`05_CLEANROOM_MIGRATION.md`、`06_ACCEPTANCE.md`、`08_SKILLS_RUNTIME_AND_PIPELINE.md` 与 `examples/`。
- Python/FastAPI/Pydantic、PostgreSQL/Mongo/S3、React/TypeScript、Celery/Redis/Langfuse 等选用技术的**官方文档**和现有授权环境的部署说明。
- 集成/审计角色单独批准并脱敏的 API schema、旧系统黑盒行为 fixtures、输入/输出样例、Consumer Matrix、测试环境和 secret references。

**不得作为内部实现参考**：旧 `src/flywheel`、`src/evaluation`、历史 Agent/ORM/Case 目录、旧模板、旧类的自动迁移、旧函数名目录结构、旧测试对内部函数的断言、旧复杂业务分支。不要求你读 `00_REVIEW_AND_GAPS.md` 或 `audit/`；你的产品合同已在 `01–06/08` 中自包含。发现缺合同时写待决项与最便宜的可证伪假设，向审计角色索取**外部行为**而不是复制旧代码。

## 工程策略和设计自由

1. **先实现一个模块化单体**：一个 Python domain/application 层，FastAPI HTTP、独立 Worker/CLI、React typed UI，共享用例，不重复写业务状态。
2. **允许主动简化**：同义的类、端口、表、抽象都可合并；不以文档中的模块框数量为验收。业务 ID、权限、source revision、audit、不可变 record、全分母和独立 trial 身份不能删。
3. **已确认技术边界**：Python + FastAPI/Pydantic + React strict TypeScript；Mongo 持轨迹，MinIO 持媒体，PG 持控制记录，Celery/Redis 传输，Langfuse 观测。不要重新开启 PostgreSQL 替换 Mongo 的迁库选型。
4. **一份业务事实只有一个 owner**：source/task revision、Review、Case、Evaluation、Snapshot、Trial receipt 各有明确写入用例。broker、index、Langfuse 和 latest view 不持另一份可分叉事实。
5. **真实事件不要变成模型自评**：`proposal != dispatched != executed != observed_after`，机器评分不等于人工审核，Case review 不等于 membership，bad case 不等于训练样本，评分 repeat 不等于 Agent trial。
6. **不建多余平台**：第一版不需要微服务、泛化 DAG、多类队列协调中心、动态 plugin market、第二套 Skill store、第二份 Langfuse tracing UI、全量向量索引或复杂知识图谱。外部系统通过真实契约适配。
7. **对新旧差异要主动记录**：应消除旧产品已知错误，但有意更改外部用户行为/存储 schema 时写 ADR 与迁移/兼容测试，不悄悄删除使用中功能。

## 分阶段交付顺序

### Step 0 · 规格重述与设计约束检查

优先复用 `docs/adr/0001-aihot-openclaw.md`，仅对真正新增决定在 `docs/adr/` 输出最多 2 页的 `Architecture Decision Record`：本次产品边界、对象身份/状态、单写权威、选定存储/理由、最小 Run/Job 方案、源证据与 reviewer 分离、当前无法证明的风险。列出 `01` 的 P0 覆盖表和 `06` 的验收映射。对未决定的技术实现，先安排一项低成本探针；不要无限大讨论。

若审计方未提供 live consumer matrix，先实现纯 cleanroom 合同与 synthetic fixture，标注 `integration_unverified`，不假装生产可替换。

### Step 1 · Domain + schemas + 数据/对象存储

定义领域实体与不变量：SourceBinding/TaskRevision/StepEvidence/Review/Case/Spec/Run/Record/Snapshot/ExperimentRef；强制稳定 ID、版本/hash、Scope/CAS、状态与证据送达语义。实现能直接测试的最小存储 ports 和 SQL/object adapters。准备合成 fixtures 中以下 case：正常、错误目标、unknown、worker 技术失败、人工审阅、重复请求、媒体缺失、跨 split 重复。

只做**必要表**；用字段/约束/事务保证数据完整性，不预先写 N 层 ORM facade。先证明 `AC-002/004/009/010` 的领域级不变量；`AC-016/020/032/043` 此时只做领域/schema 级断言，完整端到端验收安排在对应后续切片。

### Step 2 · 导入与 fixed-version 浏览

实现单轨迹/批次导入，先冻结 raw/媒体和 `ImportManifest` 再提交 task version，receipt/逐项状态可在重启后读回。实现 source adapter 可替换，避免不同生产者各自直接写库。Task 列表/详情 API 支持固定 revision、step pagination、按需 image、action phases 和错误类型。

完成 `AC-001..015` 中与存储、来源和 API 有关的断言；交互项 `AC-014/015` 随 Step 3 的浏览器工作台验收。使用真实隔离 DB+对象存储+Broker 进行重复、部分写/宕机和 2000-step 测试。纯测试可用 PNG fixtures，但不要生成“看似真实”的证据结果来冒充真实数据。

### Step 3 · Review / Case 最小用户闭环

实现 review draft/decision 与 Case locator/facets 的单一业务 owner，审阅者身份从 session 绑定、If-Match/CAS、审计历史及单 Case ID。React 可从一屏最小 Task/Step、机器结果、Review/Case 侧栏开始；在连续页面实现点击证据定位、保存、刷新、冲突、返回、浏览器重开。

先满足 `AC-016..024`、`SEC-01/02`。对于复杂的批次 UI 可先实现分页列表与多项标准操作，不为完整 AG Grid 移植延后核心 Case 正确性。

### Step 4 · Reliable Evaluation + Dataset Snapshot

先接一个明确的 Task Outcome grader（允许 deterministic fake 作为工程契约），使用固定 obligation/check_ids、来源/证据可见性、模型 effective config、`Run/Request/Attempt/Record` 或语义等价的最小实现；只通过 owning API 保存，重复消息/投影失败/回填/重启处理正确。再添加 DatasetSnapshot freeze/admission、formal publisher 的 train/dev/quarantine/membership/manifest。首版只需一个真实可跑的纵向流程，不预建 20 种 grader。

完成 `AC-025..049` 中所有 P0 项（其余按 M2 Gate）；不要将 provider 回执或自由文本解析成功误报 GUI Outcome。用同一 synthetic 12 条集合验证完整分母。评估成本用 fake provider 计数，真实模型语义另外验收。

### Step 5 · P1 自进化交接和受控试验

实现 reviewed Case → InterventionDecision → CandidateRef → `accepted/needs_evidence/rejected` receipt → 外部 Runtime Trial/Skill consumer 回执 → independent grader → frozen paired comparison。不复制旧 Runtime/Workshop/Trainer 实现。新 Workshop 候选核心及 Runtime 消费/授权/回执合同可位于本包一级模块；真机执行、云 batch 调度和 Trainer 仍经明确 adapter 接入。具体范围见 08。至少对一次 `none/raw/skill` 比较展示具体 `NO_GAIN` 和 mixed improvement/regression 的报告，不能把任何假数据说成真实收益。

执行设备恢复须由真实 Runtime owner 验证状态等价、授权与副作用边界；未获得授权时只进行协议/fake 测试并明确 `real_trial_unverified`。完成 `AC-050..063` 并提交独立 reviewer 所需证据。

### Step 6 · 外部系统对齐和最终切换

按 `05_CLEANROOM_MIGRATION.md` 由集成方提供的活跃 Consumer Matrix 做逐项接入；不为 dead route 造兼容分身。写入数据迁移工具并进行 staging→check→publish+增量水位；所有 Task/Case/Media/Eval/Dataset 对账与单写切换/回滚需独立验收。运行目标环境 tests，owner 签字后才进行真实切流或旧系统退役。此 Step 不等于当前开发 Agent 自动拥有生产权限。

## 每个切片的强制交付格式

提交一份 `DELIVERY.md`（或 PR 描述）包含：

```
Scope: 本轮真实新增的用户能力/变更
Source: spec IDs / accepted architecture decisions
Behavior: 演示路径和 API 示例（含失败/unknown/权限）
Evidence: tests + command + commit + fixture/DB/object/worker/browser conditions
Compatibility: 本轮覆盖和未覆盖的活跃消费方
Data/Provenance: source/hash/revision/audit/denominator 守恒与不确定性
Cost: 真实调用、耗时、已知/未知费用，若全 fake 则明确写 fake
Risks: 阻塞/待测/未授权项
Exit: 达到当前 slice stop condition 还是 HOLD
Next: 一个直接阻塞可用性的最小动作，不扩想象平台
```

不得把“所有测试绿了”翻译为“生产就绪”，也不得把“能生成 Record”翻译为“语义评估可靠”。测试不应该为了通过而硬编码具体 task ID、模型答案、测试标签/fixture 名称；校验需要使用可信的内容证据和规则。

## 最关键的实现禁令

- 不得把 `task.version >= 1` 当作 reviewed，也不能从某个机器 status 反推人审。
- 不得重写历史 raw、机器 Record、审阅裁定或 DatasetSnapshot 的内容。
- 不得将 Worker's 结果写入任意 Task `latest` 文档字段并以此作为唯一权威；Task summary 可由唯一 Record 投影。
- 不得将缺证据 `unknown`、评估 timeout、GUI `env_error`、业务 `failure` 合并。
- 不得在 Step ex-ante 输入中偷看未来或 Gold；被评数据的恶意指令不得成为系统命令。
- 不得以模型自评、历史复用、抽象状态恢复或拼接旧后缀制造假 trial。
- 不得把训练候选、raw JSONL/回归样本或 Worker 产物直接作为正式训练数据，不走 Snapshot/Manifest/Admisson。
- 不得因 `Langfuse` 有 trace 就删除 EvoNext 的业务事件/Case/Eval refs，也不能再造一套全量模型 Trace 存储。
- 不得在无授权时执行真机、付费模型、大规模外部导出、训练、生产切流和旧数据删除。

## 什么时候停止本轮编码

交付的目标用户流程可连续执行，固定输入/状态/来源/权限通过验收，恢复/对账也有独立证据时，**停止继续增设抽象**。发现 missing function 先判断是否会阻塞 P0/P1 的真实用户工作；若不阻塞，保留 backlog，不先建框架。若某候选在真实独立比较中无净收益，输出 `NO_GAIN/HOLD/STOP`，不要为了形成“成功故事”再增加训练、模型调用或模糊指标。

**当前工作包**：先读取 `docs/ACCEPTANCE.md` 与 `docs/ROADMAP.md` 的实际完成范围；保留已完成的证据交换、策略/调用回执、Workshop 候选核心和 Runtime 合同。后续优先补真实脱敏包兼容与 Review/Case 连续流程，再接一个独立 Outcome grader。只有某条 AC 的完整前置与实测满足时才标为通过，不因存在基础类型或 fixture 而签署整条功能。
