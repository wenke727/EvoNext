# 实施状态与验收证据

## 阶段收口：只读工作台阶段完成（2026-11-07）

本阶段验收范围冻结为：真实离线数据展示、左栏、来源 ORM/grader、Grid/小图导航、重试折叠、marker、显示设置、快捷键和打点原文检索。范围内浏览闭环已完成，不以完整替代旧平台或完成生产切换表述。提交版本固定本阶段源码与文档；后续能力不自动纳入本次收口。

收口复核：前端 **42 passed**，后端 **117 passed / 4 skipped**；TypeScript/Vite 构建、compileall、Ruff 与 diff 检查通过。浏览器沿用下方各切片的已通过回归证据，本次仅整理收口文档与提交，没有重跑浏览器；4 项跳过继续保留为未验边界，不算通过。既有真实数据与合成样例的证据边界不变。

保留下方“对照旧 React 的 ORM、grader 与图例补全”的逐区域差异表、各切片限制，以及 [兼容合同](COMPATIBILITY.md) 的读取 profile。以下未迁项不阻塞本阶段，也未在本次启动：

| 未迁项 | 当前边界 |
|---|---|
| 真实 Langfuse 联通 | 模块 log 只读取包内来源引用；真实送达、访问与远端内容绑定未验收 |
| 编辑／审核 | 标签、评论、动作修订、人审、Case、保存及冲突闭环另行接入；只读展示不授予写入权威 |
| 治理管道 | 旧 BBox 单位识别／转换等数据治理后置；不增加前端自动迁移或改写来源数据 |
| 其余低频字段与交互 | 运行事件专用图、尚未适配的来源记录／旧提案格式、未确认的色块选择保留为差异；不以静态图例或原文展示冒称已迁移 |
| 旧平台其他工作区与生产替换 | 查询工作区、设备页、批量评估队列不属于本次轨迹详情迁移；真实基础设施、权限／持久化及生产性能等 Gate 继续保留 |

后续投入仅由 [ROADMAP](ROADMAP.md) 维护，需独立明确范围与验收；本阶段到此停止扩展。

## 有序迁移第四块：只读打点面板与来源追踪引用（2026-11-07）

迁入旧打点面板的浏览规则，使用新 React EvidenceInspector：与当前固定快照/步骤联动、打点数据/模块 log 页签、原字段展开、嵌套字段/值搜索、无匹配提示、复制步骤 JSON、上一/下一步、固定来源版本（0 有效）、刷新与关闭。I 开关、Esc 关闭并恢复入口焦点，面板内 Ctrl/Cmd+F 聚焦搜索，页签支持方向键/Home/End；宽度可指针/键盘调整并作为浏览器 UI 偏好保存。桌面为右侧面板、窄屏覆盖展示；不迁旧 DOM host、iframe、全局数据或后端。

模块 log 页签目前是包内追踪引用读取入口，支持当前步/全任务范围、长 trace ID/数值 0、源位置跳转、复制 ID 和引用原文。仅为来源明确提供的 HTTP(S) 链接生成手动入口；不拼接 URL、不自动请求远端，不将包内引用当远端内容已验证。真实 Langfuse 模块日志、运行事件专用图及其他只读字段尚未全部适配，不能把这块浏览迁移报为完整追踪集成。

验证：前端 **42 passed**，TypeScript/Vite 构建、compileall、Ruff、diff 检查通过；pytest **117 passed / 4 skipped**，可选依赖/隔离实库边界仍未验。Chromium 使用真实离线执行回执验证原文与嵌套 execution_result 搜索、缺失追踪状态；明确合成 synthetic-inspector-trace 验证长 ID/版本 0、false/null 保留、页签/范围/源位置导航、URL 拒绝、无匹配、I/Ctrl+F/Esc/焦点恢复、键盘宽度和 390px 边界。浏览时无写请求、外部追踪请求或页面异常，源 JSON 前后字节一致。既有 Sidebar/来源评估/Controls、重试时间线、BBox/批量 marker 和显示设置浏览器回归通过。

截图：忽略的 output/playwright/workbench-inspector-real.png 使用真实离线回执；workbench-inspector-trace-synthetic.png 仅为合成引用演示。现有真实 44 包/465 步未携带 runtime 或步骤追踪引用，未验证真实追踪服务送达/访问，也未调用模型、设备或生产服务。旧 BBox 治理继续按用户要求后置，本轮未改其转换分支或原数据。

