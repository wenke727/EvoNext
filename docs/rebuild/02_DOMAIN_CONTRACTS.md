# 02 · 领域合同与不可破坏的不变量

> 修订：2026-11-06 / 0.2。保留原全量需求与验收编号；这是目标合同，不是已实现清单。当前交付见 [实施状态](../ACCEPTANCE.md)，目录与存储以 [03](03_ARCHITECTURE.md) 为准。

**约束层级**：本章的身份、事实权威、审核权限、结果语义、幂等与历史不可篡改为产品硬约束。字段名是推荐协议；如果实现提出简化，必须提供无损对应表与对应的 `06_ACCEPTANCE.md` 验收，不能通过简化丢失身份或分母。

## 1. 领域对象及其唯一写入权威

| 对象 | 稳定身份 | 主要内容 | 写入权威/变更方式 |
|---|---|---|---|
| RawPayload | `raw_payload_id + content_hash` | 收到的源 JSON/压缩包、schema/version、收到时间、可信上传主体 | Ingestion；不可覆盖，存稳定对象引用 |
| SourceBinding | `source_system + source_key + source_revision` | 来源系统、producer、时间、task ID、source/hash 与导入策略 | Source adapter 在接受时冻结；不能从 latest 猜 |
| Trajectory | `trajectory_id` | 一条逻辑执行及其 lineage/family/agent_trial_id | Task/Evidence owner |
| TaskRevision | `task_id + revision_id` | 原 instruction、有效改令、step 列表、generation/env context、父 revision | 只追加版本；latest 是派生解析 |
| StepEvidence | `(task_revision_id, step_id)` | step order、动作各阶段、工具回执、before/after、model/模块观测及引用 | 原始 producer 事实不可改；补证需新证据修订/引用 |
| Annotation/ReviewRevision | `review_id + review_revision` | 标注、审核决议、审核人/来源、schema/rubric、变更原因 | Review owner；内容修订与事实源分离 |
| Case | `case_id` | fixed locator、review facet、membership facet、failure lifecycle、历史 | Case owner，同一个 Case ID，CAS 更新 |
| EvaluationSpecRevision | `spec_id + spec_revision` | grader binding、Rubric/Prompt、scope、reference policy、预算 | Evaluation owner；seal 后不可改 |
| EvaluationRun | `run_id` | 固定输入、运行状态、request/attempt/record 引用与计数 | Evaluation owner；状态可变、结果不可改 |
| EvaluationRecord | `record_id` | 一次评分的 checks、native_result、送达证据、用量、执行状态 | Evaluation owner；append-only |
| DatasetSnapshot | `dataset_id + dataset_revision` | 成员清单、来源/人审/评估版本、split/用途/隔离状态、manifest hash | Dataset owner；封存后不可改 |
| PublishedDataset | `dataset_name + dataset_version` | formal publisher 的文件校验、membership、quarantine、manifest | Dataset publisher；只追加版本 |
| InterventionDecision | `case_id + allocation_revision` | root cause、repair route、候选原因、owner、审阅回执 | Case/治理 owner；不自动授权执行 |
| ImprovementCandidate | `candidate_id + candidate_revision + content_hash` | Skill/Model/Tool/Rule/Memory 变更引用、作者、适用范围 | 候选能力 owner；Flywheel 保存不可变引用 |
| AgentTrial | `trial_id` | 真实新运行、模型/环境/起态、实际采用 candidate、执行 evidence | Runtime owner；评估不得伪造 |
| Experiment | `experiment_id + revision` | 固定 baseline/candidate、控制变量、评价准则、paired membership | Experiment control owner；seal 后不变 |
| AdoptionDecision | `decision_id` | 人审/独立裁决、采用范围、撤销与发布引用 | 具有授权的 Adoption/Release owner |
| AuditEvent | `event_id` | actor、动作、对象旧新修订、原因、trace、时间 | 对象的 owning use case 提交，不由 UI 填造主体 |

