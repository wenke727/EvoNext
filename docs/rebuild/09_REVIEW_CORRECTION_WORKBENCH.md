# 09 · 人在环的失败审阅、后续步骤纠正与修复验证工作台

**开发规格 v0.2 · 已确认设计约束 · 2026-11-08**

> 目标规格，不是实施完成声明。当前证据只在 [ACCEPTANCE](../ACCEPTANCE.md)；跨领域顺位在 [ROADMAP](../ROADMAP.md)。以 PR #3（\`30bc51f\`）的 Case/Review 合同为 A0 基线，保留旧 API 语义。实际业务写入仍需隔离实库验收。
>
> 本版裁决：**首轮 A0–A3；人工框统一存 0–1000；每 Case 一份共享草稿且单独 CAS；用途只预览资格、缺项、候选内容；智能诊断及真实 Runtime 后接。**
>
> **重要修订：纠正的位置不要求是首错。** 同一失败可有多个错误/恢复尝试，操作员可以纠正任意有来源的决策，尤其是错误发生后的恢复、重试、后续动作或答复。是否首次偏离属于 Diagnosis 的另一项假设，不能成为纠正的硬门槛。

## 1. 产品定位和权威边界

EvoLoop 是现役平台的稳定维护方，仍是其历史执行/评估与回流的权威来源；EvoNext 是从固定证据生成问题、纠正、独立新 Trial、验证和学习资产的自进化引擎。旧 Case 应用已退役，参考旧规则和真实故障，不复制旧后端、Prelabel 双写、旧分发或完整 Evaluation Kernel。

现有 React Viewer、时间线、原图和来源动作/BBox 标记继续复用。**Evidence 持有原始字节与来源身份，Review/Case 持有人工判断与纠正，Evaluation 持有机器判决，Runtime 持有真实新执行，Governance 持有训练/回归用途准入**。审核不覆盖 source、evaluation、runtime dispatch；没有调用 Langfuse 时也可以依据本地固定证据审阅。

首条可交付验收路径：

