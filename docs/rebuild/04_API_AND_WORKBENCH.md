# 04 · 对外 API、用户操作台与兼容消费合同

> 修订：2026-11-06 / 0.2。保留原全量需求与验收编号；这是目标合同，不是已实现清单。当前交付见 [实施状态](../ACCEPTANCE.md)，目录与存储以 [03](03_ARCHITECTURE.md) 为准。

本章描述**行为**和最小可用界面；示例 URL 为新系统候选路径，不是对旧系统已有路径的生效声明。新实现可统一版本化 API，但必须为已证实活跃的消费端提供转换/迁移，不能因代码清洁而直接破坏 CLI、Worker、外部回流与训练发布回执。OpenAPI、TypeScript client 与契约测试从同一 schema 生成/验证。

## 1. API 设计原则

- REST 表达对象和受控命令，长任务 202 返回 `job_id/run_id/status_url`，不在 HTTP 里等待模型/设备执行。
- 同一对象的 GET 不触发“缺失就默默拉远端/重评分/修正 latest”。需要远端恢复时显式 POST。
- 具有副作用或可能重试的 POST 支持 `Idempotency-Key`；返回不可变 receipt。相同 key + 相同 digest 读回原结果；不同 digest 409。
- 审核与保存使用 `If-Match`/revision，未知或旧版拒绝 412/428；服务端 actor/role/source_scope 决定权限，客户端不能挑选可信 actor。
- 列表分页、字段选择、按需媒体；源任务完整 raw、评估原生 payload、证据和 Trace 按用途单独取。所有 reference 显式绑定版本和 hashes。
- 同一用户可使用 UI、CLI 和自动化 API；没有“页面模型直接写库”“脚本绕过应用层”等隐藏路径。

## 2. 建议 API 清单（候选）

| 业务 | 建议 HTTP | 输入或行为与关键约束 |
|---|---|---|
| 接受单条源 | `POST /api/v1/ingest/trajectories` | 幂等 source key、source scope、schema/import policy、完整 payload/媒体包；返回 receipt 或 202 |
| 批量导入 | `POST /api/v1/imports` | 固定 ImportManifest、每项源/媒体/大小、策略；返回 job_id |
| 查询/取消/核对 Job | `GET /api/v1/jobs/{id}` / `POST .../cancel` / `POST .../reconcile` | owning job 状态、attempt、每项 checkpoint、不可回滚副作用、重启可查询 |
| 查找 Task | `GET /api/v1/tasks` | 来源/时间/app/model/tag/review/case/eval 过滤，明确 read scope、排序、cursor |
| 固定 Task 与版本 | `GET /api/v1/tasks/{task_id}/revisions/{revision_id}` | 固定版本、相应 hash、summary/证据索引；不从 latest 填缺 |
| 当前版本 | `GET /api/v1/tasks/{task_id}` | 返回 latest 指针、当前 version/ETag；声明这只是当前解析值 |
| 步骤/媒体 | `GET /api/v1/task-revisions/{rev}/steps/{step_id}` / `.../evidence/{id}` | 真正 step_id + ordinal、before/after、按需签名媒体、scope 保护 |
| 内容修订 | `POST /api/v1/tasks/{task_id}/revisions` | parent revision、patch 与理由、actor，CAS；保留 raw |
| 人审草稿/提交 | `POST /api/v1/reviews` / `POST .../{review_id}/decisions` | review scope、固定 task/step、rubric、审核决策版本；草稿无审核权威 |
| Case | `POST /api/v1/cases` / `GET ...` / `PATCH ...` | canonical locator + review/facet+revisions；不自动创建另一条重复 Case |
| Case membership | `POST /api/v1/cases/{id}/memberships` | 用途、policy、审核权限、污染/label 是否冲突 |
| Evaluation spec/run | `POST /api/v1/evaluation/specs` / `POST /api/v1/evaluation/runs` | 已冻结数据、评估问题、scope、effective config、预算、publication mode |
| Eval 进度/结论 | `GET /api/v1/evaluation/runs/{id}` / `GET .../records` | count 守恒、技术/业务/证据分离、按源固定版本；只读 |
| Eval 重试/取消 | `POST .../retry` / `POST .../cancel` | 仅技术失败和未完成子集、有界尝试；保持旧 Record |
| 外部评分回填 | `POST /api/v1/evaluation/requests/{id}/results` | request/attempt/lease/source hash/schema/usage；重复同内容 receipt，错版拒绝 |
| 数据集筛选/冻结 | `POST /api/v1/dataset-snapshots` / `GET ...` | 冻结成员、审阅与评估版本、隔离/用途、manifest hash |
| 正式训练数据发布 | `POST /api/v1/published-datasets` | 受治理 publisher，train/dev/quarantine/membership/manifest；事务性登记 |
| 干预/候选 | `POST /api/v1/cases/{id}/interventions` / `POST /api/v1/candidates/receipts` | 审核 Case、owner、目标、版本/证据 hash，候选引入不能自动执行 |
| 外部运行与反馈 | `POST /api/v1/trials/receipts` / `POST /api/v1/experiments` | 冻结环境与 trial lineage；真实使用/执行证据；experiment 可比性 |
| 配对比较 | `POST /api/v1/comparisons` / `GET .../{id}` | 固定运行与 metric rev、pairing、完整分母、成本与缺失 |
| 审计/运营 | `GET /api/v1/audit-events` / `GET /api/v1/analytics/...` | 来源/权限/时间/版本/denominator、不能泄漏其他租户 |

