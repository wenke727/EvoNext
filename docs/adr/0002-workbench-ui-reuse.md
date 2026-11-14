# ADR-002 · 先迁用旧 workbench 的 React 视图

状态：已实施（2026-11-07）。范围：当前工作树中只读轨迹工作台的前端视图迁用。

**2026-11-14 新决策：本 ADR 的 EvoNext 前端复制方向已被 EvoLoop #495 + 用户后续纠偏取代。** 本文件仅保留当时实施与来源追溯证据，不再作为 EvoNext 长期 UI 架构依据。全部 React/TS/Viewer/Case/Correction/评估交互都迁回 EvoLoop；在 EvoLoop 现役组件基础上回合并差异，验收后删除 EvoNext `web/`。进化算法/领域 use case/API 留在 EvoNext。前端回迁完成前，本仓 UI 只能作临时迁移对照。



## 决策依据

用户明确要求“能不能先抄作业”，此前已指定 EvoLoop 为来源，并确认先迁完整只读浏览体验、写入/审核另接。因此，本切片对原先独立重画旧界面的做法作明确调整：以旧 React 组件、DOM 标记、CSS 和交互为基线，先迁用再改进。这是用户授权的命名前端视图例外，不扩展为复制旧后端、部署配置、真实数据或其他私有模块的授权；未执行提交或发布。

## 实际迁用

- 原 Sidebar、读取 model、Header/标签标记、反馈/评分等只读视图与样式。
- 原 ORM/grader Panel、ExpandableText、只读视图 contracts 和 CSS。
- 原 TimelineLegend、SVG/CSS、TimelineControls 的图标/滑杆与样式；排除旧 DOM createRoot/mount 桥。
- 新框架只在 TaskSidebar、evaluation-view、StepLegend、EvidenceClient 中适配冻结快照、认证、来源与导航，保留已有证据/媒体 owner。此前手写的近似评估/侧栏视图退出，不保留两套活跃实现。

## 必要适配，不借迁用改变业务权威

1. 保留“结果未携带”与“未评估”的区别，缺失/非法判断与 null 分列未判定/不确定；源版本 0 与未知字段保持原样。
2. 原组件步骤链接改由新快照映射；其他任务/版本/快照不跳入当前输入。来源版次一致只作参考定位，不声称字节输入已核对。
3. 原 Sidebar 写入、评论/标签网络控制器未接入。输入只读；新边界明确拒绝写入，不返回成功占位。未配置的旧服务外链不显示为可用入口。
4. JSON 视图通过新客户端带认证读取原字节，凭据不进入 URL。原图/媒体仍经快照 manifest 与既有 AssetStore。
5. 评分不补造 /10 量纲，旧来源检查/反馈不授予本平台人审；指令/Skill 的旧分组仅是读取视图，源 JSON 和导出字节不变。原始结果显示不反转义字面字符。
6. 左栏时间与评估展示接入新框架的本地显示偏好，开关不修改源数据；未接通的来源区域不提供虚假入口。
7. 保留原文本测量与展开交互；仅为新宿主的 border-box/面板缩放补尺寸测量。右侧自写字段 CSS 限定作用域，避免覆盖迁入的原左栏。

## 来源追溯

来源 checkout HEAD 为 `b5f3ba06c9fd5e68b2ff0c7c10c7fe2263ceea59`。迁用来自用户指定的本地工作树，可能包含尚未提交的 React 改动；以下实际文件摘要才是来源依据，不将其全部冒称为 HEAD 文件内容。复制后仅做上述适配与格式化。没有带入历史设计档案或服务配置。