Task/轨迹事实仍由 Mongo 持有，PG 仅持其所属控制记录。共享基础设施不等于共享 write authority；禁止两平台绕过同一对象的保存规则直接双写。

## 2. 身份与来源

**task_id 是字符串**，可包含超过 JavaScript 安全整数的纯数字值。`trajectory_id` 是一次执行轨迹的稳定身份；同一个任务意图可有多个独立 trial。`source_record_id` 是外部产生者的身份，可能同名/重试；必须加命名空间。`root_task_id/family_id` 说明血缘或近重复，不等于当前任务本身。`step_id` 保留 producer 的源 ID，另外维护 `source_ordinal` 供 UI 按序显示，不能用 ordinal 替代来源 ID。

建议的 SourceBinding：

```json
{
  "source_system": "gui-rollout",
  "source_key": "batch-41/trial-7",
  "source_revision": "receipt-2",
  "source_content_hash": "sha256:<full-hex>",
  "task_id": "202611061840001234567890",
  "trajectory_id": "traj-41-7",
  "agent_trial_id": "trial-7",
  "import_policy_revision": "import.v1",
  "raw_payload_ref": {"object_key": "raw/sha256/....", "content_hash": "sha256:<full-hex>"},
  "producer": {"kind": "service", "id": "rollout-worker"},
  "captured_at": "2026-11-06T10:00:00Z"
}
```

这里 `<full-hex>` 是合同占位符，不是正式例子；见 `examples/` 中可解析的样例。所有哈希明确**计算对象、编码和标准化 profile**。稳定身份 hash 不应包括 presigned URL、临时磁盘路径、API 接收时间、分页光标或当前机器的绝对路径。原始字节 hash 与 canonical input hash 分开，避免格式归一后误判来源被篡改。

### 2.1 四种 revision 不可混用

1. `TaskRevision`：实际轨迹或可治理内容修订，可因人工更正、结构补全或字段变更产生，**不能表示人工审核状态**。
2. `ReviewRevision`：人类正式审核的决定版本，有 reviewer、审核范围和受审 TaskRevision；自动脚本不得伪造。
3. `EvaluationRecord / SpecRevision`：某位 grader 对某个冻结输入按某个 rubric 作出的机器结论；评估新结果不替换旧记录。
4. `DatasetRevision`：一份冻结成员、标签/决策 revision、用途与规则的资产版本；对其中 task 的未来修改不产生隐式更新。

快照或评估任何时候都不得只写 `task_id` 后在消费端自动读取 `latest`。若缺固定来源版本，状态为 `needs_evidence` / `not_assessed`，不自动补到当前 latest。

## 3. 时间与行动证据合同

一次 GUI 决策至少区分：

```
observation_before → proposed_action → resolved_action → dispatched_action
 → execution_receipt → observation_after/terminal_receipt
```

每个阶段可缺失，缺失必须明确 `unknown` 与原因。`value.tool_call` 是该 Task 版本的业务动作，原始模型提议另行保留；`runtime.dispatched_action` 是真正派发动作，工具 ack 是执行回执，任务最终成功必须有与 obligation 对应的观察或可信外部证明。截图声明 `frame_relation = before_action | after_action | terminal | unbound`，以及 `action_id/step_id`；下一步截图只有在已核验的时间与动作对应关系下才能充当前一步后态。未经对应不能按 step 数字加一推断。真实用户中途改令、撤销、付款前停止等改变 TaskContract 的适用目标与终止边界。

Step 的 evidence 可见性分 `ex_ante`（决策前）和 `retrospective`（按声明可含后续）；后者不能产生假的“当时可知”训练监督。`EvidenceReceipt` 分别记录 `requested / found / readable / delivered_to_model` 与内容 hash、解码错误/截断原因；只在索引出现、下载 URL 存在、模型自称看过，都不等于 delivered。

