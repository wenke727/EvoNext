# 兼容与互通合同

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
