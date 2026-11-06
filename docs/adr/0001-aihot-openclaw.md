# ADR-001 · 借鉴 AIHOT 与 OpenClaw，不移植另一套产品

决定日期：2026-11-06。AIHOT 基线 `92e4a15dde652613858cc3ff33376a8d1fd38207`，OpenClaw 基线 `27a08daa6169209729093ce53715e435f4fd4595`。本次按公开文档及相关源码边界审查，未运行这两个完整产品，不以其 README 性能或生产描述当本项目验收结果。

## 采用、适配与暂缓

| 机制 | EvoNext 决定 | 本轮状态 |
|---|---|---|
| API/Worker/Web 分工，规则归所属模块 | 模块化单体；app 是装配层，EvidenceService 共用 | 已调整源码 |
| 模板/门槛与程序分离 | policies/gui + 冻结 hash + 严格变量；git 单一编辑源 | 可运行；生产 grader 未校准 |
| 收费调用先登记、响应先保存 | PG sending/received/unknown + bounded budget；未知不自动放行 | 代码/假传输验证；实 PG 待验 |
| 安全开关只控制副作用 | model_calls_enabled 默认关，真实 device 未接入 | 已实现模型开关与授权合同 |
| 页面不调用模型 | 只读接口无网络模型副作用，显式 probe 才调用 | 保持并加架构回归 |
| 采集 cursor、修订、去重 | 失败不推进成功水位；source/revision 作为身份 | 包/固定读取已有；增量采集待做 |
| 一套公开读取口径 | 同一证据用例；未来 CLI/MCP 复用，不另算成功率 | 基础已接；MCP/权限投影待做 |
| 双评分与精选门槛 | 不作为默认；按困难度/风险升级，正确性与优先级分开 | 目标合同，未做双 judge |
| 先召回再判断关系 | 失败模式建议视图，不直接合并 Case 或根因 | 关系模板已给；聚合引擎待做 |
| 人工 override、撤回与缓存有效期 | 人审独立 revision；派生分组不得盖过人工 | 目标合同，尚无人审模块 |
| 开发/留出校准与全分母 | 继承 AC 原合同，按 family/exposure 分组 | 合成合同验证；独立语义待验 |
| 架构边界测试 | 约束依赖与唯一写入/副作用，不限制所有文件名 | 已加测试 |
| SKILL.md + 固定 session snapshot | Skill 一级资产，Runtime 固定 bundle 与 hash | 本地核心已实现 |
| Workshop patch/history/Undo | append-only candidate 与 CAS、归档、可追溯恢复 | 本地核心已实现 |
| OpenClaw 默认学习即生效 | 不采用；候选不自动授权/上线 | 已明确禁止 |
| Runtime 与 provider transport 分开 | runtime 消费合同；providers 负责模型传输/回执 | 已调整源码 |
| 运行中按 session 串行和资源限额 | 外部 Runtime owner 实现租约/并发；框架只固定身份 | 合同，非分布式执行实现 |
| 插件发现、渠道 Gateway、pg-boss | 不复制；保留现有 Celery/Python，按实际需求显式适配 | 不采用 |
| Skill 自动清理/压缩 | 无可靠消费记录不自动归档；不优先建设 diet/curator | 暂缓 |

“全部可借鉴”表示每项有明确去向，不表示全部复制、全部立即实现或已经验收。新闻热度、来源分级、0–100 注意力评分不能替代 GUI 任务义务、训练资格和修复优先级。

## Langfuse 和调用回执

Langfuse 负责观察、Prompt 版本关联和实验显示；PG 调用回执决定是否可以发送以及如何恢复。存一份 response receipt 不是再造 tracing UI。当前策略在 Git，后续可发布到 Langfuse 固定版本；不维护两个可独立修改的生产“最新 Prompt”。

## 许可与内容来源

本轮代码按契约重新编写，没有复制 AIHOT/OpenClaw 源码、品牌或图标。设计引用保留以下来源；以后直接复制受许可源码时需单独保留对应版权/许可证及文件出处，不因“参考架构”默认完成第三方代码引入。项目自身许可证仍由仓库所有者决定。

## 固定源码依据

- AIHOT 架构：https://github.com/KKKKhazix/AIHOT/blob/92e4a15dde652613858cc3ff33376a8d1fd38207/docs/architecture.md
- AIHOT 收费回执：https://github.com/KKKKhazix/AIHOT/blob/92e4a15dde652613858cc3ff33376a8d1fd38207/packages/backend/src/providers/receipts.ts
- AIHOT Prompt 版本：https://github.com/KKKKhazix/AIHOT/blob/92e4a15dde652613858cc3ff33376a8d1fd38207/packages/backend/src/editorial/prompts.ts
- AIHOT 归组与校准：https://github.com/KKKKhazix/AIHOT/blob/92e4a15dde652613858cc3ff33376a8d1fd38207/docs/grouping.md
- AIHOT 边界测试：https://github.com/KKKKhazix/AIHOT/blob/92e4a15dde652613858cc3ff33376a8d1fd38207/tests/architecture.test.ts
- OpenClaw Runtime：https://github.com/openclaw/openclaw/blob/27a08daa6169209729093ce53715e435f4fd4595/docs/agent-runtime-architecture.md
- OpenClaw Workshop：https://github.com/openclaw/openclaw/blob/27a08daa6169209729093ce53715e435f4fd4595/docs/tools/skill-workshop.md
- OpenClaw Agent loop：https://docs.openclaw.ai/concepts/agent-loop