## 4. 人审、Case、归因与用途

`ReviewDecision` 需声明：受审 `task_revision_id` 与 locus、rubric/规则版本、`reviewer_id`（来自受信认证上下文）、`reviewed_at`、decision、理由、内容 hash、可反驳 evidence refs、parent_revision；`review_status = unreviewed | pending | approved | rejected | disputed`。审批/确认与普通字段 edit 分开，不允许后台按 `task.version>=1` 自动设置 approved。草稿 `draft` 不应自动获得审阅权威。

Case 只有一个 aggregate：

```
Case(case_id)
 ├─ locator (task_revision_id, step ids/span, module, locator_revision)
 ├─ reviews (review ids, decision revisions)
 ├─ memberships (pool, policy, reviewer, admitted_at, source binding)
 ├─ failure_lifecycle (root cause, allocation, fix, validation, guard, reopen)
 └─ audit_history
```

`locator_revision` 改变时，关联旧 locator 的已通过验证、复用候选/回归护栏必须重新核对；不能默默搬迁。不同 Case 可引用同一 task/step；不能仅按 task/step 自动合并多个独立问题。同一个 Case 可参与多个**合法**数据池，但同一 family 和同一固定样本在 train 与正式 regression/unseen 间需隔离。

`root_cause_locus` 表示观察到的因果错误原因；`intervention_route` 表示本次修复放在哪里：`weight | tool | rule | memory | skill | exploration | clarification | environment | safety | data | unknown`。一个错误可以有多个假设，但一次有批准的 intervention 选择一个**主要路线**和 owner；若未知就停在 unknown。reviewed allocation 是修复 proposal，不代表 Skill 已创建、模型应训练或 Runtime 有执行权限。

Case 生命周期（可配置为业务用词，但语义不能合并）：

| 当前态 | 动作 | 下个态 | 必须有的事实 |
|---|---|---|---|
| discovered | 人审核心证据 | reviewed / needs_evidence | reviewer、locator、判断与理由 |
| reviewed | 确认 root cause | diagnosed / unresolved | reviewer、cause/unknown |
| diagnosed | 选择 intervention | allocated | route、owner、依据、权限 |
| allocated | 建修复/候选引用 | fixing | candidate hash 或变更计划 |
| fixing | 独立验证新 trial | verified / rejected | frozen trial、grader record、配对对照 |
| verified | 添加固定回归护栏 | guarded | suite version、gold、无污染确认 |
| guarded | 关闭 | closed | 关闭判断与回归链接 |
| closed | 回归复发 | reopened | 新证据、复发原因，不能抹掉旧证据 |

未审核/无权主体不能直接越级写 closed；历史系统的 facet 可映射到上述语义，**不要求数据库逐态照搬名称**。

## 5. Evaluation 合同

### 5.1 请求单位与独立性

推荐完整对象链：`DatasetRevision → SpecRevision → Run → Request → Attempt → Record`。实现允许在同一关系表中合并 Request/Attempt 的局部状态，但下列四个 ID 必须语义独立：

- `agent_trial_id`：被测 Agent 真实执行一次任务；影响实际可靠性统计。
- `grading_repeat_index`：对同一个实际结果再次评分；只测 grader 的稳定性。
- `attempt_index`：一次评分 Request 因超时/429 等技术原因重新试。
- `provider_call_index`：一个 Attempt 里真实发起的模型/工具调用和协议修复数。

一个 Request 是 `run_id + item_id + grader_binding_id + grading_repeat + agent_trial_slot`。`grader_binding_id` 必须冻结 `grader_version + scope + visibility + effective_config`，避免不同 step/scope 相互覆盖。

### 5.2 三个独立状态轴

