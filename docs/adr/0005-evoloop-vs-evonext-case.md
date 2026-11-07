# ADR-005 · 现役维护平台与自进化引擎的边界

状态：提案切片已实现（2026-11-08）；生产互通、评估语义与真实执行未验收。

## 两仓库职责

**EvoLoop = Legacy Platform**：维持现役运行、存量数据/API/设备/评估器和安全性，以问题修复和兼容为主；不再为“未来完整飞轮”增加第二套新框架。

**EvoNext = Evolution Engine**：从冻结执行证据出发，组织问题、诊断、干预、真实新 Trial、独立评价、采用/撤回和资产沉淀。旧平台不是新系统的父类或共用私有库。

数据交互仅通过已冻结的 OpenCUA JSON/包、显式 HTTP 合同和外部结果回执。不得双方并发写同一旧 latest/history/Case；不得以 EvoNext 查看旧评分为由取得旧系统的写入权威。新模型调用可写 Langfuse trace，但无权更改来源评估器的历史 Record。

## 为什么从 Case 开始

旧平台 Case 应用已退役，其历史数据和规则仍在。EvoLoop 的 evaluation.kernel、Agentic Review、Diagnosis 相关合同仍有价值，保留为可独立使用的参考或外部消费方，**不搬回旧 Python 内核**。

EvoNext 第一条业务垂直切片为：

固定 Snapshot → 当前步骤的问题提案 → Review 决策修订 → 唯一 Case → 后续 Diagnosis/Experiment 消费。

- 一条 Case 是一个问题身份；Review 是该 Case 的可追溯决策，不另建 FailureCase。
- Case 的 locator 固定 Snapshot + position + 可选来源 Step ID。版本 0 合法，不能由版本号推断人审；来源 JSON 与媒体不可改。
- Case Proposal 的 issue_kind 是症状类别，不是已确认根因；analysis_refs 只是冻结来源绑定的外部 Outcome/Diagnosis 引用，不自动导入其判断。
- Case Review 的 `confirmed/rejected/needs_evidence` 是操作员对问题成立与否的判断，**不是**模型任务 outcome，不授予训练、修复执行或发布资格。
- 同一 API key 只能证明一个服务或配置的操作员范围；当前没有真实多用户 RBAC，故使用 `operator_confirmed` 而非虚构 `human_gold`。正式多用户人审需独立身份认证与权限验收。
- 申请方生成稳定 UUID `case_id`，同内容重试幂等，异内容拒绝；Decision 采用 `If-Match` + 不可变 revision。重复同一决定不会生成第二次事件。
- 原轨迹、旧评估及来源审阅永不被覆盖。存量 Case 的历史导入必须走独立兼容审计，不在创建新 Case 时猜测旧属性。
- 本轮没有 memberships、Case lifecycle、诊断运行器或 Outcome grader。其权威在后续切片明确，避免先造多个平行状态机。

## 当前实现边界与验证

`review/contracts.py` 只表达一个问题的来源定位、证据及外部分析链接；`review/service.py` 核对 Evidence 固定快照；`review/store.py` 持 Case 与 append-only review。API 装配通过 `app/case_api.py`，不修改现有 Evidence HTTP 读取路径。

正式模式使用 PG evonext schema 的 `case_heads` 和 `case_reviews` 两张表（迁移 0003）；演示模式使用显式内存存储。共用已有数据库 engine，不在每次读取/决策时新建连接池。外部 Diagnosis 通过 `analysis_refs` 显示为**未验证引用**；后续与 Eval Record 对接需要独立来源/hash 验证，不在本轮直接调用旧模型。

前端旧 Sidebar 保持只读，新增独立 Case 面板；创建和审阅是明确的写操作。来源 ORM/grader 面板没有改写能力；后续生产身份接入之前，所有确认只记录为 operator attestation。

## 下一步

先验收 Case 保存/刷新/并发冲突/旧版本不漂移及真实 PG 迁移，再构造一个只读 Evaluation/Diagnosis 结果 adapter，让既有 Kernel Record 或新 Grader 结果以固定来源引用进入同一工作台。之后才运行一次有授权的真实新 Trial，独立比较并决定是否形成 Skill/训练信号。

没有真实有界评估与设备回执前，Case 不自动触发 Teacher Rollout 或 Training。