这份列表**不是要求首版一次实现 30 个 HTTP handler**。可按业务纵向切片只实现最少 endpoints；多实体查询可合并到明确的只读页面投影。只要没有复制权限与写逻辑，允许路由别名、API client facade 和 batch endpoint 减少往返。

## 3. 规范响应与错误

### 3.1 导入接受

```json
{
  "job_id": "imp-001",
  "status": "accepted",
  "status_url": "/api/v1/jobs/imp-001",
  "source_scope": "project-dev",
  "planned_items": 2,
  "idempotency_receipt": "receipt-001"
}
```

Job 查询提供 `accepted / preparing / queued / running / succeeded / completed_with_errors / failed / cancelled / needs_reconcile` 等适用状态；必须用独立 `item_states` 说明部分成功，`succeeded + failed + cancelled + pending = planned_items`（不同阶段使用相应集合，不能双计）。一个批次 cancel 不意味着已经写入的 TaskRevision/媒体被回滚。HTTP 返回超时后，客户端可通过幂等键查询确定接受结果。

### 3.2 任务详情摘要

```json
{
  "task_id": "202611061840001234567890",
  "trajectory_id": "traj-001",
  "revision_id": "rev-001",
  "is_latest": true,
  "revision_etag": "rev-etag-001",
  "source_binding_ref": "source-001",
  "step_count": 2000,
  "review": {"review_revision_id": "review-007", "status": "approved"},
  "evaluation": {"selected_record_id": "rec-009", "outcome_status": "unknown"},
  "case_ids": ["case-002"],
  "evidence_page_url": "/api/v1/task-revisions/rev-001/steps?cursor=0&limit=50"
}
```

review/eval 是**带来源指针的只读摘要投影**。若所引用的 review 实际审的是别的 task revision，不允许仍显示为本版本已审核；不能把 `review_revision_id` 从最新的 review 随便拼到任意历史版本。

### 3.3 Evaluation Record 视图

```json
{
  "run_id": "run-001",
  "request_id": "req-001",
  "record_id": "rec-001",
  "source_revision_id": "rev-001",
  "execution_status": "completed",
  "outcome_status": "unknown",
  "checks": [
    {"check_id": "goal.target", "judgment": "unknown", "reason_code": "missing_global_evidence", "evidence_refs": ["ev-001"]},
    {"check_id": "goal.stop", "judgment": "pass", "reason_code": "observed_before_payment", "evidence_refs": ["ev-003"]}
  ],
  "coverage": {"requested": 2, "pass": 1, "fail": 0, "unknown": 1, "not_applicable": 0, "not_assessed": 0},
  "evidence_delivery_receipt_ref": "delivery-001",
  "native_result_ref": "artifact://evaluation/rec-001.json",
  "usage": {"provider_calls": 1, "known_cost": null, "unknown_usage_count": 1}
}
```

对于 `execution_status=error`、`unknown` 与 `not_assessed`，前端不必下载全部原生 payload 才能展示正确状态。`native_result_ref` 的 artifact URI 与 content hash 必须由受权对象读取端校验；示例只展示接口形状。

### 3.4 一组标准错误

- `400/422`：schema/字段/内容受限，响应指出错误路径和安全 reason，不泄漏密钥和整个轨迹。
- `401/403`：未认证或没有当前资源的 scope/操作权限；必要时采用不暴露对象存在的 404。
- `404`：固定 revision/source/item 不存在。**不得退回 latest 偷偷返回另一个对象**。
- `409`：同一幂等键不同正文、相同 attempt 异内容、逻辑结果槽位冲突，携带可安全展示的原 receipt ID。
- `412/428`：stale revision 或缺强制 `If-Match`；前端展示差异，允许人工重新提交，不自动覆盖。
- `429/503`：预算/并发/服务不可用，清楚指明是准入失败还是已接受后待恢复，不把它算 GUI task failure。

## 4. 页面与信息架构（单操作台，不做重复 Viewer）

