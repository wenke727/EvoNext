# 兼容与互通合同

## Skill 多文件与旧 v1 合同

`evonext.skill-revision.v1` 仍按 SKILL.md 的原 UTF-8 字节哈希验证，不重写历史。
无附件的 v1 Bundle 导出仍只有 `ref/document`，其 Runtime 上下文字节与旧版保持一致。
v2 显式带 `format_version="v2"` 和不可变 `assets`（path/content）；content_hash 覆盖
规范 JSON 文件映射 `{"SKILL.md":document, ...assets}`。revision 继续绑定完整记录、
parent、owner、来源集合和理由，content_hash 与 revision 不混用。

v2 附件只支持 UTF-8 文本；允许 references/templates/scripts/assets 下的安全相对路径，
不接受路径穿越和大小写冲突。最多 50 个附件，整个规范文件映射 256 KiB，
SKILL.md 仍限 64 KiB。脚本没有执行权限含义。恢复/归档/diff/导出携带全部文件；
旧调用未提供 assets 时保留既有附件，显式空映射表示移除附件。
仅懂 v1 的外部消费者须拒绝 v2，不能静默剥离附件。Runtime 的 owner/hash/grant
检查覆盖完整 Bundle；候选的导出或交付不等于实际阅读、执行成功或采用。

新增 Workshop API/CLI 不迁移 EvoLoop 数据、旧格式或生产 Registry；本地草稿目录
与 PG 模型操作回执分别履行已有职责。共享目录的生产权限、备份和多机部署不在
本地候选 profile 的已验范围。

## 1. 保留的数据

现有 OpenCUA-shaped 数据主体继续使用 `task_id`、`instruction`、`traj`。已有离线包采用：

```text
trajectory.json
metadata.json
images/<原文件名>
```

`metadata.schema_version=opencua-offline.v1` 是现有离线 profile；不把它宣传为所有 OpenCUA 上游版本的统一官方 schema。轨迹、来源元信息与评估答案继续分离。

保留顶层、步骤、value、runtime 中的未知字段。`task_id` 必须是 JSON string；大整数 ID 不经 JavaScript number。原始模型输出保留空白、解析失败和真实重试，缺失为 null；不由 thought/tool_call 拼造。`index`、source_index、step_id、显示位置不是同一个身份，不自动重排或重编号。

`tool_call`、模型原始文本、实际 dispatched/recorded execution、执行回执、动作后观测分别保留。导入不会执行 code，也不会把 historical code/normalized 字段转换为现役动作；需要转换时是单独、可回滚、显式确认的迁移。当前旧平台上传 adapter 拒绝已退役的业务动作字段。

不改写 JPEG/PNG/WebP 字节、尺寸、坐标、frame relation 或图片哈希。非默认图片变体可以作为新增派生对象，但不得替换原证据。不会从相邻截图推定动作成功。metadata 里的 do_not_train、split、exposure、源版本和约束保持原值，不因为导入而授予新用途。

## 2. 快照和版本

评估输入投影 `evonext.evaluation-input.v3` 增加原步骤的 `user_interrupt`、角色、
步骤时钟、布尔 effective 标记和一个可引用的 source context。只从原始输入读取
created_at 与首个 backflow input endpoint 的 localTime/timeZone；元信息的判决、
原始模型响应及设备身份不因此进入模型。创建日期与已声明时区下的输入本地日期一致
才给出 corroborated_local_date，不用评测当天替换历史日期。effective 不代表动作执行。
原轨迹字节和现有快照身份不变。

评估请求的 `review_localization` 默认 false。显式启用后，已给出错误位置而该位置或
更早原图未交付时，auto 可继续调查；合法但引用无效的初始 JSON 可在现有调查预算内
收到明确反馈。保留原始判定和校验错误，只有新响应通过完整校验才接受；网络不确定
不据此重发。预算停止时无效判定仍不能成为已验收结果。

