# 08 · Skill Workshop、Runtime 与处理闭环

## 1. 当前交付边界

本轮实现可本地验证的 Skill 候选维护和 Runtime 消费合同，不复制旧系统，不建自动进化后台。没有配置真实模型/设备，也不执行已有数据里的 tool_call/code。新文件中的模板不是已校准评分器，prepare-trial 不是设备 rollout。

## 2. Skill Workshop

Skill 是带适用条件、步骤、关键入口、已知陷阱、修正和完成检查的操作指南。事实放 Memory，项目约定放仓库文档；不是把整个轨迹改名成 SKILL.md。消费已有 Agent 轨迹，不重建 DemoParser。

本地候选能力：create/save、expected_revision CAS patch、no_change、history、diff、archive、restore/Undo、精确 revision export。目录绑定 owner，Skill ID/路径受限，metadata 重复 key 拒绝，读取复验内容 hash；原版本不可覆写。restore 产生新版本，保留父版本和恢复来源，因此 Undo 也能被追溯；它只恢复候选文档，不回滚设备或外部业务。

每份 SKILL.md 使用 name/description YAML frontmatter 和 Markdown body。portable SkillBundle 带 owner/skill_id/revision/content_hash/source_snapshots/stage。source_snapshots 只是绑定引用，当前文件库不证明这些来源已审核或可训练，调用者仍须通过 Evidence/Case owner 验证用途。保存与导出始终 candidate，不自动变 active/READY。

本轮不加载 home/workspace 中任意未注册 Skill，不执行 scripts，不自动安装第三方插件。archive 阻止新导出；已经冻结的运行快照不被改写。正在执行的高风险场景需要外部 Runtime 独立支持停止/撤权，不能靠改磁盘 Skill 文件假装停止。

## 3. 有界学习和复核（后续工作包）

输入：固定开发证据窗口、受审核问题/反馈、当前 Skill 或明确无匹配、允许用途和统一预算。
流程：检查现有候选 → PATCH 优先／CREATE／MERGE／NO_CHANGE／NEEDS_EVIDENCE → 提交前完整复核 → 有界定向修补 → 保存候选或停止。

复核应分别检查来源支持、适用范围、参数与常量、负向约束、完成证据、反例/局限。视觉证据按来源 step/evidence ID 读取并核 hash；图片 index 不等于已交付。文本提案不能冒充动作执行，作者自评不能作为独立验收。缺证、预算耗尽或持续无新证据停止；不强制每次运行产 Skill。

生产式模型 learner、视觉复核、merge UI、feedback 回流尚未实现。未来通过 providers 的冻结策略与收费回执接入，不把学习规则写进 CLI，也不为本模块建第二套 ModelClient。

## 4. Runtime 与 OpenClaw 的对应

借鉴 OpenClaw 的 session/context/model/tool/receipt 边界和运行期间 Skill snapshot 固定。EvoNext 不是消息渠道网关，不复制聊天渠道、ClawHub、全套 plugin harness 或 Runtime 内部类。

RuntimeRequest 明确 trial_id、session_id、task_id、snapshot_id、owner、target、context_mode、固定 SkillBundle、before_step_position、动作预算和可选恢复请求。当前 source snapshot 是运行输入，不当作新执行结果。

- none：不注入经验。
- raw：只交付指定决策点之前的来源步骤白名单字段；不包含未来步骤/人审结构化标签。原文本或图片内的隐藏答案仍需数据资格与人工检查，字段投影不能保证完全消除泄漏。
- skill：只使用已经固定的 bundle；不运行中查“latest”、不从 Workshop 文件自动更新，不声称手选成功等于自动选择有效。

上下文冻结得到独立 context hash；plan 另有 hash。调整 Skill 不改变在途计划，换模型或改输入必须形成新的对应身份。local_device 和 cloud_batch 是不同 target kind，resource_id 是设备或批资源，不强行把云 batch 伪装成单设备。

## 5. 授权与真实执行