| 一级区域 | 必须能完成的工作 | 最小 UX |
|---|---|---|
| 数据搜索 / 任务列表 | source、app、model、time、tag、review/eval/case、自然/测试来源过滤；固定版本打开 | 结果数/条件/时间、cursor 分页；无需先导全量 JSON |
| Task & Evidence Workbench | 看指令及有效改令、步骤、动作各阶段、截图、模块观测、模型裁决/人审并列 | 左侧可跳 step/Case，主区当前证据，侧栏信息可收起；2000 步不全加载 |
| Review & Case | 编辑、草稿、保存、审阅、定位、审核理由、讨论、membership 和修复 | 单一 Case 身份，显示是否有未保存草稿/冲突，不在两个页面复制表单业务 |
| Evaluation | 发起、观察进度、看每条义务/证据、技术失败/unknown、retry/cancel | Outcome 与执行状态分开；证据点击定位原步骤，列表只取摘要 |
| Dataset & Governance | 搜索候选、质量/隔离/准入、冻结 Snapshot、查看导出 manifest & quarantine | 动态候选与 sealed dataset 清楚分离；已冻结快照只读 |
| Experiments | Case→候选→授权试验/新 trial→对照→独立验证→决定/撤销 | 保留 none/raw/skill 的缺项与不可比；不预置复杂 DAG 图 |
| Operations | 导入/评估 Job、进度/阶段/receipt、补投/reconcile、审计/权限 | 只有获权的人能重试/撤销/操作，所有按钮可确定结果 |

### 4.1 Task/Step 页面硬 UX 要求

- 任务标题与指令、`source_kind / task_id / revision / agent_trial_id` 和可观测的 review authority 同时展示；区分“机器结论”“人工审核”及“当前版本是否被审过”。
- 按真实步骤顺序展示 2000 步导航，可跳 ID、搜索错误/Case、首个偏航/窗口，侧栏实时 URL 固定 task revision；不能因页面分页改变 source step_id。
- 对一个 Step 单独展示 proposed/resolved/dispatched/execution receipt/observed after 与是否存在缺失；若只有动作前帧，明确标注不可据此验证后态。
- 仅在用户打开当前步骤/窗口时取证据和媒体，按新签名 URL 获取；UI 切版本时取消旧请求、忽略陈旧响应，避免 v1 图像显示在 v2 侧栏。
- 图像缩放、截图原尺寸与坐标标注要保留原图尺寸/缩放比例关系；人工修正 bbox 或点位置必须绑定使用的图片源及版本。缺图时显示错误与修复入口，不放一张看似正常的占位图误导审核。
- 查看机器更新或切 Step 不丢审核草稿；保存冲突需要差异/重试提示；链接返回 Case 的 task/version/step 不得残留旧深链接参数而误开另一个问题。

### 4.2 避免与 Langfuse 重复

EvoNext 的任务视图只显示必要**业务事件**：任务何时开始/停止、用户改令、动作提议/派发/回执、哪个模块调用结果与哪个证据。点击 `trace_ref` 到 Langfuse 看模型调用细节、耗时、token 与完整调用树。默认不另造一套相同模型 span 甘特图或 trace storage；如 Langfuse 不可用，Flywheel 业务证据和 Case/Eval 仍应正常工作，只提示深层 trace 暂不可达。

## 5. 活跃消费者兼容清单的模板

在删除旧路径前，**独立审计者**必须产出每一条消费链的实际证明，不能仅 grep 文件名就断言无流量。

| Consumer | 现有入口/产物 | 必需固定行为 | 新入口/转换 | 状态及签字 |
|---|---|---|---|---|
| Rollout/远端 backflow | 当前 rollout/import API | 来源版本、media、已接受/部分结果、幂等 | 见 IN-01..05 | 待实测 |
| ORM R1/R2 workers | 当前 direct source read + 回填 | 快照/权限/回执、队列行为、真实错误 | Eval Worker adapter | 待实测 |
| Task/Review/Case 页面 | 当前 Task/Cases API | fixed rev、人审 CAS、媒体定位 | React/API Workbench | 待实测 |
| Query/Analytics | Query Job/过滤/报表 | 完整分母、source scope、结果文件 | ReadModel adapter | 待实测 |
| 外部训练与数据脚本 | formal dataset manifest | MS-Swift train/dev、quarantine、会员与 hash | Publisher adapter | 待实测 |
| Runtime/Skill Workshop | 稳定 trial/context usage 回执 | 真 trial/候选 hash/授权 | Experiment adapter | 待实测 |
| 旧脚本/历史归档 | 仅经核实活跃者 | 历史只读转换，不要求保留所有 alias | Import adapter | 待实测 |

**合同优先**：consumer owner、真实样例、回归/监控、legacy 参数差异、截止窗口、rollback 必填。迁移后才撤旧入口；无活跃使用证据的废弃工具不必重建。注意检查运行中外部 URL、HTTP status、CSV/JSONL、Batch/Return shape 和签名媒体缓存，不只检查内部 Python import。

## 6. 可自动化操作的最小 CLI 形态

CLI 只做 authenticated API/application client：

```text
flywheel import --manifest <path> --idempotency-key <key>
flywheel task show --id <task-id> --revision <rev>
flywheel eval run --snapshot <id> --spec <id>
flywheel eval status --run <run-id>
flywheel dataset freeze --manifest <candidate-manifest>
flywheel reconcile --job <id> --dry-run
```

这里的语法是目标示意，非现有可执行命令。CLI 不直接通过 Mongo 私有文档更新 human 字段，不与 UI 并行持有第二个 Case 状态机。批量操作默认 dry-run/summary，必要时导出不可变 manifest 并要求明确写入授权。