v3 为交付的事实字段提供 `fact_refs`，保留提案、思考、runtime dispatch 的不同引用。
`bind_decisions` 默认 false；启用后，定位错误须引用本步骤实际交付的决策字段，
不能借用后一步的字段或仅引用时钟/状态标记。原图邻接关系不是动作效果或执行者证明。
`runtime_coordinate_profile=evoloop_fraction_v1` 是调用者显式声明的来源坐标格式，
仅在 runtime 未声明单位时允许用 0–1 画派遣标记；source 默认不猜单位，
原声明单位优先，原图字节不变。派遣标记不代表该动作成功。
未定位的 finding 不填 decision_ref；观察引用仍保留在 evidence_refs。绑定模式的调查
响应无效时，可在剩余调用预算内收到校验反馈并重新提交，预算耗尽仍报错；不自动改引用。

`Snapshot.id` 使用 `evonext.snapshot-bytes.v1`：trajectory 文件 byte SHA-256、metadata 文件 byte SHA-256、图片路径到 byte hash 的映射，按规范 JSON 编码后再哈希。输入 JSON 的纯格式变化也可能得到新 snapshot_id；这不是“任务语义变化”的判断。移动整个包所在目录不会改变 ID。

旧 `task_id` 和来源 `version_number` 保留。版本 0 有效，未知版本保持未知，版本不代表审核状态。快照同名内容不可覆盖；没有按照 hash 排序推断 latest 的规则。未来审阅需独立 revision/CAS，不能覆写已有 snapshot 或复用它伪造历史。

原 JSON 上传 API 先严格解析再编码，保证结构保真，不保证原 JSON 空白；ZIP 保留两个 JSON 文件和媒体的原始字节。归档 ZIP 自身的压缩头/时间戳可不同，不声称整个 ZIP 文件 byte hash 恒等。

## 3. 两平台互通矩阵

| 路径 | 当前行为 | 验证边界 |
|---|---|---|
| 旧平台导出的完整包 → 新平台 | 校验后导入；保存原文件与媒体；未知字段不丢 | 合成合同已测，尚未跑目标环境真实包总体验收 |
| 新平台 → OpenCUA JSON / 包 | 原数据导出；ZIP 原文件字节一致 | 已测试导入/导出/再导入身份一致；需旧消费方执行自己的合同测试 |
| 旧 API → 新平台 | 配置固定服务地址，GET `/api/task/{task_id}`；显式 version 核对响应版本，含 0 | HTTP mock 已测；不回退 latest。图片 URL 只保留，不任意下载 |
| 新平台 → 旧上传 API | 显式 `traj → steps`、multipart 图片、create-or-skip；默认 dry-run | 不是无损路径；元信息/额外顶层字段可能不转移，返回 omitted 字段和未验证状态 |
| 两套平台直接写同一旧库 | 本轮禁止 | 后续先证明并发、审核保留、版本/CAS、审计与单写切换；不能用“都接 Mongo”代替 |
| 旧平台全量 API / Cookie / 页面兼容 | 未实现 | 不能把少数 adapter 说成全量可替换协议 |

旧 API 的媒体读取后续应使用来源绑定的固定版本图片端点，不信任数据内任意 URL、文件路径或 presigned locator。JSON 导入可保存缺图轨迹，但完整 ZIP 导出会明确拒绝未绑定媒体，不拿别图补齐。

## 4. HTTP 写回规则

需要同时满足 `EVONEXT_LEGACY_WRITES=true`、调用参数 `dry_run=false`、`allow_projection_loss=true`。默认拒绝覆盖，`existing_task_mode=skip`，不自动触发模型评估。未取得同内容读取回执时，返回 `submitted_not_verified`，不是同步成功。响应超时可能已经写入，保留不确定状态，不自动再次 POST。

该 adapter 是可选择的旧上传桥，不是后台双向同步引擎。完整无损互通优先使用包；需要在线完整同步时，应先由双方冻结版本化交换合同，增加显式入站导入和来源回执，不能继续依靠可能丢字段的旧 rollout 投影。