ExecutionGrant 由可信宿主提供，不信任模型/客户端自报。必须绑定 trial/task/snapshot/owner/target、有效期、动作预算和精确 SkillRef（revision + content_hash + owner/来源绑定）；candidate skill 与 recovery 需要独立 opt-in。check_grant 是校验函数，不是完整身份服务，也没有提供远程 dispatch endpoint。

后续 Runtime adapter 的提交必须先完成持久 admission、资源租约和副作用审批。会话串行与全局资源并发是两个约束；本轮只定义 session_id，不伪造已实现的分布式会话锁。长任务取消是停止新动作并收束已派发动作，不声称撤销已经发生的行为。

恢复仅允许 current_state 或 replay_prefix 请求，携带 reviewed Case、来源 Step ID、before_action/after_action 边界和预期状态。实际状态等价必须由执行端核对；请求中有 hash 并不证明已经恢复。缺失/重复 Step ID 拒绝，不用数组位置伪造原 ID。失败可 blocked/not_equivalent/unknown；改变动作后必须执行新后缀，不能复制旧轨迹。

消费回执绑定 plan/task/snapshot/context/Skill refs 和新轨迹引用。当前 verify_usage 只确认关联一致，execution_verified=false，outcome=not_assessed。独立 evaluator 评新轨迹，不能把自身 binding 校验当任务成功。

## 6. AIHOT 流程在本项目的落点

采集 → 原始快照；预筛 → 便宜确定性结构/媒体检查；评分 → 按义务逐项 Outcome；复杂问题 → 按需调查与人审；聚合 → 原 Case/轨迹上的派生失败模式；校准 → 独立开发/留出集；精选 → 受审核的优先处理建议，不等于训练或发布授权。

聚合候选先按 App/版本/目标/现象召回，再判断 candidate_same_mechanism、related_symptom、unrelated、unknown。当前只提供版本化关系 Prompt，未实现索引、自动分组或写入合并。模型不能覆盖人工归属；重复上传、同任务 retry、独立需求分别计数。保留反例和未知，不能从相似文本推断同一根因。

新鲜度与采集时间分开，采集失败不推进成功 watermark；导入与消费按来源幂等。共享读取层承载相同资格规则，缓存不能延长撤权/删除的有效期。这些是后续采集/协作切片的必测合同，不因基础包导入实现就宣称全部支持。

## 7. 新增验收（工程合同，不替代 06）

| ID | 行为 |
|---|---|
| AX-01 | 旧 Python 路径移除；app→领域→contracts，Runtime 不 import Workshop、contracts 不 import 存储/网络 |
| AX-02 | Prompt 缺变量、非法 include、循环、秘密配置拒绝；共享规则改变必须改变 policy hash |
| AX-03 | 同请求复用已收到响应；新 repetition 不复用；malformed JSON/non-2xx 留原响应 |
| AX-04 | timeout/崩溃后 sending/unknown 不自动重发；预算跨请求原子计数，不持锁等模型 |
| AX-05 | 技能新建/patch/no_change/history/diff/CAS 冲突正确；原版本不可覆写 |
| AX-06 | Undo 新增可追溯版本；archive 阻止新导出；冻结 Trial 不随文件变化 |
| AX-07 | 不同 owner、越界路径、symlink、重复 YAML、篡改 hash 拒绝 |
| AX-08 | none/raw/skill 区分，raw 截止不读未来；Scope/Skill hash/输入身份绑定 |
| AX-09 | local/cloud target 不混；过期/错 target/超预算/未授权 candidate 与恢复拒绝 |
| AX-10 | usage mismatch 或原 snapshot 冒充新轨迹拒绝；正确 binding 不升级任务成功 |
| AX-11 | 真 PG 多进程预算/唯一性、kill/响应丢失/重启恢复/权限与保留策略，必须实库验收 |
| AX-12 | 真实学习/视觉复核、实际设备恢复及 none/raw/skill 独立收益，必须单独语义验收 |

## 8. 最小操作