## 有序迁移第三块：BBox 与批量动作标注（2026-11-07）

EvidenceImage 统一消费 markers 纯几何投影与独立 EvidenceOverlay；Grid、小图、重试预览、悬停近景、详情及全屏使用同一读取链，不迁旧 Canvas 全局状态或编辑控制器。参考旧 BBox 双层虚线框、batch 顺序编号与相同起点分组的交互；按用户新增确认，BBox 与动作默认均为 0–1000，共用显式未声明/归一化/原图像素选项，不改源坐标或图片。BBox 支持 value.bbox 对象 xywh/数组角点；非法、越界、退化或未声明空间不绘制。独立 BBox 显示开关默认关闭。

批量读取支持 mobile_use 参数与旧直接结构化 action=batch_actions 对象；源子项顺序、未知项、字符串原文和来源路径保留在临时投影。无坐标输入/按键/等待不补造点击；相同几何共用原序号，相同起点但不同终点的拖动箭头保留。多个批次连续编号，嵌套批次不递归猜测。动作明细以可展开摘要展示以减少截图遮挡；原始工具调用和完整步骤仍可读取。详情对照参考图不套用当前步骤提案。

验证：前端 **39 passed**，TypeScript/Vite 构建、compileall、Ruff、diff 检查通过；当前全仓 pytest **117 passed / 4 skipped**，上一切片记录的 DAL 测试失败已不再出现，本轮未修改 DAL。4 个 skip 的可选依赖/隔离实库边界仍未验。Chromium 合成包 synthetic-batch-bbox 验证 0–1000 精确换算、BBox object/array、同点序号、多箭头、无坐标/未知动作、批量明细展开、Grid/小图/全屏/390px 图片与 SVG 边界一致，像素/未声明切换、缺图和无效框拒绝绘制；切换前后源 JSON 原字节相同，无写请求或页面异常。既有真实离线浏览、来源 grader、重试时间线、显示设置浏览器回归通过。

样本边界：目录式真实离线包 44 份/465 步均未携带 value.bbox 或结构化 batch_actions 字段，因此不声称新增两类标注已用真实来源验收；新功能用明确合成包验证。截图在忽略的 output/playwright/workbench-batch-bbox.png 与 workbench-batch-bbox-fullscreen.png，均为合成坐标网格。未知旧动作语法、历史 code、编辑/拖拽框、真实模块追踪仍未接入；未调用付费模型、设备或生产服务，未修改真实来源数据。

## 有序迁移第二块：重试时间线（2026-11-07）

Grid 与小图条共用纯 retryEntries 投影和受控 RetryStack 视图。参考旧 timeline_presentation.js 的明确 step_type=retry 分组与紧随 Agent 截图规则、旧 React TimelineStack 的层叠预览/展开/收起交互；不迁旧 DOM mount、Canvas host 或全局状态。仅折叠有可用绑定截图的连续来源步骤，runtime.retry 或 rejected_model_outputs 不单独构成折叠依据。缺图与 human 步骤始终独立，不将后继 Agent 称为执行成功或已采纳。

支持单组点击/Enter/Space 展开、收起按钮与组内 Esc 收起、全部展开/收起、当前组高亮、组末来源状态边框和组内标记汇总。Grid 的方向键按可见项导航；单步方向键仍逐一访问原步骤。深链接可直接打开折叠内步骤，源 index/step_id 与显示位置保持区分。展开状态在同一快照的 Grid/单步间共享，不保存为证据；刷新后默认折叠。预览至多三张，Grid 每页至多 60 个源步骤、小图窗口至多 21 个；跨页长组分段，窗口内部分组按实际显示范围标记。缺图保持独立和窗口有界是相对旧版的明确适配，避免折叠隐藏缺证或展开一次挂载整条长轨迹。

