# 01 · EvoNext 产品需求规格（PRD）

> 修订：2026-11-06 / 0.2。保留原全量需求与验收编号；这是目标合同，不是已实现清单。当前交付见 [实施状态](../ACCEPTANCE.md)，目录与存储以 [03](03_ARCHITECTURE.md) 为准。

**版本**：2026-11-06 / 0.1。**状态**：供独立实现的目标行为规格，不代表生产已实现。**定义优先级**：P0 必须交付，P1 完成首个闭环后交付，P2 有验证收益再考虑。编号可长期作为验收追踪键。

## 1. 产品使命与边界

EvoNext 是 GUI Agent 的**可信执行证据资产库 + 质量治理与人审工作台 + 实验和改进控制面**。目标不是把旧平台的每一个 URL 和类复制到新目录，而是让开发者回答五个问题：

1. 这条任务到底发生了什么，证据可靠吗，哪些证据尚缺？
2. 目标、约束及停止条件是否满足，哪个位置首次出现可证实偏离？
3. 谁确认了问题，根因是什么，最便宜且正确的修复层在哪里？
4. 用新代码、模型、Skill/Memory 或 Teacher fork 后，有没有独立可重复的净收益和退化？
5. 哪条来源、标签、修正、模型或实验进入了哪个训练/回归/发布版本，能否追溯和撤销？

上游包括线上真实回流、受控 rollout、人工采集/Teach、独立评测 trial、历史受支持的导入文件和外部训练/验收回执。**历史接口存在不代表继续支持**：Event-TP HTTP 上传及旧 Teach API 已被记载为退役，不要求恢复；需要历史格式时通过离线转换和当前导入契约。

下游为 Runtime、Evaluation grader、Skill Workshop/Memory、Trainer、Benchmark/Regression 与 Release owner。Flywheel 仅拥有必要的资产、任务、Case、运行账本、受治理 Snapshot 与交接记录，不私自接管设备、训练集群、生产发布审批。

## 2. 用户、常见工作和成功判据

| 用户 | 最重要任务 | 结束时的可见结果 |
|---|---|---|
| Agent/算法开发 | 查看失败任务、定位偏航与反事实、构建对照 | 固定来源、错误定位、证据、候选改动、paired 结果与成本 |
| 数据标注/审核员 | 搜索、修正字段、补证据、审核 Case、批次分诊 | 标注 revision、审核身份与理由、冲突提示、可重开草稿 |
| 评估开发者 | 选择 grader、运行/校准、比较策略 | 每个请求状态、完整分母、证据、误放行/unknown、评估用量 |
| 质量/项目负责人 | 发现高频可靠问题与处理进展 | 按来源/需求/能力/模型切分，显示未覆盖与真实分母 |
| 数据集/训练负责人 | 选择候选、验收资格、冻结、发布 | 可复现 Dataset Manifest、隔离/污染原因、消费回执 |
| 运营/自动化消费者 | 批次导入、重试、查询、回填与核对 | 幂等 Job/Run、错误与恢复状态、可审计 API/CLI |

### 2.1 关键不变量（比页面名称更重要）

- **事实与推断分离**：真实动作、执行回执、截图/模块 Observation 属于事实；视觉说明、模型预测、人工审核、因果假设和训练候选是不同来源的派生对象。
- **内容 revision 与审阅 authority 分离**：`version=1` 只说明存在一个修订版本，不证明有人校核。审阅必须有审核主体、时间、规则、revision 和证据。
- **计划、执行和效果分离**：proposal 不等于 dispatched，不等于 executed，也不等于实际 after-state；相邻截图不自动证明动作成功。
- **Case、数据池与修复层分离**：一个 Case 的审核、locator、failure lifecycle 和 membership 是不同 facet；bad case 不自动成为 trainable。
- **质量与用途分离**：结构有效不代表任务成功；任务成功不代表训练可信；一份候选 JSONL 不代表正式 Dataset。
- **运行与业务结果分离**：grader 的技术运行成功不等于 GUI 任务成功；unknown 不当作 fail 或 pass。
- **实验、采用和发布分离**：一个 candidate 由谁提议、谁评估、谁采用、谁撤销分别有权限、身份和回执。

## 3. 六条必须支持的端到端用户流程

### J1 · 导入并看清任务（P0）

提交单轨迹/批量 manifest（可包含媒体）→ 服务持久接受、返回 Job/回执 → 保存原始 payload/媒体 hash → 归一来源、动作及步骤 → 建立不可变 TaskRevision/StepEvidence → 搜索并打开任务 → 按版本查看截图、动作/回执、模型/模块 Observation、缺失项及原始来源。同步导入可直接返回回执，异步导入必须恢复并给逐项结果。重交同一幂等请求不重复保存，异内容冲突明确拒绝。