| 来源（EvoLoop 相对路径） | 当前目标 | 来源文件 SHA-256 |
|---|---|---|
| `src/flywheel/web/src/features/task-evaluation/Panel.tsx` | `web/src/workbench/evaluation/Panel.tsx` | `18678a29ac0ec76e5ba15c04ebbda6f96e909c676c51557ea1a55ecfd898c865` |
| `src/flywheel/web/src/features/task-evaluation/ExpandableText.tsx` | `web/src/workbench/evaluation/ExpandableText.tsx` | `e4cdc0495a3620a077fa3204375528a71e91566d18c9a896f9ef379d30ced94b` |
| `src/flywheel/web/src/features/task-evaluation/contracts.ts` | `web/src/workbench/evaluation/contracts.ts` | `01058445ff2ec468eff3bd77f8238787ec87938b336ba12c785bbc6b401d6698` |
| `src/flywheel/web/src/features/task-evaluation/styles.css` | `web/src/workbench/evaluation/styles.css` | `25c49fe52e561e665afe74cdeba53d886aabb8b0b779aa1176250c135c07b3a3` |
| `src/flywheel/web/src/adapters/timeline-legend.css` | `web/src/workbench/timeline/legend.css` | `bd4da746e471079b0152fb1c1d3db8cd44b1530a7a3cabcfda591ca76d16592d` |
| `src/flywheel/web/src/adapters/timeline-legend.tsx` | `web/src/workbench/timeline/Legend.tsx` | `eed15ebe354646d9c404729c0cc6e12fcb0be3831734be18fab1bf65f094b658` |
| `src/flywheel/web/src/adapters/timeline-controls.tsx` | `web/src/workbench/timeline/Controls.tsx` | `0dc51298e3ba7d7c0eb40858769db28fbce309a2c72c01b60cf57c1c35fe3c0f` |
| `src/flywheel/web/src/features/task-sidebar/Sidebar.tsx` | `web/src/workbench/sidebar/Sidebar.tsx` | `463a038dd8d650f431cadf307d6e61908a2f24ac01a38b9da623ec93090fec17` |
| `src/flywheel/web/src/features/task-sidebar/contracts.ts` | `web/src/workbench/sidebar/contracts.ts` | `7da74d229d07bb2f591c6f42d2b6a8fb52d2d0a84ccb25848b69cfa88ef0d0d9` |
| `src/flywheel/web/src/features/task-sidebar/styles.css` | `web/src/workbench/sidebar/styles.css` | `2a4dbaa4b7030ef86b00b307da95c2767ff7ddd30dba25421339d1a602245262` |
| `src/flywheel/web/src/components/EditButton.tsx` | `web/src/workbench/components/EditButton.tsx` | `1cbdf9033df431cf5321897427cf4e72e9d04e2a13a2928b800a551e416c4b25` |
| `src/flywheel/web/src/components/edit-button.css` | `web/src/workbench/components/edit-button.css` | `5e20243e2ab365d3a271f9a36c3e13492462fda97da005398889bb52a7988008` |
| `src/flywheel/web/src/features/tags/styles.css` | `web/src/workbench/sidebar/tags.css` | `cced4817fe7a077733590cdd30d8f0fdadb10cb0438a894bde3baa1aa522faab` |
| `src/flywheel/web/src/features/task-sidebar/model.ts` | `web/src/workbench/sidebar/model.ts` | `67ee2c6ed1d7e2347119c9726dc77acd6e24a902a5c78553b5d47103a006e2e5` |
| `src/flywheel/web/src/features/tags/model.ts` | `web/src/workbench/sidebar/tags.ts` | `f2d4b4f793c5a9c5ebe5e6c2a20634ed3cb0a9a12d0b4edc3cc4f5a1b3ad983e` |
| `src/flywheel/web/src/features/tags/Tags.tsx` | `web/src/workbench/sidebar/ReadOnlyTags.tsx` | `e28db5944daa9e057962d2cd3ca19c58c41338477864d8fa9d8cc4c27f507804` |
| `src/flywheel/static/css/base.css` | `web/src/workbench/sidebar/base.css` | `93ea9f74fd11ef4dfbd5d566e75d7bc80e62069dff130fe76d9e0d17bc027893` |
| `src/flywheel/static/css/task_review_theme.css` | `web/src/workbench/sidebar/base.css` | `e49621c9b4fd5f2228f746e704c4b2ef5a256e31ec72c568bc7e66554fe0e129` |
| `src/flywheel/static/css/workbench_navigator.css` | `web/src/workbench/timeline/controls.css` | `33dec236470464f65f07f2bd266a536e3c8e9561226c5d6e047f682427923373` |
| `src/flywheel/static/icons/timeline-retry.svg` | `web/src/workbench/timeline/retry.svg` | `107b5c08a06ae8b861ead52603787d2cbd4cf75bb7e48aa41f0561db52b9d0dd` |

## 验收边界

实际运行结果记录在 ../ACCEPTANCE.md。当前使用本地 demo 与真实离线包；grader 完整交互用明确合成来源结果验证。没有运行 grader/模型/设备，也没有验证旧服务真实评估结果或生产持久化。

## 重试时间线增补（2026-11-07）

新增 RetryStack 为适配后视图，交互参考旧 adapters/timeline-cards.tsx 的 TimelineStack 和 static/js/components/timeline_presentation.js 的重试分组；不是上述整文件的直接复制。纯分组与导航位置投影放在 evidence/timeline.ts；不迁旧 createRoot/flushSync、全局 renderer、Canvas 调度或 DOM 状态查询。缺图/human 保持独立，来源分页与小图窗口限制展开范围；分组仅改变显示，不写回 source 或授予执行/评估权威。实际验证与限制见 ACCEPTANCE.md。

## 标注迁移增补（2026-11-07）

本轮参考旧 features/step-evidence/bbox-marker.ts 的双层框与 batch-markers.ts 的编号/起点分组语义，采用新共享 SVG 层实现，不复制旧 Canvas host 或坐标编辑器。用户明确将 BBox 默认坐标也改为 0–1000，优先于旧实现的像素约定；读取 UI 保留显式像素选择，不静默转换历史 source。新投影只处理已命名的结构化 profile，未知子项仍可见，无坐标动作不获得猜测坐标，详情参考图不附加当前提案。契约见 COMPATIBILITY.md，当前验收与真实样本覆盖边界见 ACCEPTANCE.md。

## 打点面板增补（2026-11-07）

参考旧 task_trace_panel.js / inspector-layout.tsx 的独立侧面板、页签、步骤联动、Esc/焦点与可调宽度规则，在 evidence/EvidenceInspector.tsx 内以受控 React 实现；不迁旧 DOM 创建、iframe 导航或全局 BackflowEventsModal。当前包内步骤原文和追踪引用形成完整只读浏览切片；真实模块日志仍由 Langfuse 承担，缺失引用不生成虚构链接或新追踪后端。旧 BBox 的兼容治理按用户最新决定后置。实际证据见 ACCEPTANCE.md。