```bash
# 保存候选：source 必须换成实际允许开发使用的 snapshot hash。
evonext workshop save check-target --root .local/workshop --owner dev \
  --file examples/skills/check-target.md --source <snapshot-hash>
evonext workshop history check-target --root .local/workshop --owner dev
evonext workshop export check-target --root .local/workshop --owner dev --revision <revision>
# RuntimeRequest JSON 内放精确 bundle；本命令仅准备，不执行。
evonext prepare-trial --request .local/request.json --bundle .local/source.zip
```

本轮停止于可测试候选维护、冻结消费和调用恢复基础。下一步是真包兼容、Review/Case 与一个独立 Outcome grader，而不是先开发自动 Skill 商店或万能运行平台。

## 9. Workshop 草稿、学习与精简

2026-11-10 增补范围：在现有本地候选 owner 上实现草稿、完整多文件版本、显式学习与精简。实际检查结果由 ACCEPTANCE 记录。依据 OpenClaw Workshop 的 draft/diet/统一 authoring 思路独立实现，不复制其插件框架或旧私有实现。上游研究固定于 `bd0557f4fac019b945905facd9211ae726210647` 的 `extensions/skill-workshop/src`；草稿的基线 revision 绑定是本项目额外约束。

责任分开：

- `library.py` 管不可变版本、历史、CAS、归档和恢复；`drafts.py` 管完整提案、复核绑定、丢弃和显式提交。
- `authoring.py` 管文件/Markdown 引用与可达性校验、建议性 lint、整段原文搬移。脚本附件是惰性 UTF-8 内容，不执行。
- `service.py` 管固定 Evidence 步骤、可选原图、固定 Case 审核版本以及最多一次修复。`policy.md` 是 Git 维护的统一规则，提交时冻结正文与 hash。
- app 装配既有 gateway、PG 操作回执和 Celery；Runtime 仅依赖 `contracts.skills`。没有新增调度器或模型传输层。

**流程**：选择已有 Skill（或明确新建）和证据 → 预览 → 提出完整草稿 → 人工或模型复核 → 操作者显式提交 candidate。手工草稿固定整个来源快照；模型草稿还固定选定步骤、Case 引用、输入 hash 与 operation_id。修改既有候选时保留原来源集合。每份提案的内容、base revision 和来源共同形成 draft_id；改内容必须新建草稿。过期草稿拒绝提交；先读最新版本再重新提案，不静默覆盖。磁盘在 HEAD 更新后、草稿提交回执前失败时，重试核对同一提案的已落版本后补回执。

学习针对一个明确 Skill 目标修订，允许新建、`no_change`、`needs_evidence`。模型最多生成两次、复核两次；缺证停止，驳回最多修复一次。最终仍是候选，没有任务成功、激活、采用或训练资格。Case 必须引用一个已保存的审核版本，且其步骤位于本次选定证据内；纠正提案始终不等于已执行成功。Case 确认不会自动触发学习。

精简是独立显式操作：模型只选择 `##` 段标题，host 将原文搬入 `references/diet.md` 并保留原位置的读取入口；主文至少减少 20%。已存在 diet 文件、歧义标题、选中段中的链接/代码围栏、引用式链接等无法安全搬移的情形停止，交给手工草稿。语义复核额外检查条件、顺序、规则强度、检查/退出规则和正确读取时机，字节保留不是语义通过。普通引用校验使用 CommonMark 解析器，校验本地目标/标题锚点与 references 文档可达性；复杂 HTML/自定义 Markdown 语法不在此 profile。

**存储配置**：`EVONEXT_WORKSHOP_ROOT` 必须是服务端配置的绝对目录，配合 `EVONEXT_WORKSHOP_OWNER`。API/Worker 同主机共享，FileLock 不作为分布式锁。操作员取 `EVONEXT_REVIEW_OPERATOR_ID`，共享 API Key 不代表已认证的个人身份。模型请求/结果沿用 PG ledger；同 operation_id 固定请求、策略、输入和生效模型配置。已收到响应可复用，sending/unknown 必须核对，不生成新 ID 偷偷重跑。