### J2 · 人工审阅与 Case（P0）

在 Task/Step 页查看机器结论 → 编辑人审字段、bbox、点/动作更正或评论（不覆盖 raw）→ 保存草稿和提交 → 宿主绑定可信 actor 与当前 revision → 冲突 412/409 让用户选择刷新/比较而不是覆盖 → 生成 ReviewRevision → 关联已有或创建唯一 Case → 审核结论及固定 locator → 可将 Case 加入 bad_case/regression/train_candidate/label_issue/env_issue 等用途池，但审核与入库是两个独立动作。原任务仍可查看旧版本，Case 变更留下审计。

### J3 · 机器 Outcome 与证据分歧（P0）

选择固定 TaskRevision 与冻结 Task Contract → 发起或查询现有 EvalRun → 查看排队/调用/结果/投影状态 → 逐个 obligation（对象、操作、数量、排序、时机、安全停止条件）展示 pass/fail/unknown/not_applicable/not_assessed、来源 evidence refs 和真实交付回执 → 一键进入审阅/Case。缺后态、缺全局比较证据、模型超时必须独立呈现。机器评分不能覆盖人工结论。可异步批量、重试技术错误并取消剩余任务。

### J4 · 从失败到可证伪的修复候选（P1）

审核过的 Case → 标定错误位置或有因果证据支持的区间及缺证 → 确认 root_cause_locus 与 intervention_route（weight/tool/rule/memory/skill/exploration/clarification/environment/safety/data/unknown）→ 选择成本低的候选，或回到补证 → 候选版本与所使用证据、父 Case/Run/Step 可追溯。Skill Workshop 或其他 owner 生成 candidate，Flywheel 只记录引用和审核回执，不把建议等同于成功修复。

### J5 · 恢复/Teacher fork 与独立对照（P1）

从失败步骤提出恢复请求 → Runtime 先验证当前设备状态与目标历史状态是否可合法/等价恢复；无法验证则显式停止或新起 trial → 执行真实新动作并记录新的 `trial_id`、起态、设备配置、真正使用的候选与工具回执 → 独立 grader 使用新轨迹给 Outcome/Step/Diagnosis → 与 baseline 按任务/家族/起态/预算配对比较。不能拿对旧轨迹更换 judge 的结果当一个新的执行 trial，也不能复制旧轨迹未执行的后缀宣称成功。

### J6 · 准入、冻结、正式发布及回传（P0 资产冻结；P1 正式训练联通）

按来源、固定 Case/标签 revision、质量与用途查候选 → 运行 admission / contamination / split 检查 → 冻结 DatasetSnapshot 和成员、查询、规则/版本/内容 hash → 生成受治理发布包（train/dev/quarantine/membership/manifest）→ Trainer/Benchmark 用 manifest 消费并回传消费版本和产物 ID → 后续实验结果绑定同一 Snapshot、模型版本和原 Case。不能通过动态 tag 查询代替不可变成员。unseen / held-out 受污染时不可认证。

## 4. 能力需求矩阵

### 4.1 Source、Task、Evidence

| 编号 | 行为（必须能被测试） | 优先级 |
|---|---|---|
| IN-01 | 单条 JSON/JSONL/multipart 和批次 manifest 统一为 IngestionCommand；来源 adapter 只做解析，不私自保存 | P0 |
| IN-02 | 含稳定 `source_key`, event time, producer identity, source hash, import-policy version, idempotency key；保持 task_id 字符串 | P0 |
| IN-03 | 原始 bytes/结构与媒体先校验/归档；缺图、损坏、partial 与待补图需被显式记录，拒绝伪成功 | P0 |
| IN-04 | 批次 Job 逐项进度、取消、技术重试、宕机恢复、reconcile 与计数守恒；不依赖 Redis 存唯一结果 | P0 |
| IN-05 | skip/error/new_revision 等已声明冲突策略；不得隐式 overwrite raw、审阅和历史版本 | P0 |
| IN-06 | 已退役外部入口只提供离线兼容转换（若存在有价值数据），不恢复双轨服务 | P1 |
| TK-01 | `task_id`、`trajectory_id`、`revision_id`、`step_id`、source_id 独立；latest 只是解析当前修订的 view | P0 |
| TK-02 | raw v0 与后续 revision 内容不可覆盖；修订写入保留父版本、actor、reason、change history | P0 |
| TK-03 | 长轨迹源顺序、0-based source step index、非连续 step ID、子任务 lineage/分支身份完整 | P0 |
| TK-04 | action proposed/resolved/dispatched/executed/after 与 image before/after/terminal 明确区分 | P0 |
| TK-05 | 任务列表、组合搜索、固定版本详情、证据引用、长轨迹跳步、按需图片/Trace | P0 |
| TK-06 | 证据 URL 到期可重新获权生成，内容身份不因 presigned URL 或目录变化而变化 | P0 |
| TK-07 | 允许派生结构/OCR/向量索引但不将其直接晋升 canonical fact | P1 |