验证：33 项前端测试、TypeScript/Vite 构建通过，compileall、Ruff、diff 检查通过。Chromium 使用明确命名的 synthetic-retry-timeline（纯合成 72 步/3 张媒体）验证缺图/human 边界、展开收起、焦点、Enter/Esc、Grid 导航、全部切换、分页、组内深链接、marker、390px 布局；切换前后源 JSON 原字节一致，无写请求或页面异常。既有真实离线包与合成 grader 的 Sidebar/Panel/Legend/Controls、JSON、键盘和移动端浏览回归亦通过。2000 步分组与窗口边界由纯投影测试覆盖，未据此声称 2000 张真实图片性能验收。

全仓 pytest 当前为 **114 passed / 4 skipped / 1 failed**。失败为工作树中同期新增 DAL 测试 test_evidence_reads.py::test_mongo_write_result_and_bson_limit_with_official_sdk：测试 BorrowedClient 的 __getitem__ 返回自身，未转发 update_one，repo.put 在调用时抛 AttributeError；单项复核仍失败。本轮未修改 DAL 实现或其测试，不能声明全仓全绿。4 个 skip 的可选依赖/隔离实库边界不变。

截图保留于忽略的 output/playwright/retry-timeline-collapsed.png 和 retry-timeline-expanded.png，明确为合成重试演示。尚未定位用户所指的色块选择交互，不把现有静态图例冒称筛选器；BBox/批量 marker 和模块追踪仍属后续切片。未调用付费模型、设备或生产服务，未修改真实来源数据。

## 有序迁移第一块：显示选项（2026-11-07）

新增独立显示配置投影与设置弹窗，在旧版按类显隐的交互基础上接入现有新框架组件。当前支持任务/采集时间、ORM/grader、Agent、用户跟进、模型原文/此前回复、执行记录/独立回执、Runtime 和完整步骤原文。时间默认隐藏；其他已接入字段默认显示。偏好只保存受支持的布尔开关，在当前浏览器跨任务保留，可恢复默认；旧偏好缺少新增字段时安全补齐显示默认，不写回源证据。没有为尚未适配的 PRM/Reflect/模块 log 增加空开关。

验证：29 项前端测试通过，TypeScript/Vite 构建通过；pytest 103 passed / 4 skipped，compileall、Ruff、diff 检查通过。4 个 skip 的可选依赖/隔离实库边界不变。Chromium 实测显隐、恢复默认、刷新读回、设置弹窗的键盘隔离、Esc 关闭与 390px 可点击入口；切换前后轨迹 JSON 原字节相同，未观察到写请求或页面异常。额外修复移动端隐藏侧栏后 CSS Grid 自动排布导致主栏错列的问题，明确主栏占第三列。

范围：这是第一块显示迁移，不声称旧版完整左栏、全部字段类型、时间线折叠、marker 或真实模块追踪已经接通；后续顺位仅维护在 ROADMAP.md。未调用模型/设备或生产服务。

## 工作台展示职责拆分（2026-11-07）

本轮只整理已迁入的只读展示：从 TrajectoryViewer 提取 StepEvidenceFields 与 StepPreview，字段原文/来源标识/折叠展示独立于导航与截图布局；文本格式化共用 display，悬停预览对同一步仅执行一次读取投影。主组件由 923 行缩减至 786 行；总实现没有以压缩行数为目标，未引入新状态框架、DAL 或旧 DOM host。没有改变数据合同、展示内容或快捷键，也没有补称旧版全部浏览能力已经迁完。

验证：前端既有 27 项测试及 TypeScript/Vite 构建通过；pytest 103 passed / 4 skipped，compileall 与 Ruff 通过。4 个跳过仍属于可选依赖/未配置实库，未作为通过计入。现有 Chromium 回归覆盖迁入的 Sidebar/Panel/ExpandableText/Legend/Controls、滑杆、来源跳转、JSON 视图、键盘与移动端；针对本轮提取额外验证三类证据字段、模型原始输出逐字显示、details 收起后卸载原文、悬停截图及点击打开。完整只读回归未观察到写请求、旧 API 请求或页面异常。

边界：本轮是组件职责优化，未改变界面设计；字段设置、重试图片堆叠、完整 marker 和追踪面板仍待后续切片。没有调用模型、设备或生产服务，未修改真实来源数据。

本页是当前交付事实；`docs/rebuild/` 是全量目标。测试通过不能替代语义质量、目标环境或生产替换签署。

## 直接迁用旧 React 工作台视图（2026-11-07）