## 5. 验收与切换

兼容验收必须包含旧真实样本的 raw_model_output-only、原生 tool_call、历史动作字段、null 截图、辅助图片、长 ID、版本 0、缺历史版本、未知字段、重复导入、hash 不符、已修改 Task、Case 固定引用和人机评估并存。真实材料留在授权环境，不提交公开仓库。

切换前单独验收旧读新、新读旧、媒体可达、固定版本、写冲突、幂等、审核保护、回流来源与返回回执。任何缺项保持未测，不以合成测试全绿填满兼容矩阵。

## 6. Workbench 只读显示投影

显示序号沿用旧 workbench 的 0-based Step，但不据此补造源 index/source_index/step_id。原字段、来源版本和 Snapshot 身份保持分离。`raw_model_output` 中单个闭合 think/action 区块和严格 JSON tool_call 可以形成注明来源的临时读取视图；解析失败保留原文，不执行 code，不将 recorded_execution 提升为模型提案或 Runtime dispatch，也不把解析值序列化回源 JSON。

本批 mobile_use 样例经用户确认采用 0–1000 归一化坐标作为显示配置；它不是所有 OpenCUA 数据的默认坐标合同。页面允许显式选择未声明或绑定图片像素，不按坐标数值大小自动猜测。原图上的标记与近景是临时展示，不修改图片字节、hash 或源坐标，不证明实际执行或成功。

只读标注 profile 增补：支持 `mobile_use.arguments` 及旧 `value.tool_call` 的直接结构化 action 对象，显式 `action=batch_actions / batch_actions[]` 按源顺序投影。未知子项保留原位，不执行历史 code；type/system_button/wait 等无空间动作不补坐标。重复几何可共用序号标记，但不同 motion 终点不合并。该读取 profile 不代表全部旧动作语法已兼容。

用户进一步确认 BBox 也采用 **0–1000** 的默认显示约定，与动作共用坐标选择。这不是对历史像素字段的自动探测或原数据迁移；需要读取旧像素数据时显式选择原图像素。当前 `value.bbox` 支持 `{x,y,width,height}` 与 `[x1,y1,x2,y2]`；有效范围按选定空间检查，数组反向角点可规范化显示，退化/非法/越界框保留原文而不绘制。不将 0–1000 默认为所有外部 OpenCUA 来源的事实。BBox 独立显示开关默认关闭，提案标记与来源框均不代表执行结果。

打点面板直接展示当前冻结步骤的原字段，搜索可定位嵌套属性；不会把 recorded_execution 当成 dispatch，也不把 observation 当成新执行。复制为格式化步骤 JSON，不声称保留原文件空白字节。

来源追踪引用 profile：读取 `step.trace_ref` / `step.runtime.trace_ref`，支持字符串 trace ID 或对象中的 `trace_id / observation_id / url`，其余字段保留原文。长字符串 ID、数值 0 保持可见；不安全大整数不转为猜测 ID。只将来源明确提供、无 URL 用户凭据的 HTTP(S) 绝对链接作为手动入口；不按 Task ID、步骤位置或 trace ID 拼接 URL，不自动读取、嵌入或验证远端服务，不附加本平台 API 凭据。全任务范围只汇总当前快照的步骤引用；点击 Step 定位的是声明该引用的源步骤，并不证明远端 trace 内容匹配。没有引用时明确缺失，不生成假的追踪数据。本 profile 不等于旧模块 log API 或真实 Langfuse 日志集成已完成。

旧 BBox 单位识别与数据转换按用户最新决定留给治理管道，前端不继续增加旧 BBox 迁移分支；已有原图像素选择不构成自动兼容承诺。

## 7. 来源评估与图例读取 profile

Workbench 支持 `trajectory.evaluation.prediction` 与 `trajectory.evaluation.graders` 的来源评估读取视图：状态、理由、来源、逐项判断及源步骤引用。它不运行评估、不创建新评估控制事实，也不仿真全量旧 Evaluation API。包未携带结果不同于未评估；逐项 false/null/true/缺失或非法判断分别显示错误/不确定/正确/未判定，保留完整条目分母与原始未知字段。

