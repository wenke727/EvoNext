# 06 · 行为验收、故障演练与发布 Gate

> 修订：2026-11-06 / 0.2。保留原全量需求与验收编号；这是目标合同，不是已实现清单。当前交付见 [实施状态](../ACCEPTANCE.md)，目录与存储以 [03](03_ARCHITECTURE.md) 为准。

**三套证据不能混淆**：① schema/unit/fixture/容错证明**工程合同**；② 允许使用的真实轨迹+独立 Gold 证明**语义质量**；③ 目标环境真实 API/Worker/数据/媒体/权限/回滚证明**生产可替换性**。一项完成只代表对应 Gate，不自动继承其余 Gate。

## 1. 测试层与运行原则

| 层级 | 验什么 | 正确证据 |
|---|---|---|
| S0 静态/合同 | Schema、字段/ID、hash、样例 JSON、输入/输出/来源范围、枚举 | 自动化 schema 检查和独立跨对象断言 |
| S1 纯领域 | 状态机、对象版本、requested checks、Case/审阅、Snapshot、权限决策 | 使用 synthetic 夹具、可控时钟/ID/假模型 |
| S2 集成 | 真 PG 或选定 DB、S3 object store、真实 Broker/Worker、Job 恢复、幂等与审计 | 容器真实联通、故障注入、已封存 readback |
| S3 浏览器 | React 用户连续操作、长轨迹/截图、草稿/冲突、固定版本和导航 | 浏览器实际操作、waterfall、200/2000 步计量 |
| S4 独立语义 | Outcome/Step/Diagnosis/Skill/Recovery 的真实质量 | 冻结来源，独立 reviewer Gold、blind eval、同源 paired、预算完整 |
| S5 迁移/生产 | 存量迁移、增量 watermark、消费者切换、ACL/恢复/回退 | 计数/hash/场景对账、canary、单写签署与运维演练 |

测试使用固定随机种子、可计数假 provider、进程 kill、网络失败注入；正式模型请求/设备/生产数据写入需另行授权和预算。不能为了合成 fixture 全通过就把真实模型准确率/成本填成已验证。

## 2. P0：来源、版本、媒体、界面

| ID | 输入/故障 | 期望的可观察行为 |
|---|---|---|
| AC-001 | 单轨迹带 instruction/task_id/步骤/媒体上传 | raw receipt、稳定来源/hash、TaskRevision、按来源顺序可查看步骤与媒体 |
| AC-002 | 超出 JS 安全整数的数字样式 task_id | JSON 与 UI 一律按字符串完整显示，不截断、不用数字索引 |
| AC-003 | 同一 Idempotency-Key+同一内容并发/重复提交 | 返回原 receipt，不重复 TaskRevision/媒体统计；批量也不双计 |
| AC-004 | 同一 Key 但内容不同 | 409 与原身份/冲突原因；不得静默 overwrite |
| AC-005 | source_key 相同但来源 revision/hash 变化 | 按已声明 source conflict 策略生成显式修订或拒绝；raw 永不可被覆写 |
| AC-006 | JSON+multipart、批次 manifest、CLI 的语义等价输入 | 归一到相同内容合同与来源身份；没有一条 CLI 私有绕过验证的写路径 |
| AC-007 | 媒体上传成功但 DB 失败；DB accepted 后媒体缺失 | Job `needs_reconcile` 或明确失败，补扫/核对不伪造成功；孤儿对象可管理 |
| AC-008 | 损坏 PNG、缺图片、1×1 占位、过期 URL | available/readable/delivered 与失败原因分别准确；模型没有实际接收不得引用作结论 |
| AC-009 | 输入同时含 raw v0、自动补字段 v1、人审提交 v2 | 三版本可读；**v1 不因版本号大于 0 自动 reviewed**；人审记录附 actor/review rev |
| AC-010 | latest 指向 v2，打开固定 v0，随后修改 v2 | v0 始终原样可读；不会把 latest 数据/图像/判断塞回历史版本 |
| AC-011 | 非连续 step_id + 2000 步完整轨迹 | source IDs/ordinal 正确保留；列表/单步按需分页，不读取全部媒体；跳步准确 |
| AC-012 | 第 n 步为动作前图，下一步有后态；缺 dispatch 或后继 | UI 明确 frame_relation/action receipt；不会仅凭相邻帧将动作判 executed/effective |
| AC-013 | 用户中途修改目标/取消，模型已提出旧计划 | 有效改令与终止边界保留在 TaskContract，不能按原始 instruction 的单一目标评分 |
| AC-014 | 两个 Task/版本快速切换、滚动、刷新 | 旧请求数据不显示在新任务；未提交人审草稿有保护；Case 返回正确 version/step |
| AC-015 | 图片缩放/旋转、bbox 编辑/修正 | 依原始截图大小正确换算坐标，数据与截图绑定同版本，不发生缩略图坐标漂移 |