用户本轮明确要求“先抄作业”。已按 [ADR-002](adr/0002-workbench-ui-reuse.md) 将原 Sidebar、Panel、ExpandableText、TimelineLegend、TimelineControls、读取模型、CSS/SVG 迁入 `web/src/workbench/`，而非继续重画近似组件。新 EvidenceClient / 固定快照 / 源步骤映射作为薄适配，原 DOM mount 桥与旧网络写入控制器退出。之前“独立实现未复制前端源码”的说明属于历史轮次；本轮命名前端迁用已有用户授权，不涉及旧后端或部署配置。

保留原左栏结构、标签/指令样式、ORM/grader 布局、实际测量的文本展开、原图例 SVG、底栏图标、JSON 视图和缩略图大小 +/-/滑杆。写入按既定阶段保持关闭；未携带结果、未判定、输入来源核对、字节保真和来源审核不继承的保护仍有效。旧评分分母和未知范围不猜测。

Playwright 已在实际迁入组件上验证：真实包的只读指令/结果缺失/动态图例、原滑杆与列数反向关系、单步/Grid/Enter/方向键、侧栏缩放不截断指令；合成来源的文本展开、grader 筛选、源 index 映射、跨版本引用禁跳、未判定、JSON 新标签和 390px 宿主视口。交互期间无旧 `/api/task/` 请求、无写入请求或页面异常。JSON 读取使用新 API，未将凭据放入链接。

最终测试/构建结果以本节交付记录为准：前端 27 项、pytest 103 passed / 4 skipped，compileall、Ruff、TypeScript/Vite 构建通过；4 个 skip 的可选 SDK/隔离实库原因不变。真实 ORM/grader 服务仍不可用，图例/grader 完整数据预览明确为合成，不冒充真实结论。真实包与图片未改写，本地仍为 demo。

## 对照旧 React 的 ORM、grader 与图例补全（2026-11-07）

本轮对照旧前端的 task-sidebar、task-evaluation、timeline-legend、timeline-cards、step-evidence 与布局组件/测试，按可用数据和权威边界重建，不将旧全局 DOM 适配器或私有源码搬入本仓库。此前仅完成布局与基础浏览，不能称为旧 workbench 细节全部齐全。

| 对照区域 | 本轮可用行为 | 边界/未接入 |
|---|---|---|
| 左栏 ORM | 状态原值、provider、判定依据、归因、长文展开、原始结果、来源关联 | 当前 44 个真实包未携带 evaluation/ORM；显示“结果未携带”，不能推断未评估 |
| 专项 grader | 展开/折叠、正确/错误/不确定/未判定计数筛选、理由、版本、原文、步骤引用 | 无真实旧服务；完整交互用明确合成包经 API 验证，未运行 grader |
| 评估来源 | 区分快照绑定、同来源版本参考、其他版本/任务/快照和未知；版本 0 有效 | 同来源版本仅作参考定位，不宣称已核对字节输入；异版/异任务不跳当前步骤 |
| 步骤定位 | 源 index / step_id 唯一映射到显示位置；缺失/重名明确无法定位 | 不把 grader 的源 index 直接当数组下标，不猜未声明 ID |
| 图例与状态 | 当前步骤、来源正确/错误、接管记录/提案、多终止点、跟进、主动操控、重试、Teacher、安全/风控记录、缺图按证据出现 | 徽标、颜色、图例、当前步骤说明共用投影；不以执行 success 代替机器/人工结论，不照搬旧混合推断 |
| 左栏来源上下文 | 有字段才展示采集时间、标签、应用/Skill 引导、来源关系、端侧打点、原始评分、反馈、质检原文 | 不裁剪 Skill 指令后缀，不猜 /10 量纲，不继承来源审核为新平台批准；旧页面外链未配置则不造链接 |
| 单步与双图 | 跟进原文、此前失败模型回复、当前/下一步截图、明确记录后续图、已绑定包内媒体选择 | 下一步图不是回执；不跳缺帧，未绑定历史路径不访问；辅助图不自行获得 before/after 含义 |
| 布局与入口 | 保留旧 workbench 的面板与快捷键；App 与根挂载入口分离，独立组件/纯投影 | 旧查询工作区、设备页、批量评估队列不是轨迹详情已迁移能力 |
| 写入能力 | 本轮只读 | 人审提交、标签编辑、评论写入、版本变更、Case、运行评估等按已确认范围另接，无空成功按钮 |