### 4.2 Review、Case 与治理

| 编号 | 行为 | 优先级 |
|---|---|---|
| RV-01 | 任务/步骤级人工 review、批量审核、待办/认领/分配、意见与评论，所有变更带 actor 和 revision | P0 |
| RV-02 | 浏览/修改/刷新/切换时维护未提交草稿；版本冲突拒绝并允许比较重试 | P0 |
| RV-03 | 原机器结果不可被人审替换；人工修订新增独立 ReviewRevision，可纠正 GT/标签和锚点 | P0 |
| CA-01 | 每个逻辑问题唯一 Case ID；review、locator、memberships、failure_lifecycle 为同一 Case 的 facet | P0 |
| CA-02 | Case 固定 task/version/step/module，支持区间、多来源 refs 与空/unknown 归因 | P0 |
| CA-03 | 审核通过≠进入数据池；bad_case、regression、train_candidate 等加入需明确用途/范围/决策者 | P0 |
| CA-04 | 修改 reviewed locator 后旧验证/Regression guard 失效，需新证据再恢复 | P0 |
| CA-05 | 失败生命周期：待归因→已归因→修复中→已验证→加护栏→关闭；复发重新打开 | P1 |
| GV-01 | 基础质量 gate: schema/media/action/step order；失败不能冒充 Agent 失败 | P0 |
| GV-02 | 数据质量、评估结论、审核、污染、用途准入是独立状态轴，不复用一个 `status` | P0 |
| GV-03 | 所有处理有 processor run、输入绑定、policy/代码版本、diff、可重复执行的 idem/回执 | P1 |
| GV-04 | root/family/semantic duplicate 与 train/dev/unseen/benchmark 关系分开标注，阻止跨 split 泄漏 | P0 |
| GV-05 | 风险/环境/权限/误标签原因有自己的排除分母与 reason，不暗中丢困难案例 | P1 |

### 4.3 Evaluation、试验与改进

| 编号 | 行为 | 优先级 |
|---|---|---|
| EV-01 | 单条与冻结批次共用 source binding 和 Record 语义；开始前固定 rubric/model/prompt/证据策略 | P0 |
| EV-02 | 状态区分 queued/running/completed_with_errors/cancelled、技术错误与 Task pass/fail/unknown | P0 |
| EV-03 | 每个义务 check 的全分母和实际交付证据 refs；原生 Outcome 七类保留且映射版本化 | P0 |
| EV-04 | 不读当前样本已有 Gold/人审标签；ex-ante 不能含后续帧、终态或事后诊断 | P0 |
| EV-05 | 重复消息、未知回执、stale lease、模型回复后 Worker 崩溃、投影失败均可核对；已封存不重跑 | P0 |
| EV-06 | Outcome、Step/Span、控件/风控、Diagnosis、Planner/Matching/VQA 的专业语义保留；不得共用伪统一 pass 定义 | P1 |
| EV-07 | 评估器校准：独立 Gold、误放行、误拒绝、unknown、coverage、用量、复测稳定性 | P1 |
| EV-08 | baseline/candidate paired comparison 完整展示退化/增益/未评/不可比；区分 grader 与 agent 改动 | P1 |
| EX-01 | 受治理的干预分配/候选提出/接收/拒绝/补证与 candidate version，作者与独立 reviewer 区分 | P1 |
| EX-02 | 支持真正的新 trial 及设备起态/状态等价/lineage；Teacher/Recovery 需有实际执行回执 | P1 |
| EX-03 | 默认支持 none / raw memory / scoped skill 三臂，不强迫启用 Skill 或训练；收益不显著允许停止 | P1 |
| EX-04 | 同一个冻结实验条件下比较质量、覆盖、成本、耗时、退化和成功率；分母按独立 trial，不按 judge repeats | P1 |
| EX-05 | 经验/Skill 采用和撤销需要显式授权、作用范围与可追溯实际消费，不得自动上线 | P1 |

### 4.4 Dataset、出口与运维