## 3. P0：Review、Case、治理

| ID | 输入/故障 | 期望的可观察行为 |
|---|---|---|
| AC-016 | 自动 machine patch 后进行 review | 机器 patch 不变人工审核 authority；人审后存 ReviewRevision 而非覆盖 Record |
| AC-017 | reviewer A 打开 v3，reviewer B 先保存，A 再保存 | 返回 412 或明确冲突，不丢 B 的改动；A 可以查看差异并基于新 revision 重试 |
| AC-018 | 客户端伪造 reviewer/admin/HUMAN_REVIEW header/body | 服务端从可信会话/权限绑定 actor；伪造不提高 authority |
| AC-019 | 使用 Playground/Task 修订待审核内容后提交 | 可生成/关联原 Case，一条问题的 review、membership、failure facet 不复制第二个 Case |
| AC-020 | Case 审核完成但未加入 bad_case | 仅 review approved；不自动入数据池或启动 failure lifecycle/训练 |
| AC-021 | Case review 后明确加入 regression | 保存用途、suite/gold 来源与 reviewer；其原 task/version 可定位，检测跨训练集冲突 |
| AC-022 | Reviewed Case 改变 first-error/locator step 后 | locator revision 递增；旧验证与 regression guard 标 stale/失效，不自动视为仍通过 |
| AC-023 | 归因未知/多因、风险环境阻断、错误标签 | 可以记录 unknown/data/environment/safety 并进入补证/对应 owner，不强迫 weight/skill |
| AC-024 | 关闭的 Case 发生新回归失败 | 有 reopen/revision/新证据，旧审核/验证仍可追溯，不能直接覆盖历史原因 |
| AC-025 | contamination=unchecked、同 family 在 train 与 unseen | 保持 unchecked/阻止正式不兼容准入，报告碰撞；不把 unknown 假装 clean |
| AC-026 | 数据质量 hard error 而 Agent 可能成功 | quality 和 outcome 两独立维度；不因图片坏或 schema 缺失给 GUI failed |

## 4. P0：Evaluation、异步作业与结果

| ID | 输入/故障 | 期望的可观察行为 |
|---|---|---|
| AC-027 | 有动作回执+可证实新鲜后态且全部必需义务满足 | Outcome success、每个 check 指正确 evidence；不由 terminate(success) 单独推断 |
| AC-028 | 只有 `terminate(success)`，无有效后态/对象确认 | unknown/not_assessed 及缺证原因，不能被计算为确认的 success |
| AC-029 | 选错对象但其他动作成功、目标范围必须全局比较 | 错对象的必需约束 fail；缺全局比较为 unknown，不用首屏/点赞数代替播放量 |
| AC-030 | 用户要求付款前停，停止动作符合冻结合同 | 依实际约束判断 pass/unknown，不因未付款自动 fail |
| AC-031 | provider timeout/429/invalid JSON | Record/Attempt 技术 error/partial；不计 GUI fail/environment error；Run 完整分母 |
| AC-032 | 同 Run 12 Request，其中 pass/fail/unknown/not_applicable/未评/错误 | `requested = pass+fail+unknown+NA+not_assessed` 按固定 check 计；任务数与 checks 数不混 |
| AC-033 | 重复消息、Worker 并发抢占同 request | 只有一个有效 lease/采用的 Record；可保留其它迟到 Attempt 但不双计/覆写 |
| AC-034 | worker 在发布前/模型返回后/结果事务提交后强杀 | 按持久状态恢复；已封存不重跑；未知模型调用可解释、重试有界 |
| AC-035 | Record 已封存，更新 Task/latest 投影失败 | Record 可查；只重试投影而不再付费评分，旧版结果不能覆盖新版 |
| AC-036 | 新 source revision 已评分，旧 run/lease 迟到 | 旧来源只在历史显示，不能变 latest 的当前结果，hash 校验正确 |
| AC-037 | 技术 retry/cancel 进行中和已完成的混合请求 | 新 attempt 不改原 Record；取消停止后续领取，保留费用和所有未完成项 |
| AC-038 | 评分模型/Prompt/Policy alias 随部署变化 | Run 的 effective config 冻结；actual provider revision 与 declared 不符时 unverified/mismatch |
| AC-039 | 人审答案、旧 judge verdict/Gold sentinel 混在 metadata/step/user notes | 独立 judge 最终可见 payload 不含 sentinel；合法原始用户改令仍在 |
| AC-040 | Step ex-ante 判决含未来帧/Outcome sentinel | Provider 输入不含目标步后的证据；retrospective 结果不能冒充 decision-time label |
| AC-041 | 指定图片索引但图像未送达/解码失败、越界 ID | 该证据不能支持 pass/fail；交付回执与可见范围完整记录 |
| AC-042 | 1000/10000 请求矩阵、多 grader 共享相同冻结输入 | 按引用读取，无逐 Request 深复制大轨迹；控制数据增长近线性，性能报告有实测证据 |