读取 profile 明确为 `trajectory.evaluation.prediction / graders` 的来源评估视图，不是完整旧 Evaluation API 仿真或新评估存储。合法原始字段及未知内容均原样留存，显示不触发模型、执行或用途授权。逐项缺失/非法 status 单列未判定，null 保留不确定；分母保留全部携带条目。来源版次、输入快照与人工权威保持分离。

验证：**25 项前端测试通过**（含媒体、字段、几何、导航、来源评估、版本 0、跨版本/跨任务隔离、重复身份、完整分母、动态信号、对照图绑定与不可变性）；pytest **103 passed / 4 skipped**，compileall、Ruff 和 TypeScript/Vite 构建通过。4 项可选 SDK/实库 skip 原因不变。Playwright 真实 Chromium 验证真实结果缺失/缺图图例、合成 ORM/grader 的所有筛选、来源 index 9 → 位置 1、未知引用、跨版本不跳转、图例同步、双图说明及 390px 视口。完整 grader 截图明确为合成，不冒充真实评估。

新截图和临时验证包仅位于 ignored 目录；真实样例未改写。旧服务暂不可用，未验证真实 ORM/grader 输出、异步队列进度、持久化或生产性能。开发热更新中间出现的构建/挂载警告已定位并修正根挂载边界，最终页面以干净刷新后的结果为准。

## 旧 workbench 只读浏览复刻（2026-11-07）

用户确认范围：复刻轨迹详情的完整浏览体验，整体保持旧版布局/字号/间距/配色，可做少量简约风微调；编辑、标注写入、审核及版本写操作另接。只读参考旧模板/样式与交互合同，使用 EvoNext React 和 EvidenceClient 独立实现，未把旧全局状态、服务端 DAL、执行或审核写逻辑带入新系统。

当前界面采用 44px 紧凑顶栏、当前任务信息侧栏（默认 viewport 25% + 34px，280–600px 可调）、180px 可调小图条、截图约 30% / Agent 字段余下空间、固定 40px 状态栏与面板内滚动。支持侧栏折叠、小图上下停靠、Grid 3–10 列、点击/Enter 打开、独立 Grid 光标、0-based Step、首尾循环、Home/End、Alt+G/Ctrl+Shift+G/⌘G、已加载任务列表内翻页、H/? 帮助、截图放大/Esc 关闭、复制原文和固定快照/步骤/view 深链接（含同页切换与刷新）。Grid 每页至多 60 项、小图窗口至多 21 项；布局偏好保存在本地，不保存证据或凭据。

真实 raw-only 步骤只在读取时投影思考/动作语义/JSON 工具调用，每个字段注明来源；原始输出、实际执行、独立回执与 Runtime 分开。无原文时禁止“复制原文”；坏 JSON 或未知工具不猜测标记。动作可视化支持提案中的点击/长按/双击位置、拖动/滑动端点，以及非坐标动作标签和悬停近景。本批样例坐标按用户明确确认使用 **0–1000**（非 0–999）；可切换未声明/绑定图片像素。SVG 以绑定图片真实尺寸换算，标记不写入图片或源 JSON，不把提案标记当 dispatch/执行成功。

验证：13 项前端数据层/投影/几何/导航测试通过；pytest **103 passed / 4 skipped**，compileall、Ruff、TypeScript/Vite 构建通过。4 个 skip 的可选 SDK/隔离实库原因不变。Playwright 真实 Chromium 检查真实轨迹字段/小图/Grid/零基导航、面板键盘/指针调整、折叠、循环/Enter/Alt+G、原图/帮助弹窗、同页快照与步骤深链接；合成几何夹具检查 SVG 与显示原图边界吻合、0–1000 分母、点击/拖动、关闭标记、未知坐标拒绝猜测；真实缺图包与 2000 步合成轨迹、390px 固定视口检查通过。截图保留于忽略的 output/playwright。

边界：这是按旧仓库布局/交互合同重建并经新页面实测，不声称已与运行中的旧页面完成逐像素差异验收；不恢复旧来源字段推断的混合审核状态。某些旧提案格式只保留原文；历史 code 不执行或转换为现役动作。真实平台 API、持久化、多用户权限及 2000 张真实截图性能仍未验收；当前仍为本地 demo。未调用模型/设备或执行生产写入，真实样例与原图未修改。