手工请求示例（来源 hash 必须换成已导入的合成/授权快照）：

```json
{
  "skill_id": "check-target",
  "base_revision": null,
  "files": {
    "SKILL.md": "---\nname: check-target\ndescription: Check a GUI target before acting\n---\nVerify the visible label before tapping. Stop if ambiguous.\n"
  },
  "source_snapshots": ["<snapshot-sha256>"],
  "reason": "A reusable target check supported by the selected source"
}
```

```text
evonext workshop-api draft --file <draft.json>
evonext workshop-api show --id <draft-id>
evonext workshop-api review --id <draft-id> --file <review.json>
evonext workshop-api commit --id <draft-id>
evonext workshop-api list
```

`review.json` 为 `{"verdict":"approved","notes":"具体复核依据"}`；也可使用 `rejected`、`needs_evidence`。API 前缀 `/api/v1/workshop`；`/drafts/{id}/discard` 丢弃，历史仍保留。既有 `workshop save` 是兼容的本地直接候选编辑命令，不生成模型复核证明；新的自动生成链只走草稿。

模型请求：

```json
{
  "operation_id": "<stable-operation-id>",
  "skill_id": "check-target",
  "base_revision": null,
  "mode": "learn",
  "sources": [{"snapshot_id":"<snapshot-sha256>","positions":[0,1]}],
  "cases": [],
  "instruction": "Sharpen the target-check rule using these observations.",
  "include_images": false
}
```

`mode` 可为 `diet`。最多 4 个快照、每个 12 个步骤、共 4 张已绑定截图；总请求仍受 gateway 字节预算限制，不静默截断。可选 `cases` 条目为 `{"case_id":"<id>","revision":1}`。`preview/author/status` 分别使用 `workshop-api preview --file`、`workshop-api author --file`、`workshop-api status --id`；HTTP 对应 `/preview`、`/operations`、`/operations/{id}`。图片附在输入中不证明模型阅读或执行收益。

本片停止于可审查候选闭环；不扩展后台自主学习、自动归档/激活、Skill 商店、通用插件系统、merge/group undo 或真实设备执行。真实学习质量、截图复核能力和 none/raw/skill 收益保留 AX-12 独立验收。

### 2026-11-14 · 选图、预算预览与定向修补

每个 SourceWindow 可显式提供 `image_positions`，必须是 `positions` 的子集；总共最多附 4 张图，文本窗口仍可保留每源 12 步。`include_images=false` 时不能提供非空图片选择。`image_positions=[]` 明确不附图，省略/null 则保留旧的“所选步骤中所有已绑定图”语义，超图数仍拒绝，不静默截断。工作台提供单独的图片步骤输入框；CLI 的请求 JSON 与 HTTP 共用该合同。

`/preview` 同时读取固定基线、Case 审核引用和选定证据，返回 `initial_request_bytes`、`max_request_bytes`、`input_budget_exceeded`、`model_configured`。字节数使用与网关相同的请求序列化合同；未配置模型时显示的是空模型名的预览，配置后须重新预览。该估计仅覆盖首轮作者输入，复核和修补含新生成内容，仍在每次 gateway admission 前校验预算。HTTP 提交在初始请求超限时拒绝入队且不新增操作回执；增大预算必须明确配置，不压缩或改写源图。

修补请求分开携带 `original`（不可变基线）、`previous_proposal`（被驳回的完整文件/精简标题和原因）、`repair_feedback`。新建时基线为空不代表被驳回稿不存在。策略和请求均冻结并核 hash，仍最多修补一次，旧草稿及复核不覆写。

`gpt-6.1-sol` 及其日期版本通过 gateway 使用 `max_completion_tokens`；其他既有模型保留当前参数合同。实际 wire payload 参与收费回执身份，不自动重发 sending/unknown，也不把参数兼容当作语义质量验收。

## 10. 标准学习闭环：相关经验召回、按需取证与短指南（目标规格）