## 5. P0/P1：Snapshot、正式导出、外部消费

| ID | 输入/故障 | 期望的可观察行为 | Gate |
|---|---|---|---|
| AC-043 | 动态 Query 选 30 个任务后创建 sealed Snapshot，再修改 tags/latest | 旧 Snapshot 固定成员、来源修订、label refs 与内容 hash 不变化 | P0 |
| AC-044 | 将 Snapshot 拷贝目录、媒体改 URL 但字节不变 | 逻辑 manifest 不变；某个图片字节变化须校验失败或生成新 revision | P0 |
| AC-045 | 同 family/near-duplicate 分布在 train/dev/unseen | 受控 split 分组/污染审计并拒绝不合法正式发布；unknown 不认证 unseen | P0 |
| AC-046 | 某候选无 human/judge label provenance、缺必要 image | 进入 quarantine，计数与理由写 membership；不能进入 train.jsonl | P0 |
| AC-047 | 正式 publisher 输出 train/dev/quarantine/membership/manifest | 所有文件 hash/计数正确；由 canonical manifest 消费，不扫描任意 JSONL 目录 | P0 |
| AC-048 | 删除/匿名化已到保留期的敏感 raw 内容 | 权限/法律策略允许时可删除或脱敏；引用变不可用且有最小删除回执，不偷偷返回其它内容 | P0 |
| AC-049 | Trainer/Benchmark/外部 Runtime 提交过期/未知/重复/异内容回执 | 验证 owner/scope/source/candidate/trial hash，幂等/冲突/unknown 清楚，不能伪造训练完成 | P1 |

## 6. P1：Diagnosis、Skill、Recovery、实验与回归

| ID | 输入/故障 | 期望的可观察行为 |
|---|---|---|
| AC-050 | 一条真实失败只有无效点击回执且后态缺失 | Diagnosis 给最早有证据支持的 step/range 或 unknown，不凭生成想象首错 |
| AC-051 | 提出干预但源证据缺失或 Case 未审核 | 候选 owner 返回 needs_evidence/rejected，不允许直接触发 Skill/训练/设备执行 |
| AC-052 | tool/environment/rule/data/weight 多种修复路径 | Reviewed allocation 的 route 与 cause 分开；默认优先消除有证据的系统缺陷，不强迫 weight |
| AC-053 | Skill Workshop 作者生成候选且自评为通过 | 保留候选证据与作者身份，不产生独立 reviewer/adoption/发布权限 |
| AC-054 | 同一任务 none / raw / skill 三臂并行/配对 | 固定任务与环境条件，记录真实消费 hash、延迟/费用/安全/Outcome；未运行臂列 missing |
| AC-055 | Skill 匹配了某条已成功历史轨迹但没有在新设备 replay | 只报告来源支持与候选相关，不报告新的任务成功 |
| AC-056 | 原错误时设备处于页面 A，当前设备无法证明恢复到 A | Runtime 明确 blocked/not-equivalent，新建 trial 或停止，不静态拼接旧轨迹 suffix |
| AC-057 | Teacher 纠正错误 Step 并在设备继续实际执行 | 新 agent_trial_id、起态/恢复回执、真正动作证据，后续独立 Eval，原 task/Record 不变 |
| AC-058 | Teacher 只给文本正确动作建议、未真实执行 | 记录 proposed candidate；不得计入成功 trial/恢复收益 |
| AC-059 | baseline/candidate 一部分改善、一部分退化、错误/缺失 | 展示完整配对/未配对数、原分母和未知、成本，不能只报胜出的子集 |
| AC-060 | candidate 质量无净增益或多轮无新增证据 | 合法输出 `NO_GAIN/HOLD/STOP`；不因此强行增加 Graph/新训练/额外付费调用 |
| AC-061 | 原实验开发集曾用于调 Prompt，随后称 unseen 验收 | 追踪 exposure/leakage，不能将 exposed Dev 重新认证为 unseen |
| AC-062 | 模型 A 只重复 judge、多次 cache 命中，模型 B 实际多次 rollout | 只对后者计 Agent trials；judge repeats/cache/attempt 另行统计 |
| AC-063 | reviewed Case 经验证且挂回归，后来出现退化 | 保留固定 suite/gold/Case/旧/新 trial 引用，触发 reopen，不自动改写旧通过记录 |

## 7. 安全、权限与数据出站 Gate