- **Run 执行**：`queued | running | completed | completed_with_errors | failed | cancelled`；存在技术报错但已结束时不改写成 Agent failure。
- **Record 技术状态**：`completed | partial | error | cancelled`；另保留 requested/queued/not-run 这类没有正式 Record 的 Request 情况。
- **Check 判断**：`pass | fail | unknown | not_applicable | not_assessed`。`unknown` 是尝试过但缺证；`not_assessed` 是未判断（预算、取消、错误等），`not_applicable` 是明确定义条件不适用。

对预冻结的 requested_check_ids，必有：

`requested_checks = passed + failed + unknown + not_applicable + not_assessed`。

Task Outcome 独立为 `success | failure | unknown | not_assessed`，Native Outcome 的 `perfect / fair_enough / failed / env_error / uncertain / unsafe_failed / invalid_input` 原样保留，并使用版本化 mapping policy 转公共结果。模型 API timeout 属于评分技术失败，不等于原任务 `env_error`；工具自报 success 不证明任务成功。一个 Task 成功不推出每个 Step 都正确。

### 5.3 结果固定与乱序

Run 在受理时冻结 data/evidence/input hash、SpecRevision、model/rubric/prompt/预算与 allowed reference policy。网络重投同一个 idempotency key 且内容相同返回同一 Run/receipt，异内容明确 409；Worker 条件领取，最多选择一个当前 Record。崩溃后可重投；**不能宣称 provider exactly-once**，未封存返回可能产生第二次付费调用，须有 unknown-call/budget 审计。

技术 retry 只新建 Attempt，保留旧结果；语义 fail/unknown 不因技术 retry 自动变 pass。旧 source revision/expired lease 迟到的记录可归档，不得取代当前选中结果。兼容 task latest 显示只是投影，不得作为机器真值；投影失败重试投影，不重跑模型。结果比较必须绑定当时选中的 Record 集合与指标版本，不被后续 retry 改写。

### 5.4 Evidence 与 Gold 隔离

模型输入由受控 `EvidenceForEvaluator` 白名单投影生成。初始用户指令、有效改令、task contract、动作事实、允许的 reference 及原始证据可以进入；当前样本 Gold、历史审核结论、先前机器判决默认不能进入独立 judge。含有隐藏答案的自由文本/截图需提前排查、标记污染、隔离或者独立人工确认，不能只靠字段 whitelist 自称解决全部泄漏。

## 6. Dataset 与污染控制

DatasetSnapshot 记录 `purpose`（train_candidate / formal_train / dev / benchmark / regression / diagnostic）、`dataset_revision_id`、有序 membership、每个成员的 fixed TaskRevision/ReviewRevision/label/quality refs、source lineage、family、query/policy/config hash、media checksums、split/exposure、seal 时间与作者。成员不可变；动态 tag/查询的后续变化不回流至已封存快照。不要用 task_ids_hash 一项替代成员 revision/内容哈希。

污染/准入状态至少：`clean | suspected | contaminated | unchecked`，且保留检测 profile、scope 和 evidence。**unchecked 不能自动等于 clean**；开发探针可有显式 limited override 与风险标注，正式 protected benchmark/train 由用途准入规则控制。`source_family`、fork、同一原始来源改写、near-duplicate 在 split 前做归组；无法确认时 `exposure=unknown`，不能授予 unseen 身份。

正式训练数据由唯一的 `publish_dataset` 语义边界生成 `train.jsonl`、`dev.jsonl`、`quarantine.jsonl`、`membership.jsonl`、`dataset_manifest.json`。输出 JSONL 是数据面，manifest/membership 是控制面。输出必须记录 schema/publisher/revision/hash、样本/拒收的完整计数以及允许的 media。`trainable` 不等于已训练或已发布模型。Benchmark/Regression 快照可采用不同导出格式，但遵守相同不可变成员和隔离原则。

## 7. Intervention / Skill / Recovery / Experiment

### 7.1 交接协议