\`\`\`text
打开 Snapshot → 选中任意纠正步骤（不要求首错）
→ 在绑定原图上画“原目标/建议目标”区域，必要时手动指定点击
→ 保存共享草稿 → 提交操作员审核 → 刷新读回固定 ReviewRevision
→ 按 Diagnosis/Localization/SFT/DPO 用途查看资格和缺项
\`\`\`

**纠正的对象是决策或动作，不是“整个失败事件”**。某项纠正审核成立，不代表第一次错误已找到、全程任务已修好、Actor 训练样本合格、Runtime 已实际执行。

## 2. Case 发现、锚点及证据

一个 Case 是同一逻辑问题的唯一 ID；同一步可以提出两个不同 Case；一次请求丢失响应使用原 case_id 重发。一个 Case 可以包含多个 CorrectionItem：各自的 step 位置、源动作对象、原/建议框、人工建议动作与独立 verdict。多个 CorrectionItem 可引用首错之后任意不同步骤，**不能因其 position 不等于 Case 提案位置而被拒绝**。

三种位置绝不复用字段：

| 概念 | 语义 | 是否必填 |
|---|---|---|
| detection_anchor | 实际观察到偏离或终态的证据，支持任务级 | 必须有证据引用，不要求知道哪个动作先错 |
| correction_target | 每个 CorrectionItem 的实际待纠正步骤/动作 | 有具体纠正时必填，可晚于失败 |
| recovery_checkpoint | 新 Trial 可以安全恢复/重置的状态目标 | A0–A3 不要求，由 Runtime 另外验证 |

Case 提案明确 \`scope=task/step\`。步骤级保存 \`snapshot_id + position + nullable source_step_id\`；任务级 \`position=null\`，以终态/实际现象的 \`evidence_refs\` 定位，不伪造第 0 步。来源 \`task_id\` 是字符串，版本 0 合法；step_id、显示数组位置、源 index 和批量子动作编号不同。智能诊断可提供首错候选，但不得自动把候选写成 confirmed。

审核工作区仍要同时显示原指令、有效改令、时间线、动作前图、可信后态、模型提议、解析、实际 dispatch、回执、机器解释和缺证。下一步截图不能仅凭数组相邻推定“操作成功”。切步不改变本地草稿锚点；过期请求不覆盖新任务/图片。

机器 Outcome/Diagnosis 引用至少声明 producer、record ID、来源版本/hash、输入 hash 与绑定核验状态；第一版可继续使用 PR #3 未验证引用，但前端必须标注“未核验”，不能将其评估/诊断文字变成操作员决定。

## 3. 同一纠正的结构和坐标合同

### 3.1 CorrectionItem（独立审核单元）

| 字段 | 行为 |
|---|---|
| \`item_id\` | 在 Case 内稳定、唯一，保存草稿及审核后不换 |
| \`position\`、\`source_step_id?\` | 绑定原 Snapshot 内该步骤，**可位于最初检测错误之后**，不等于 source index |
| \`source_action_stage\`、\`source_action_ref?\` | \`model_proposal / resolved_action / runtime_dispatch / unknown\`；必须区分模型选错与执行器点错。未知保留未知，不补造原动作 |
| \`kind\` | \`region_only / action_correction / no_action\`；区域与动作不是同义词 |
| \`regions[]\` | 可有原目标/建议目标多个标注，每个都有独立 role、media、rect 和 provenance |
| \`suggested_action?\` | MVP 只支持明确指定的 \`click\` 与点；只有框时绝不取中心点造点击 |
| \`verdict\`、\`reason\` | 每个候选分别 \`accepted/rejected/unknown/not_reviewed\`；两个合理候选可都 accepted，未确认者不能默认通过 |

草稿可以同时含不同步骤的纠正项或没有纠正动作的纯问题判断。修正 source_action_stage 并不改变实际 recorded dispatch。待审/缺图/错图/非法坐标不会导致源轨迹重新序列化。

### 3.2 确认采用的 0–1000 归一化坐标

**人工新标注统一使用 \`space=normalized_1000\`。** BBox \`xyxy=[x1,y1,x2,y2]\`，满足全部有限且 \`0 ≤ x1 < x2 ≤ 1000\`, \`0 ≤ y1 < y2 ≤ 1000\`；点击 \`point=[x,y]\` 满足 \`0 ≤ x,y ≤ 1000\`。这些是坐标域约束，不表示原图在设备里是 1000×1000。

所有几何绑定原始冻结 \`snapshot_id / media_locator / media_sha256\`、服务端校验的解码宽高、方向 profile 和已声明的转换版本。页面原图不论缩放、留白或移动端尺寸，通过所见媒体有效图像矩形进行坐标映射，不可按整个包含留白的画框直接归一。SVG 缩放只改显示，源 BBox（可能是像素或 0–1000）保持原样；来源未声明空间则不得猜测。

\`\`\`text
媒体上展示坐标 x_media/y_media → 新人工 normalized_1000：
x = 1000 × x_media / displayed_width
y = 1000 × y_media / displayed_height

反向：x_media = displayed_width × x / 1000
      y_media = displayed_height × y / 1000
\`\`\`

持久化是浮点归一值而非像素取整；图像真实方向不明、EXIF 方向与显示不一致、媒体损坏或不匹配都阻止结构标注提交，但可以保存文字问题。后续导出给特定设备/模型动作空间时单独记录输入/输出 hash 与转换 profile，不直接把 normalized_1000 当设备像素点击。

Region 示例：

\`\`\`json
{
  "role": "suggested_target",
  "space": "normalized_1000",
  "xyxy": [472.2, 217.4, 768.5, 301.3],
  "media_locator": "images/step_003.jpg",
  "media_sha256": "SHA256_HEX_OF_BOUND_IMAGE",
  "image_width": 1080,
  "image_height": 1920,
  "orientation_profile": "upright_v1"
}
\`\`\`

此处示例 hash 为占位符；正式写入必须是服务端核实的 64 位十六进制摘要。

### 3.3 交互

基于同一 Viewer 提供两类框（原目标、建议目标）与点击点，区分来源框、人工框、模型提案和实际派发。支持绘制、修改数值、删除未提交框、撤销本次编辑；需要时增加拖动/边缘缩放，首版不处理批量多动作编辑与滑动纠正。按项审核多个合理动作，未确认者保持自身状态。画框不自动产生可执行修复，也不触发付费模型。

## 4. 一份共享草稿、两条版本链与回执

Case 有 \`case_id\`、源 locator、\`review_revision\`；每个 Case 仅一个持久共享草稿，拥有独立的 \`draft_revision\` 与 \`draft_hash\`。没有草稿时作为 revision 0/空内容读取，保存草稿不改变已审结论。审核修订永远是不可变的 ReviewRevision，包含当时**实际所见**草稿内容、证据引用、每项 verdict、操作员身份/授权强度、判定和 hash。

\`\`\`text
Case(case_id)
 ├── locator/scope       原来源绑定，不随 UI 当前步骤移动
 ├── draft_revision      共享草稿 CAS，可以多次更新
 ├── review_revision     追加的正式决定（可重审/撤回）
 └── use/application     不由 Review 顺手写入；只在目的 owner 执行
\`\`\`

- **草稿 PUT**：固定 case_id、expected_draft_revision、command_id、正文 hash，旧版提交 412；冲突时本地未保存编辑不能被覆盖。
- **正式 Review POST**：核对 expected_case/review revision、实际冻结 \`draft_revision + draft_hash\`、来源、actor/权限和 command_id；在一个 PG 事务内追加审核内容和版本。
- **幂等**：同 command_id+同正文+同 actor 即使 Case 更新也返回原回执；同 key 内容不同 409。优先查稳定回执，再做 CAS。
- **变更判断**：确认/驳回后重审或撤回必须新增 ReviewRevision，不覆写旧记录；若 locator 真正改变，独立推进 locator_revision，并提示旧回归/实验绑定待复核。第一版不能承诺自动失效实际已发布的外部对象。
- 操作员身份来源必须是受信服务器配置/会话；PR #3 的配置型操作员只表示 operator attestation，**不代表独立 Human Gold**。
- Case 一个身份；Review、membership、failure lifecycle、数据集准入不复制成第二个 Case。当前 v0.2 不建完整失败状态机。

保存失败、PG 不可用、断线和超时必须返回可解释状态；本地草稿在冲突/切步后保持，按命令 ID 对账而不是盲目生成另一份 Case。未保存草稿切换任务前提示。历史 GET 读取固定 ReviewRevision，不用最新草稿重建过去的人审事实。

## 5. 按用途预览；不做正式发布

统一只读 \`GET /cases/{id}/reviews/{rev}/previews/{purpose}\`，固定 \`ReviewRevision\` 与 \`preview_policy_version\`。状态 \`ready_for_preview / needs_evidence / not_applicable / blocked\`，返回可读候选、缺项与原因。**Ready 只代表允许生成只读预览，不代表用途审核通过，更不代表模型有效**。

| 用途 | 条件 | 缺条件时 |
|---|---|---|
| diagnosis | 固定审阅问题与证据，允许首错未知；后续动作纠正也有效 | 允许文本/证据候选，缺证标 needs_evidence |
| localization/regression | 有已审核区域或合理动作集合、原媒体与任务约束来源 | 不生成“唯一正确点”或正式回归集 |
| sft | 有 accepted 完整点击动作 + 可复验的 Actor 决策时输入/动作空间 | 只有 bbox 不造点击；无当时输入交付证据为 needs_evidence |
| dpo | 同一 Actor/同一可见输入下不同候选、明确人工偏好和分歧依据 | 等价/缺原输出、未来证据泄漏、执行器错误均不得凑负例 |

对来源 \`do_not_train=true\`、没有明确用途授权或已知污染，SFT/DPO 输出 \`blocked\`。不因训练预览存在而改变来源资格；正式 DatasetSnapshot/发布属于独立 Governance owner，当前不生成 train/dev/DPO 文件。

## 6. Evaluation、智能诊断、Runtime 的后续对接

Outcome 一次评估只代表其冻结任务义务、来源和证据可见性；技术错误、unknown、未评分别统计。Agentic Diagnosis 可有条件调查早期或后续任何偏离、恢复判断、替代解释；**首错是可选诊断结果，不是 Case/CorrectionItem 的准入条件**。模型建议不自动取得 Review authority。

Intervention 选择原因与修复路线（Tool/Rule/Skill/Weight/Env/Data 等）由 Review 后的独立治理决定；Runtime 只能经授权创建真实新 Trial，冻结 Case 修订、候选、检查点与起态，采集新动作和新后态；不能把旧后缀拼接当恢复。

独立评估必须绑定新 Trial 与原任务义务，报告改善、退化、不变、不可比、未评和费用分母。未证明净增益时允许 STOP，不因已有纠正文本自动 adopt。Langfuse 只做模型观测，不持评估/Case 事实。

## 7. 分切片交付与验收

| 切片 | 要求 | 停点 |
|---|---|---|
| A0 · 继承 PR #3 | PG Case/Review 的隔离并发/持久验收、浏览器提案/审核/刷新，任务级 anchor 与跨快照待审基本读取 | 保持旧创建/查询/审核兼容，无第二 Case 系统 |
| A1 · 纠正草稿 | normalized_1000 原目标/建议目标框、手动点、不同步骤 CorrectionItem；CAS 草稿保存、刷新恢复、错误/越界/错图拒绝 | 不做训练/设备/旧 Canvas |
| A2 · 审核冻结 | 按项 verdict、所见快照与内容 hash，固定 ReviewRevision、同命令幂等、历史精确读取、冲突保留本地编辑 | 不构建多人 Gold 审批 |
| A3 · 用途预览 | 诊断/定位/回归/SFT/DPO 统一状态、缺项和候选只读报告 | 不发训练文件、不发设备操作 |
| B · 机器回流 | 读取真实旧 Outcome/Diagnosis 并核来源，独立 grader/诊断后接 | 不复制旧 kernel |
| C · 实际修复 | 受控设备恢复与新 Trial、独立对照 | 不自动 adopt |

工程验收要求：pytest/compileall/Ruff + TS 单测/构建；浏览器完整的“选中错误后续步骤→画框→保存→审核→刷新→预览”，含任务切换、移动端、不同图片比例、0–1000 边界、多个合理动作、未提交内容保护；隔离真实 PG 校验 CAS/重启/幂等；200/2000 步测首屏/媒体加载与审核耗时。真实模型、设备和训练测试需单独授权。**不能用 synthetic unit 测试声明真实 PG、Browser 或净收益已经通过。**

## 8. 已确认决策与开发禁令

1. 首版只做 A0–A3。B/C 的模块合同可冻结，但不因协议已写就称接通。
2. 人工区域和点统一存 \`normalized_1000\`；来源旧坐标保持原格式，映射/方向必须验证。
3. 每 Case 一个持久共享草稿，CAS/version 独立；正式审核含冻结草稿和回执。之后如需真正独立盲审，才引入个人草稿及独立身份。
4. 用途只提供资格/缺项/内容预览，不正式发布、不转训练数据；SFT/DPO 的 Actor 输入来源必须可复验。
5. 失败发现、纠正目标、首错假设、恢复检查点四者分离；Case 内可以纠正错误发生后的任意步骤。
6. 不恢复旧独立 Case、Prelabel 双写、旧多套评分器、全量设备 Runtime、通用 DAL 或第二个队列。
7. 不因为 Case confirmed 就自动确认候选动作、训练资格、设备恢复或任务成功。

参见 [02 领域契约](02_DOMAIN_CONTRACTS.md)、[04 工作台/API](04_API_AND_WORKBENCH.md)、[08 Skill/Runtime](08_SKILLS_RUNTIME_AND_PIPELINE.md) 与 [06 原验收合同](06_ACCEPTANCE.md)。
