# 08 · Skill Workshop、Runtime 与处理闭环

本文件维护模块合同；交付顺位统一见 [当前路线图 R0–R5](../ROADMAP.md#r0r5按证据门槛推进)。先证明固定指南的独立执行与迁移收益，再推进下文的自动学习/选择能力；本文“后续工作包”不表示可绕过该门槛。

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