任何跨 owner 交接记录至少包含 `handoff_id`、`schema_version`、`idempotency_key`、source Task/Case/Run/Step refs、checksum、目的 owner、scope/allowed_usage、review authority、请求、状态和回执。接收方必须返回 `accepted | needs_evidence | rejected`（及理由），随后给出 `produced_candidate_ref` / `no_candidate` / `terminated` 结果之一。重复同内容返回同一 receipt，冲突拒绝。只有审阅者审核后允许进入受控消费，不把 accepted 解释为候选有效。

### 7.2 Recovery 的真假界线

`fork` 是一个**新的执行 lineage**，不是旧轨迹 JSON 截断后加生成文本。恢复实验必须有 Runtime 侧授权、目标历史锚点、当前设备可观察状态、state-equivalence verdict、restoration action logs、new trial_id、actual actions/observations、provider/model/agent/harness version 与错误处理。不能断言任意时刻手机可以恢复到精确的历史状态；不可验证或不可合法恢复时选择新 trial 或 `blocked`。模型 Teacher 产生正确建议但没有设备执行只能是 `proposed`, 不计真实修复成功率。

### 7.3 三臂比较与收益证据

Experiment 比较预冻结的 `none / raw memory / compiled or scoped skill`；允许实验只测两臂但必须声明缺失的第三臂和原因，不能在不完整时宣称 Skill 净收益。每条 trial 记录真实消费的 candidate/hash、使用上下文、环境版本、起态/复位一致性、独立 grader、成本/延迟/unsafe、回归约束。变化的变量一项项声明，模型/环境变动不是 Skill 收益。改善、退化、不可比、缺失全部入报告。发布采用/撤销是另一个明确决策，不能由作者自己评分自动触发。

## 8. 数据写入、删除、保留与访问

1. Canonical raw 与内容修订只追加；自动机器判断、人工标注、Case lifecycle、Spec/Record、DatasetSnapshot 都有明确 owner 与 append-only history。必要的 `latest`、`summary` 和搜索索引是**可重建的缓存**，要写明来源版本及失效规则。
2. 所有人工/管理动作由受信会话/API key 绑定角色与 scope；客户端不得通过 request body 自称 `reviewer`、`admin` 或 `HUMAN_REVIEW`。读/写/导出/获取签名媒体逐次核查作用域，不依赖界面隐藏按钮。
3. 敏感来源、凭证、内部网络地址、个人数据需按配置最小化/脱敏；生产密钥不进入 Dataset、trace、日志或提示词。媒体签名 URL 是短时访问凭证，不放在长期 hash 身份里。
4. 清理策略必须区分数据保留/隐私删除的合法请求与不可变审计：数据可以按受控保留政策删除或匿名化，且需留下**不泄露原内容的删除收据/墓碑**，不能以“不可变”为由无限保留私人原始数据。存量脱敏和删除遵守实际授权与合规边界。
5. 任何外部调用可收费/有设备副作用的操作必须有执行 owner、批准 scope、明确预算与确认门；失败、未回执与取消都需要正确的费用与执行状态描述。

## 9. 最小领域验收谓词

- 同一 task/version 的两个 grader 不争一个结果槽；同一 grader 的 ex-ante 与 retrospective 不串证据。
- 对旧版本产生的评估不因 latest 移动而绑定新版本；对旧版本的 Case locator 可稳定打开。
- 自动 task revision 不能让 review_status 由 unreviewed 变 approved；同版本人审也不能覆盖机器 Record。
- 导入后 Job 可重启恢复；相同源内容重复交付不新增原始事实，异内容不能悄悄覆盖。
- 一份 expired presigned URL 不能改变资产身份；损坏对象通过 checksum/receipt 报错误。
- 同一 Case 不复制第二条 failure Case；池 membership 不代替 review。
- 离线 judge 重新跑一次只增加 grading repeat，不增加 agent trial。
- 训练文件中不混入未通过 admission 的 quarantine 与 benchmark_locked 样本。
- Recovery 后静态套旧轨迹后缀不能声称成功；状态不等价时禁止继续效果归因。
