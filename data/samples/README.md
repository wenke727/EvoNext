# 离线轨迹包数据契约

本目录仅保存数据契约，不收录真实轨迹、截图或来源索引。公开可运行的合成样例位于 `examples/`。正式互通边界见 [兼容合同](../../docs/COMPATIBILITY.md)，身份与证据语义见 [领域合同](../../docs/rebuild/02_DOMAIN_CONTRACTS.md)。本文不声明新增字段已被所有导入器或消费者支持。

## 包布局

```text
<task_id>/
  trajectory.json             # task_id / instruction / traj
  metadata.json               # 来源、版本、图片 profile 与摘要
  images/<来源文件名>.jpg
```

整个包应可在仓库外读取，不依赖仓库内来源索引。轨迹与元信息分开保存，不在包中混入评测参考答案或消费者生成的投影文件。

## 轨迹与步骤

轨迹顶层保持 OpenCUA-shaped 的 `task_id / instruction / traj`。下例仅说明字段位置，是合成示意，不是采集证据：

```json
{
  "task_id": "synthetic-example-task",
  "instruction": "合成任务指令",
  "traj": [
    {
      "index": 0,
      "image": null,
      "step_type": "agent",
      "value": {
        "raw_model_output": null
      }
    }
  ]
}
```

- `index` 是从 0 连续排列的包内位置；已有 `source_index`、`step_id` 是来源步骤身份，分别保留，不能按包内位置补造。长字符串 ID 不转换为数值。
- `image` 指向该步动作前截图的包内相对路径；缺帧保持 `null`。不得拿下一步或其他请求的图片补齐动作后态。后态或终态必须有明确的帧关系和证据绑定。
- `step_type` 可为 `agent / human / retry`；缺失时仅可在读取视图中默认显示为 `agent`，不得回写原始证据。`human` 不等于实际执行或人工审核；`retry` 不足以证明步骤替代关系。
- `value.raw_model_output` 保留模型实际返回的可见文本、空白、标签和解析错误，不由 `thought / action / tool_call` 拼造。原文缺失时保持缺证；已有解析字段可通过 `value.recorded_fields` 保留。
- `value.thought / action / tool_call` 是来源已有的结构化字段，不自动证明是原始模型提议。结构化工具调用保留 `name`、`arguments`、调用 ID、批量顺序与未知字段；历史字符串不静默转换。
- 同次决策解析重试的真实回复可保存在 `value.rejected_model_outputs`；步骤重试关系由来源已有的 `runtime.retry` 等记录表达，两类重试不混用。
- 已有 `user_interrupt`、`take_over`、`activity`、`runtime`、时间、trace 引用及未知扩展原样保留。`user_interrupt` 是用户新输入；接管记录与人工审核分别表达。

## 动作、派发与观测

- 模型提议、修订建议、实际派发和执行返回分别保存。来源已有的 `runtime.dispatched_action`、`runtime.action_transformation`、`value.recorded_execution`、`value.execution_result`、`runtime.execution_result` 不合并成一个 success。
- 历史 `runtime.executed_action` 的字段名不证明动作已执行；来源回执的 `status=success` 不自动证明设备 ACK、动作效果或任务成功。不能从动作差异反推转换原因。
- 已有 `action_source_ref`、执行身份、重试血缘和来源版本须固定引用；来源版本 `0` 有效，不能替换为 latest。
- 修改原始证据产生新的 source/revision/snapshot，不覆盖原始派发和结果。恢复执行需要新证据，不能在修改动作后拼接旧运行后缀。

## 元信息与媒体

- 现有离线 profile 使用 `metadata.schema_version=opencua-offline.v1`。保留已有 `record_id / origin / source_snapshot / _version_info`、采集时间、环境与 App 上下文、`split`、`do_not_train`、`image_profile / image_hashes`，并保留未知字段。包格式版本、来源版本、字节 hash、语义输入 hash 与人工审核状态分别表达。
- 图片沿用来源文件名；同名异内容须消歧，相同内容可复用。`image` 相对路径不含 base64、data URL 或机器绝对路径；原始回复与回执中的历史定位作为来源证据原样保留，不自动访问或绑定。
- 离线图片转换 profile 为 JPEG、`quality=98`、`subsampling=0`，按 Qwen smart-resize 将尺寸对齐到 32 像素，最多 980 个 32×32 patch。该预算不保证供应商计费 token 数；转换产物不冒充模型历史请求中的原始 bytes。
- 已存在的图片不得在无损互通中重新编码。发生转换须声明原媒体与产物的 hash、尺寸、变换及坐标空间；本项目新采集的 0–1000 坐标约定不能改写历史像素或 0–999 协议。
- `auxiliary_images` 只表示额外图片，不自动获得动作后态或成功含义。缺少终态报告、原始请求、dispatch 或媒体绑定时保持缺证。

## 无损互通与存储权威

- 缺失、`null`、`false`、`0`、空字符串和空数组分别保留；未知字段包含嵌套字段。验证视图的默认值、解析投影或查询结果不得序列化回源证据。
- JSON 导入保留结构；需要文件字节保真时使用 ZIP。ZIP/file 互通保留原始 `trajectory.json`、`metadata.json` 和媒体字节；HTTP 投影须声明支持的 profile、转换、未知项与未验证读回，不能宣称完整模拟旧 API。
- Mongo 拥有轨迹事实，MinIO 拥有对象字节，PostgreSQL 拥有明确引入的控制记录。来源携带的既有评估字段仍无损保留并按来源展示；新增评估、诊断、人审、Case、纠正建议、采用与训练资格由各自 owner 记录并绑定固定输入，不回填为原始执行事实。
- 机器判断、人工审核、候选生成、执行、采用和训练资格保持独立。来源标签、包完整性、模型完成声明都不自动赋予任务成功、Human Gold、验收资格或训练准入。