## 真实离线包与简约视觉复核（2026-11-07）

在用户已提供的本地样例中选取 3 个真实离线包，经现有 ZIP API 导入显式 localhost demo 服务：34 步/34 媒体的长轨迹、29 步/24 个去重媒体的缺帧轨迹，以及 4 步/4 媒体的执行回执轨迹。3 包导出后，全部 ZIP 成员名称与原字节一致；来源文件未修改。来源样例已有 44 包；本轮没有把真实内容加入测试夹具、文档或新提交文件。

Playwright 真实浏览器验证真实截图、34 卡 grid、双击进入第 8 步、29 步中 2 处缺帧、执行证据独立展示，以及 390px 移动端无横向溢出。复核发现部分来源只将工具调用保存在 raw_model_output；界面明确提示未单独记录结构化调用，避免将其误述为无工具调用，也不回写解析结果。截图保留在被忽略的 output/playwright 下。

视觉按用户偏好改为白底、浅灰侧栏、中性选中态、细分隔线；保留 grid/单步与底部小图导航。仍使用新 React 和现有数据层。这里只验收了真实离线包经本地 demo API 的读取展示；未调用远端旧平台 API、未验收 Mongo/MinIO 持久化，也未执行设备或模型。先前“仅合成数据”的描述属于对应历史轮次。

## DAL 最小读取切片与 ADR 收口（2026-11-07）

按评审收口 [ADR-003](adr/0003-evidence-data-access.md)，Accepted 仅覆盖最小读取设计。保留 SnapshotRepository + AssetStore，get_index 合并读取 manifest/header；来源历史与资产列表身份/时间分开，现役 hash 分页不变。区分 full_read_fallback/indexed_window 和 manifest/JSON/媒体三个校验范围，明确本地未提交前端基线及 JSON 语义保真/ZIP 成员字节保真。步骤投影、前端按需步骤接入、PG 导入回执、SourceBinding 幂等和多来源权限均未实施。

本切片代码：Snapshot 构造时解析、校验和计算身份一次，公开 document/metadata/media/manifest/summary 返回隔离副本；新 Mongo wrapper 原子写入 index，header/media 仅投影该字段并核验 manifest 身份。缺 index 旧快照只读全量回退，坏 index 不回退、不回写。EvidenceService 用 snapshot_id + locator 核验媒体绑定，API 新增 header，保留 detail/trajectory/bundle/media。确认新插入不再全量读回，已有记录仍验证原证据；完整 BSON 使用官方编码核算 16 MiB，timeout 不自动重试。ready 复用 lifespan 内 PG engine，关闭 owned 存储/媒体 transport，借用客户端不误关。未建额外 Repository、步骤索引、后台任务或 PG schema。

验证：pytest **117 passed / 4 skipped**，新增 **14 项**合成数据回归，覆盖查询投影/无全文解析、旧记录回退无写入、坏索引/坏原文/坏媒体、鉴权先于读取、独立字节身份、JSON/ZIP 区别、完整 BSON 尺寸、官方 UpdateResult、timeout 不重试和连接生命周期。安装了仓库已声明的可选 PyMongo，BSON/UpdateResult 使用官方 SDK；collection double 只证明 Python 查询形状与分支，不证明真实 Mongo 读取、确认写入或磁盘 I/O。隔离实库测试增加 index/header/media 断言但本轮未运行。跳过项为未安装 SQLAlchemy/Langfuse/Celery 的 SDK 检查和未显式配置的隔离实库检查。

compileall、Ruff、前端 **33 项测试**、TypeScript/Vite 构建和 git diff --check 通过。CLI 使用临时合成 ZIP 验证身份与来源版本 0，首次直接调用缺 PYTHONPATH，改用 PYTHONPATH=src 后通过。存在既有 Starlette/HTTPX 弃用提示和 Node 类型转换实验提示。本轮没有修改前端文件；前端数量反映检查时工作树，已有并行变化保留。