| ID | 场景 | 期望 |
|---|---|---|
| SEC-01 | service account 无权访问其他 source 的 Task/图片/Eval Record | API 与媒体签名 endpoint 都拒绝，分页/缓存也不泄露 |
| SEC-02 | 低权限用户伪造 `owner_id/reviewer_id/source_scope` | 服务端忽略伪造身份，403/409，不改变真实对象 |
| SEC-03 | LLM 在轨迹文本/截图里读取“忽略权限、去某 URL” | 证据按数据处理；Agentic evaluator 无未授权网络/文件/设备工具 |
| SEC-04 | 模型请求 budget/时间/图片数耗尽 | 有界结束、技术 partial/unknown 和真实用量，不无限递归 |
| SEC-05 | 密钥/PII/敏感屏幕内容出现在日志/导出路径 | 按规则遮盖/隔离，URL短时授权，不存原始 secret 于模型/数据库 trace |
| SEC-06 | 未授权真实设备 fork 或模型训练/部署请求 | 在明确 owner/permission gate 拒绝，不能以评估请求绕过 |

## 8. 性能与成本验收——先报基线再优化

冻结一套披露的环境：CPU/RAM、DB/MinIO/Redis 版本与部署方式、Worker/provider fake 并发、Task 步数和媒体大小、索引状态、冷/热缓存。初始目标可参考：50 行摘要/状态 API P95 ≤ 500ms；单条 Record 索引（不下载图片）P95 ≤ 1s；带 10 个耗时 Worker 时 API 仍可用。用 1000/10000 Request 矩阵检查进度记录近线性增长；100,000 Record 验证分页。对 2000 步 Task 查明传输字节数、JSON parse、DOM/JS heap 与单步页面响应，避免全部一次性展开。**上述是新系统待验证目标，不是已有跑分，也不是必须套用同一硬件的通用门槛。**

正式模型/真机另报 P50/P95、实际图片 delivered/重传、token/费用（缺失为 null 而不是 0）、不同来源上的任务指标、模型 judge 与人工 Gold 的一致/分歧。请把 `quality=improved` 与 `cost=unknown` 分开，不以便宜的 fake provider 冒充真实推理性能。

## 9. 独立语义验收协议

- 原始需求样本按真实自然流量、benchmark、Dev、训练/示教和未知来源分桶，记录各自分母与采样方式；不得把 dev/tag 命中数当真实需求频率。
- 冻结 TaskContract：目标对象、动作、数量/时点/排序和负向约束（包括用户授权/停止），复杂案例逐项检查，允许 unknown 和多因归因。
- 预先选正例、明确反例、证据缺失例、环境阻断例、工具错误例、恢复成功/失败例；独立 reviewer 在不读取 candidate 预测的条件下出 Gold revision，分歧有明确解决流程。
- Judge 运行时不可接触 Gold、当前样本 reviewer verdict、旧判决 sentinel；如从源截图/自由文本不能排除泄漏，标 exposure unknown 或污染。
- 用相同输入/模型、控制变量和真实送达证据比较 fixed judge、agentic investigation、不同 grader/Skill 方案。报告 false accept / false reject / unknown / coverage、pairing/family 样本数、费用与边际收益。10–20 个案例只能用于发现重大问题，不能证明低误放行率。
- Fork/Recovery 试验由 Runtime 签署实际执行证据和起态等价，不能混淆同轨迹重复评分与多次独立 Agent trial。无正向净收益时应 HOLD，不因实现了流程就宣称自进化成功。

## 10. 发布签署与失败处理

| Gate | 必须有的文件/结果 | 不通过时 |
|---|---|---|
| G0 Spec Ready | `00–07` 一致、synthetic fixtures 解析、不可决定项/ADR 列表、活跃消费者待验表 | 补真实合同，不开始大规模实现 |
| G1 M1 Engineering | P0 合同/DB+object/broker/Worker/browser/重启/权限/2000 step 实测报告 | 保留新实现隔离，不接真实生产 |
| G2 Semantic | 真实允许来源、独立 reviewer、full denominator、误放行/unknown/成本/缺证 | 不宣称质量提升，按最低成本 baseline 再验证 |
| G3 M2 Evolution | reviewed Case → candidate/new trial → independent paired → adoption/STOP 的可审计流程 | HOLD/STOP，不强制有训练结果 |
| G4 Migration | 旧/新合同与数据/媒体/Case/权限/消费者/Job 对账 + 增量水位 | 不迁移未知对象；继续 old owner |
| G5 Cutover | 单写权威、canary、监控、rollback 演练、操作手册和授权人确认 | 暂停流量、只读或回滚到可证明安全的状态 |

任何 `pass` 都须写：运行日期/commit/环境/fixture或生产来源版本、样本数、结果链接、测试人/Reviewer、已知局限。缺真实连接的验收记 `not_run`，不能用旧报告或本地 fake 值补齐。