| 编号 | 行为 | 优先级 |
|---|---|---|
| DS-01 | 基于固定成员/来源/标签/质量策略建立不可变 DatasetSnapshot，允许动态查询只用于选候选 | P0 |
| DS-02 | 每个快照保留规则、split、成员与字节级清单/哈希、审计、来源/标签版本；变更建新快照 | P0 |
| DS-03 | formal train/dev、quarantine、membership 和 manifest 分开；没有受治理发布回执不宣称可训练 | P0 |
| DS-04 | 不允许训练集与 benchmark locked/unseen 成员泄漏；同 family/near-duplicate 不跨可信 split | P0 |
| DS-05 | 训练/评测候选支持 SFT、preference、recovery/verifier 等信号的有依据导出，不要求实现训练本身 | P1 |
| DS-06 | 记录 Model/Trainer/Benchmark/Release 的消费回执与版本，不由 Flywheel 伪造训练结果 | P1 |
| OP-01 | 认证主体、数据 source/tenant 作用域和 read/review/write/export/admin 权限每个 API 与 Worker 重新核查 | P0 |
| OP-02 | 导入、审阅、Case、Eval、Dataset 的审计记录可按稳定 ID 串起来 | P0 |
| OP-03 | 作业概览、重投/取消/恢复、重启读回与异常排查，不能用仅存在于进程内的 Job 状态 | P0 |
| OP-04 | 重要结果含实际 model/policy/version、usage 缺失原因；Langfuse Trace 只作观测引用 | P1 |
| OP-05 | 搜索、来源/app/时间/需求成功率报表显示全分母与 unknown；明确自然流量 vs test/dev | P1 |
| OP-06 | 数据/媒体迁移核对、单写 cutover、只读兼容与回滚有工具、可签署报告 | P0 发布门 |

## 5. 不做什么、删除什么

**绝对不自动做**：未经用户授权触发真实设备危险操作、训练/生产发布；从失败自动生成训练 GT；从 embedding 命中推断已达成目标；覆盖原始事实或 reviewer 决议；未回执的模型调用声称低成本成功。

**不要求复刻**：已退役旧分发、旧 AutoResearch、旧独立 Find/Compile/Card/Provider、旧双套 Trace Viewer、Event-TP HTTP upload、历史一切兼容 alias。只有实测仍在使用的消费者才通过转换或兼容薄层接入。

**可选后续研究**：全局自动候选规划、复杂能力图谱、跨应用自动 Skill selection、生成式数据扩张、微服务、全量图存储、通用审批平台或数据库大一统迁移。每项必须单独说明一条真实失败、最便宜 baseline、独立验收和停止条件。

## 6. 成功指标与证据质量

- **工程正确性**：导入 accepted/succeeded/failed 分母守恒、哈希一致、重复投递无双计数、状态恢复、旧版本可读、权限隔离、页面连续流程。
- **数据可信度**：random spot-check 的 raw-to-canonical 保真率、媒体可解析率、人工与机器判断分歧、训练隔离拦截、不可复现样本占比。
- **评估质量**：Gold 校准的误放行与未知率、first-error 区间误差、必需义务覆盖、无后态错判率。合成样例只证明工程协议。
- **飞轮效果**：同一真实来源 family 的受控 baseline/candidate 对比，实际独立 trial 成功/恢复/退化、成本/token/总时延；没有证据的收益写 unknown。
- **使用体验**：从失败任务到可信 Case 的人工耗时、找证据点击/页面切换、200/2000 步操作可用性、批次分诊完成率。

所有百分比随分子、分母、来源范围、时间窗、去重规则、版本、unknown/未评数量一同展示。**导入数量、评估 Record 数量、Skill 文件数均不是自进化收益。**

## 7. 首个纵向交付切片（MVP）

1. 在新系统中导入含截图的合成/脱敏长轨迹，得到唯一持久 Job、TaskRevision 和可搜索视图。
2. 在页面打开特定版本和步骤，按需加载正确截图及源/执行/后态标记；添加注释、修改标签、保存审阅并经浏览器/Worker 重启重开。
3. 对同来源用一个 Outcome grader 评估，能显示成功、失败、证据不足、评估器技术失败四种边界，并创建/关联 Case。
4. 从固定版本/标签/Case 创建一个 DatasetSnapshot，保留污染/准入/成员清单，导出 manifest 与 quarantine，重新查询 tag 不会改变旧 Snapshot。
5. 至少验证一条外部实验结果的安全导入回执与比较呈现（MVP 可用 fake Runtime；**真实 fork 收益属 P1 实验验收**）。

MVP 可用并不等于全量替换完毕：`05` 的消费者矩阵、`06` 的切换门和真实环境验收仍然必需。