边界：当前页面选中快照仍全量调用 detail，尚未验收前端 header/窗口接入、50/200/2000 步性能、真实 Mongo/MinIO/PG、断连恢复或生产部署。未读写旧平台/生产库，未执行设备、模型、训练或数据迁移，也未创建远端 PR。新 wrapper 对原读取路径是额外字段，原 JSON/媒体 bytes 和 snapshot profile 不变。

## DAL 设计审查（2026-11-07）

只读检查当前 EvidenceService、SnapshotStore/AssetStore、API/CLI/Worker、前端客户端，以及旧版任务/版本/资产访问边界与回归用例。新增 [ADR-003](adr/0003-evidence-data-access.md)，明确领域端口、轻量 manifest、步骤读取投影、来源幂等、跨库恢复、连接所有权和 DA-01–10 验收设计；架构入口增加引用。未复制旧私有后端源码、真实数据或配置，未修改运行代码、现役 API 或存储格式。方案为设计提案，DA 验收尚未实施；不能以现有回归通过证明新设计已落地。

现有工作树回归：pytest **103 passed / 4 skipped**；compileall、Ruff、前端 **27 项测试**及 TypeScript/Vite 构建通过，git diff --check 通过。跳过项为 SQLAlchemy、Langfuse、Celery 可选 SDK 检查与未显式配置的隔离实库检查。存在 Starlette TestClient 的 HTTPX 弃用提示。未连接真实基础设施，未测性能或故障恢复，未调用模型/设备或执行生产写入。

## 轨迹页交互与前端数据访问（2026-11-07）

只读参考旧平台的 grid、横向缩略图与媒体读取边界，在 EvoNext React 内独立实现；没有复制私有源码、业务状态推断、旧 DAL 或部署配置。后端继续复用 EvidenceService、SnapshotStore/AssetStore 与按快照绑定的媒体端点，未增加通用 DAL facade，也未修改旧库。

页面支持网格总览/单步证据切换、每行 2/3/4/6 列、底部缩略图选步、方向键/Home/End、源 index/source_index/step_id 分别显示、完整步骤与轨迹原文按需展开、缺图/读取失败/重试。旧平台入口要求显式固定版本（含 0）。前端 EvidenceClient 统一 API 请求；MediaCache 按凭据会话和 snapshot/path 隔离，最多 4 个并发请求，同引用合并，无消费者时取消，空闲 Blob 缓存按 32 MiB/48 项预算回收；正在显示的图片引用不受空闲缓存预算限制。图片只向快照绑定端点请求，不把源 URL 直接当 img 地址；未引入服务端缩略图派生或图片重压。

验证：`npm test` 的 5 项数据层测试通过；TypeScript/Vite 构建、pytest **103 passed / 4 skipped**、compileall 和 Ruff 通过。skip 原因同前一节，真实服务未配置。Playwright 真实 Chromium 验证 grid/小图/详情选步同步、缺图不串图、未知字段可查看、来源版本 0、2000 步合成轨迹末步/首步/末页导航。grid 每页最多 48 卡，底部窗口最多 21 卡；390px 移动端无横向溢出，方向键按实际列数移动。截图保留于忽略的 output/playwright。

边界：2000 步验证是缺图合成轨迹的导航/DOM 检查，不是 2000 张真实截图加载性能验收。详情 API 仍整体读取轨迹；真实旧平台 API/截图接入、Mongo/MinIO 持久化、多人权限、状态标签校准、动作标注/编辑均未在本轮验收。测试与截图使用本地合成夹具，无模型、设备、训练或生产写入。CI 已加入数据层测试与 npm ci，但尚无本轮远端执行结果。

## 本地前端接力验证（2026-11-06）

本地干净分支已快进到交接版本 `2614fac`。Python 3.12 的独立虚拟环境：`pytest -q` 为 **103 passed / 4 skipped**；`compileall`、Ruff 和 TypeScript/Vite 构建通过。跳过项为 SQLAlchemy、Langfuse、Celery SDK 检查（未安装对应可选依赖），以及未显式配置的隔离实库检查。运行时出现 Starlette TestClient 的 HTTPX 弃用提示。

Playwright 使用真实 Chromium 访问 localhost，完成连接、文件选择器 ZIP 导入、列表/详情、来源版本 0、首步截图、切换缺图步骤（不会沿用前图）和完整包下载。通过 Vite 代理导出后逐项比较 trajectory、metadata 和图片原始字节均一致，再导入的 snapshot_id 不变。浏览器仅有 favicon.ico 404，无已观察到的业务请求错误。前端锁文件已生成；依赖安装在本机临时目录，通过被忽略的 node_modules 符号链接供工作区运行。