2026-11-14 用户增补：把手工选来源、截图和编写提示改为可重复的学习流程；兼顾手机任务结束后的即时总结与空闲期整理。以下是待实现合同，不把 §9 的显式 authoring 宣称为自主学习。本节细化当前 ROADMAP 的能力演进门槛，不增加第二条全局路线。

### 10.1 OpenClaw 的实际机制与本项目取舍

2026-11-14 核对上游官方 [Self-learning](https://docs.openclaw.ai/tools/self-learning)、[Workshop](https://docs.openclaw.ai/tools/skill-workshop)、[Dreaming](https://docs.openclaw.ai/concepts/dreaming)。实现复查基线仍固定为 `bd0557f4fac019b945905facd9211ae726210647`；后续实现须按实际采用的源码版本复核配置，在线文档不作为永久不变的默认值。

- Self-learning 的 64 是单次近期摘录的 **transcript events 上限**，不是召回 64 个相关 session；上游同时限制摘录字节，并为缺失内容保留省略说明。
- Workshop 借鉴先查已有方法、补丁优先、无增量则不变更、版本与 Undo、运行中固定快照；保留其 propose 思路，不继承“写入即生效”的默认策略。
- Dreaming 是 Memory 的后台整理，不等同于 Workshop learner。借鉴“短期信号 → 汇总 → 有据沉淀”的分工，不复制睡眠阶段名或新增通用编排系统。

对应本项目：轨迹结束事件、手工学习、空闲扫描使用同一学习用例；操作方法送 Workshop，用户事实/偏好交给已有 Memory owner，工具/环境问题送原问题域。一次输入可得出“不值得学习”或“需补证”，不强制产 Skill。

### 10.2 一条流程，三个触发入口

```text
手机任务结束 / 手工指定案例 / 空闲期扫描
→ 固定新证据与消费反馈 → 判断是否有持久知识增量
→ 找相关任务族与已有 Skill → 选 4–8 条相关来源
→ 保留上下文的轨迹窗口 → 按需读截图与回执
→ 对照成功、失败、unknown，提出可复用规则
→ Patch / Create / No Change / Needs Evidence
→ 完整复核、最多一次修补 → 固定候选版本
→ 独立试验与限定采用 → 其他模块消费精确版本 → 新反馈
```

“每轮”首期指一次完整任务/Trial 收尾，不是每个点击。任务完成后先生成轻量事实摘要，记录实际终止原因、输出快照、已消费 Skill revision、异常位置和缺证；它不是新 Outcome 判决。只有确认方法纠正、重复绕路、入口发现、已用 Skill 失效等增量信号，才申请一次有预算的学习。失败/unknown 也可以学避坑；不能无依据学成成功路径。

| 入口 | 作用 | 与其他入口的关系 |
|---|---|---|
| 手工指定案例 | 操作者指定任务族/来源，复现与调试全流程 | 不手工填写正确答案充当自主学习成果 |
| 任务收尾 | 收到冻结执行输出后登记一次学习信号，后台处理，不阻塞手机交接 | 同一次来源/Skill revision/策略身份重复通知复用结果 |
| 空闲整理 | 合并待处理信号、查重复/冲突、修补或精简既有候选 | 读取尚未处理或有新证据的信号；不从自己生成的摘要递归制造新学习事件 |

复用现有 Celery/Worker 和 PG 操作回执，不新增 scheduler 或自动化平台；本节不是创建定时任务的配置。运行中 Skill 固定，空闲更新只影响后续候选选择。在途设备操作由 Runtime 管，不因后台归纳重跑任务。

### 10.3 召回 4–8 条：先保证相关与独立，再控制数量

以新任务的目标/子目标、App、页面上下文和问题症状召回候选，再查来源权限、用途、版本、证据覆盖与相关性。优先使用既有搜索及元数据；有测量证明召回成为瓶颈后才加复杂检索。

默认选 4 条，上限 8 条是首期工程预算，不是成功质量标准。库存不足就用实际数量并说明缺口，不重复采样凑数；当前李子柒只找到两条，只能作两条来源的示范。允许先从较大候选摘要列表筛选，但不得把所有全文和图片塞进首轮请求。

- 相同任务的 retry、重复上传、不同修订按 lineage 关联，保留具体差异，不计多个独立支持案例。
- 有条件时兼顾成功、失败、相似但不适用的反例；unknown 单列。成功/失败标签是来源判断，附其判据/复核版本，不能代替状态证据，也不强制 1:1 配比。
- 同族不同起态、App 版本、语言、账号状态、额外提示注入分别标记。遇到冲突先收窄规则或补证；更多重复正例不能抹平关键反例。
- 既有 Skill 的目标/触发条件召回与任务来源召回分开。先读取最相关的 0–1 个已有精确 revision，决定修补、新建或不变更；不以账号人名给每个实例建一份 Skill。
- 留出确认集不进入 learner/reviewer；一旦被用于调试或修补，就按暴露材料重新标记。展示用人审摘要与自主学习输入分开记录。

本节目标最多 8 条来源；当前 `AuthorRequest` 实际只支持 4 个快照、每个 12 步。后续切片必须显式调整这些合同及引用上限，不能通过分批偷偷扩大一次操作的累计预算。

### 10.4 切轨迹是保留决策上下文，图像是可请求证据

第一层读取整条轨迹的轻量文本索引：原用户目标、来源版本、步骤身份与位置、动作描述、实际 dispatch/回执、可用图片索引、异常/缺证及后续观察关联。执行者的 think/原始回答保留为提案或自述，不升级成事实。来源中的人审/纠错建议单列，不能伪装成当时执行者看到的上下文。

第二层按相关子流程选择连续 span，至少保留入口前态、关键决策、动作、后态/失败/恢复或结果缺口。长等待/相同重试可生成有界摘要，但保留原引用和省略说明。先给索引再按需展开原文，不统一取头 12 步、尾 12 步，也不拼接不同 Trial 形成一条“成功轨迹”。文本预算不够时明确缩小任务范围或停下，不能静默丢掉关键反证。

作者和复核者可以向 Evidence 读取用例发出有界请求，至少包含冻结 snapshot、源 position/evidence_ref、所需类型和用途，例如“确认点击后是否展开排序菜单”。只允许读取本轮已选来源，不能任意抓 URL、查询其他人的资料或操作手机。

优先读取：页面身份/入口歧义、控件状态切换、排序前后、分歧点、错误恢复和完成判据相关图片。action 的描述用于发现“该看哪里”，不证明动作正确或成功。必要时看前后态配对；只有动作前图时仍报告后态缺证。

首期建议默认首轮不附图，共享上限 4 张、最多 2 次取证轮、最多 6 次模型调用（包含取证请求、作者、复核和一次修补），以先到的字节/Token/费用/时间限制停止；这些是待验证初值。复核与作者共用累计预算和已交付图片缓存，不重复收费获取同一图。图片读取权限、实际 hash、模型送达与结论引用分别记录；下载存在不代表模型已看，模型已看不代表结论成立。

原始图不改写。需要派生视图时显式标示变换、源 hash 与派生 hash，并固定模型实际消费版本；不得为绕过预算偷偷压图。所有模型调用仍走 gateway 与持久 PG 回执，unknown 先核对。

### 10.5 产物是一份短指南与按需参考材料

Workshop 是编写系统，其他模块消费的产物是冻结 `SkillBundle`，不是 Workshop 内部状态。运行时正文只保留：**何时用、需要什么、如何做、关键陷阱、何时停、怎样确认完成**。

正文首期以约 300–800 中文字/不超过约 1000 Token 为编辑目标，不做越短越好的硬认证。复杂任务可例外说明。单一意图和状态边界优先于字数；不能为减长删除影响动作选择的条件，也不能把每个来源步骤改写成一条规则。

| 位置 | 内容 | 消费时机 |
|---|---|---|
| description + SKILL.md | 触发条件、参数、短流程、必要的分支/停止检查 | 命中且适用后读取 |
| references/ | 特定页面差异、罕见恢复步骤、失败反例和来源对照 | 正文在相关动作前明确链接；不默认注入全文 |
| 候选/采用/来源回执 | hash、revision、权限、费用、审核/采用状态、证据覆盖和 do_not_train | 宿主/Review/治理读取；不在每一步反复写进操作正文 |

通用的账号权限、调用预算、重试授权、训练限制由 owner 合同管理；正文保留真正影响该方法的特定风险，例如已点赞不要取消、评论结果未知不要重发。更详细的审计不等于更好的操作指南。精简必须比较全部原规则；被移动规则在触发条件出现时必须能在动作前找到，不得靠 references 隐藏关键限制。

不把 `generation outcome=approved` 写成 `verified`。方法内容、证据审查和采用决定分开；正文短不代表功能已验证。

### 10.6 每次更新都针对知识增量，避免越用越长

一次 run 的总结先回答：沿用了哪份方法、哪个前提被证实/推翻、哪一步多走或失败、需要新增什么可迁移知识。只记录必要事实和引用，不默认生成完整 Skill。

后台按相同任务族和固定候选归并信号，先 view 再 patch。没有新知识就 No Change；证据冲突或缺失就 Needs Evidence；有新增触发分支或状态检查才修补。反复失败首先分辨召回、适用性、内容、工具、环境或未消费，而不是继续加禁止条款。

每轮只提出一个明确目的的修改，保留 base revision、完整提案与反馈、来源和父版本。输出 diff 与一句变更理由；重叠即时/空闲学习在提交时走既有 CAS，冲突刷新并重新提案，不覆盖在途版本。累计预算跨尝试，不靠新 operation_id 规避。

独立采用后，消费者记录是否选择、拒绝、实际送达、引用了哪些参考内容，以及对应新 Trial。后续效果评估据新证据作比较；候选可以撤回、缩小范围或淘汰。自动写草稿可以早做，自动执行/采用仍需独立门槛。

### 10.7 首期交付与验收

先交付“手工选一个任务族 → 自动召回/选窗/按需看图 → 短指南或已有 Skill patch → 草稿读回”；在固定样本验证该链路后，再连接任务结束事件与空闲扫描。两种触发的身份/预算/去重从首片设计，实际后台运行属于后续 Gate，不反过来以后台规模阻塞第一片。

| 验收点 | 必须观察到的行为 |
|---|---|
| 相关来源与完整分母 | 返回实际 4–8 条或不足原因；重复 lineage 不充数；成功/失败/unknown 与来源证据分开 |
| 无手工正确答案 | 记录模型看到的输入与人工干预；人工补提示单列 assisted，不算自主学习成绩 |
| 自主取证 | 至少一个关键页由作者或复核主动请求；也有不需图片的任务；缺图/越界/超预算正确停止 |
| 来源和语义 | 无点赞量=播放量等无据等同；建议、操作、自报完成、人审和观察分开；冲突可返回不变更/补证 |
| 短且可用 | 核心流程可读、必要条件未弱化、关键参考在动作前可发现；报告正文 Token 和实际加载参考 Token |
| 渐进更新 | 新证据修补既有 revision；重复事件不重复产稿；一次修补后停止；旧版本可读回 |
| 双触发一致 | 手工、收尾、空闲输入同一信号时复用/关联回执；学习结果不再触发自己；前台运行快照不变 |
| 消费与收益 | API/CLI/Workbench 同一候选；其他模块只消费合同；固定 None/Raw/Skill 对照、新任务收益与负迁移另验 |

上游依据：[固定版本经验复核](https://github.com/openclaw/openclaw/blob/bd0557f4fac019b945905facd9211ae726210647/extensions/skill-workshop/src/experience-review.ts)、[固定版本复核 Prompt](https://github.com/openclaw/openclaw/blob/bd0557f4fac019b945905facd9211ae726210647/extensions/skill-workshop/src/experience-review-prompt.ts)。本节不复制上游源码或其完整产品。

### 10.8 手工触发首片的现役合同

`POST /api/v1/workshop/learning/preview` 只读规划；`POST /api/v1/workshop/learning/operations` 冻结并提交，后者要求已配置 operator、模型开关和 PG。请求为 `operation_id`、`topic` 或 `seed_snapshot_id`、可选 `skill_id`、`source_limit`（默认 4，允许 1–8；不足不补重复来源）。CLI `workshop-api learning-preview/learn` 与工作台“从相关经验学习”消费相同用例；状态仍由既有 `/workshop/operations/{operation_id}` 读回，队列复用 `evonext.workshop`。没有第二套学习状态库或调度器。

本片只检索 Evidence 已注册工作区，按稳定快照 ID 顺序扫描最多 200 个条目，返回截断标志和后续 cursor；不是“最近 200 条”或全库语义搜索。用中英文词项重合筛相关候选，按来源标签补足对照；标签明确为未独立核验的来源提示。排除 sidecar 显式声明的 test/holdout/heldout/confirmation、revoked/restricted 以及空轨迹。同 Task 的版本只取一个；同 lineage 可保留一对不同标签的对照，另报 `independent_family_count`，不将它们当独立案例。缺少 lineage 元数据时只能按 Task ID 去重；该边界不是完整的来源许可或污染审查实现。

选窗使用动作描述中的主题词项，在单条轨迹内按出现频率降低重复账号名的权重，围绕相关邻域保留最多 12 个连续源 position。返回遗漏位置，不能拼接为未执行的连续成功链。原始 JSON、媒体字节和 source revision 不变。现有 Skill 通过名称/description 词项发现，唯一明确匹配固定 base revision；接近匹配有歧义则拒绝并要求指定 ID。相关性不等于适用性，作者仍可 No Change / Needs Evidence。当前支持 create/patch，不实现自动 merge。

首轮无图片，提供本轮窗口内的绑定图片 inventory。作者/复核可按策略返回严格 JSON `{"read_evidence":[{"evidence_ref":"snapshot:position","reason":"需确认的状态"}]}`；只能读取该窗口的已绑定图片。每次校验源 hash，图片字节在本次运行内共用缓存；不同模型请求仍可能计费。共享上限为 4 张、2 次读取轮、6 次模型调用、一次修补，每次发送前检查字节预算及 180 秒运行截止时间；已发出的请求仍受 gateway 的传输超时控制。缺图/无新增图片、调用/轮次/字节/时间预算耗尽返回 needs_evidence；越界引用拒绝。事件区分 loaded 和实际响应收到后的 delivered，结果列出图片引用、调用数和正文字符数。未实现正文/参考材料的实际消费者 Token 统计或硬长度认证。

同一 operation_id 恢复读取原先冻结的来源、base、策略和请求；不重新召回。收费响应仍先落 PG 再解析，sending/unknown 不重发。预览本身不锁定来源；提交时的 PG 回执是本轮正式输入。模型审查只形成草稿，沿用显式候选提交、CAS 与冻结导出；不改变执行/评估/采用/训练权威。

任务收尾、空闲扫描、共享事件去重及实际消费收益均未在本片启用。§10.7 的目标验收仍保留，当前证据以 ACCEPTANCE 为准。

### 2026-11-14 · 补齐模型 JPEG 消费视图

§10.8 的按需图片读取现使用共享 JPEG 视图，默认 quality 98，可受信配置为 90，均为无色度抽样、32px 对齐与最多 980 patch。该参数由宿主配置、在提交时冻结，不由模型/上传内容提供，也不因预算不足自动降低。源图与 JPEG 派生图分别核 hash、记录尺寸/字节和实际编码版本，预览展示当前策略。Workshop 的首轮显式选图与后续按需取图、Evaluation 的 Judge 与 Investigator 使用同一转换；历史冻结 profile 保持原路径。精确参数、旧版本处理与限制统一见 [COMPATIBILITY §10](../COMPATIBILITY.md#10-模型图片消费视图)。

本补齐不接通任务收尾/空闲事件，不重发已有 unknown 收费请求；也不将旧的原 PNG 语义评估结果自动归属新 JPEG 输入。