`source_snapshot_id`、`source_task_id`、`source_version` 分别核对；同任务同来源版本（含 0）仍标为“输入快照未核对”，只允许参考定位。其他任务/版本/快照或关联未知的引用不跳转到当前输入。源 step index/step_id 必须唯一映射到显示位置，重复或不存在保持无法定位；不补造身份。

图例根据显式来源字段生成，卡片、徽标与说明共用同一投影。来源正确/错误标记、模型提案、Runtime 接管、独立回执与人审结论不能互相替代。当前/下一步对照不赋予动作后状态；只有 manifest 已绑定的记录后续图/辅助图才可读取，辅助图不自动获得时序含义。

## 8. 轻量概要与媒体读取

新增 `GET /api/v1/snapshots/{snapshot_id}/header`，沿用 API Key 与 no-store；返回现役 summary 的字段（instruction 为完整原文而非列表的 600 字截断）、missing_media 和 manifest，不返回 trajectory 或 metadata 正文。它是 `evonext.snapshot-index.v1` 可重建读取投影，不授予来源审核/评估权威，也不声明全部 JSON/图片已经逐字节验证。完整 detail/trajectory/bundle 路由保留。

新快照的 header/media 只读取轻量 Mongo wrapper；缺 index 的已有快照全量核验后生成临时视图，不回写。media 仍用 snapshot_id + path 校验绑定后读取原 bytes，不能以 digest 绕过绑定。不存在/未绑定为 404；已有 index 损坏或绑定媒体缺失/损坏为 500，保留 error 字符串形状，不泄漏存储地址。不将损坏当客户端输入错误或自动更换来源版本。

现役列表继续按 snapshot_id/hash 游标返回资产，不改变排序或新增来源时间筛选。页面选中轨迹目前仍调用完整 detail；本后端切片不等于页面已消除整轨迹传输。

## 9. 默认旧 Mongo 来源 profile

`evoloop.mongo-read.v1` 通过显式受信的本地 dotenv 引用读取配置，使用官方 Mongo/MinIO SDK；只读 `{collection}_latest / {collection}_history`，不导入旧 DAL 或执行索引、迁移、修复及写入。前端自动读取列表；`POST /api/v1/source/open/{task_id}` 表示操作者打开并在新 Evidence owner 中固定输入，不是向旧平台发布。`GET /api/v1/source/tasks` 为有界列表，游标按字符串 Task ID 降序；不是全文检索或完整旧查询 API。CLI inspect-source 复用同一读取逻辑，在临时内存中检查而不持久化。

版本留空时读取一次 Latest 的完整文档并保留其明确版本；固定版本只读取匹配的 History 或同版本 Latest。未找到、未声明版本或版本不匹配均报错，0 不当成空值。BSON 文档以 Extended JSON 读取投影，保留 `_id`、未知字段、原始输出与字符串 ID；非 JSON 原生类型和不安全整数的表示转换在 metadata 中声明，不能声称 Mongo 原文是未经转换的 JSON 文件。

只绑定已配置 MinIO origin 下的图片桶及旧 VLM 桶（VLM_MINIO_BUCKET，旧约定默认 vlm-api） 中无 URL 内联凭据、query 或 fragment 的来源对象；不重写源 image 字段、不访问任意来源 URL。缺对象或不支持的 locator 明确未绑定；字节/步骤上限及读取错误不转为假成功。图片字节仍由新 AssetStore 拥有。保留原 URL 的读取 profile 当前可导出 JSON；可移植 ZIP 需要显式路径投影，当前页面禁用该入口。这不是改动既有离线 ZIP profile。

旧源是配置后的默认页面入口，配置错误不静默回退。未配置仍可使用显式本地快照/离线包；本轮 localhost demo 的新捕获仅在内存中，不证明持久化、访问隔离或生产替换已验收。