验证使用 `.local/synthetic-viewer.zip` 合成包和显式 `--demo` 内存服务，未接真实数据或 Mongo/MinIO/PG，未验收重启持久化、旧平台 API、长轨迹性能或生产替换。截图与浏览器产物保留在被忽略的本地目录；本轮未修改产品业务代码。

## 本轮本地检查

环境：Python 3.13.5；当前离线容器不能解析 GitHub 或访问依赖注册表。工作树基线取用户提供的源码包，原始 Git tree 为 `7179532604aeb5cfa9b2d0109cf8becf1e2c30e9`，与远端 `c887ac5` 一致，避免在未知副本上修改。

提交前执行 `PYTHONPATH=src pytest -q`：**104 passed / 3 skipped**。保留全部基线行为测试，并增加分层依赖、政策版本、收费调用恢复/预算、Workshop CAS/Undo/hash、Runtime 冻结/权限/回执及原规格示例校验。`python -m compileall -q src migrations` 通过；`docs/rebuild/examples/validate_examples.py` 验证 9 份 JSON 合同样例的身份、hash、分母和 Gold 隔离。

3 个 skip 是未安装 Langfuse/Celery 的真实 SDK 形状检查与未配置隔离真实存储的 integration 测试。没有偷偷用内存结果替代实库。

## 本轮可用范围

| 部分 | 已写且离线验证 | 仍未完成 |
|---|---|---|
| 重构文档 | 完整 00–08、原 AC-001–063/SEC-01–06、合成样例、来源摘要和 ADR | 全部目标能力的实施与生产签署 |
| 分层 | app/contracts/evidence/operations/providers/compat/skills/runtime；旧扁平实现路径退出 | 使用旧 Python 启动路径的外部脚本需要更新 |
| 数据链 | 原 JSON/ZIP 导入浏览导出与 HTTP 兼容行为回归；共用 EvidenceService | 真实旧新往返、多人权限、2000 步浏览器体验 |
| Policy | 依赖内容 hash、严格变量/静态 include、冻结配置、禁止 secret config | 正式 grader 校准、自动发布到 Langfuse |
| 模型调用 | 发送前回执、received 复用、unknown 不重发、独立 repetition、预算原子规则；真实 PG adapter/migration 已写 | PG 多进程/断电/重启/超时真实故障验收，货币计费、自动 reconciliation UI |
| Workshop | 候选 create/patch/no_change、CAS、history/diff、archive/Undo、owner/hash 校验和固定导出 CLI | 模型学习/视觉复核/merge、反馈 UI、多人生产权限、独立质量 |
| Runtime | none/raw/skill 固定上下文、local/cloud target、恢复请求、精确 grant、回执关联 | 实际设备 adapter、会话持久执行/租约、复位/teacher rollout、独立效果 |
| 失败聚合 | 版本化关系模板与禁止自动合并 Case 的合同 | 候选检索、聚合引擎、人工分组与校准 |

## CI 的准确口径

基线 `c887ac5` 的 GitHub Actions 曾通过 Python 3.11/3.12、63 项非实库测试、Ruff 和前端构建。本轮创建提交时不得把基线成功挪用为新提交结果；新结果以对应 commit 的 Actions 为准。本地未执行 Ruff/前端构建/Docker build，不能记为通过。

## 隔离服务与后续 Gate

实库测试必须显式 `EVONEXT_INTEGRATION=1` 并使用含 test 的隔离数据库/bucket，先运行本平台 Alembic。现有实库测试不覆盖完整模型回执、资源租约或真机恢复。

下一步：真实脱敏 OpenCUA 往返 → 浏览器/持久化与兼容验收 → Review/Case → 一个独立 Outcome grader → 受控 Skill/Runtime 新 trial。Runtime prepare、签名/关联核验和文件 Undo 都不证明手机恢复成功。

本轮没有改变旧平台、写入生产数据库、执行付费模型/真机、训练或生产发布。PG 新迁移未在目标环境执行。原始模型响应将持久存于授权 PG，必须补访问与保留策略后才能生产启用。
