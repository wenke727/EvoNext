# 离线轨迹包格式约定

共享事实统一放在这里，benchmark 只维护评测题、合同、标签和引用。来源索引是 [sources.jsonl](sources.jsonl)，登记 74 条 Dev 来源：44 条已打包（15 条本地、29 条 EA），30 条明确为 `not_packaged`。来源池不是已审 benchmark。

轨迹顶层采用 OpenCUA [原始示例](https://github.com/xlang-ai/OpenCUA/blob/main/data/cot-generate/gen_cot_example/raw_example.jsonl) 的三个字段；它的 [可视化说明](https://github.com/xlang-ai/OpenCUA/blob/main/data/vis/README.md) 也将轨迹与元信息分开。这里沿用每包一个 JSON 的布局，并保留手机执行所需的原始输出与独立回执。

```text
sources.jsonl                 # 唯一来源索引、资格与当前文件摘要
dev/<task_id>/
  trajectory.json             # task_id / instruction / traj
  metadata.json               # 来源、版本、图片摘要；不带评测答案
  images/<来源文件名>.jpg
```

```json
{
  "task_id": "example-task",
  "instruction": "用户任务原文",
  "traj": [
    {
      "index": 0,
      "image": "images/image_0.jpg",
      "value": {
        "think": "xxxx",
        "action": "操作语意",
        "tool_call": "模型返回的工具调用" # 因架构升级替换原来的 code
      }
    }
  ]
}
```

- `index` 从 0 连续排列，保持来源步骤顺序；`image` 是该步骤动作前的截图。缺帧使用 `null`，不得拿其他步骤或请求图片补齐。
- `raw_model_output` 保留模型实际返回的可见文本，包括原有 ReAct 标签、空白和解析错误；不强制补全示例中的标签，也不根据 thought / action / tool_call 字段拼造原文。消费者复用库中的解析逻辑。
- 原始输出确实缺失时使用 `null`，并通过该步骤的 `value.recorded_fields` 保留已有来源字段。它们是已记录的解析结果，不是原始输出。
- 有解析失败后的重试时，最终接受的输出放在 `raw_model_output`；此前真实返回的输出按顺序放在可选的 `value.rejected_model_outputs`。没有重试则省略该字段。
- 图片统一 JPEG，`quality=98`、`subsampling=0`；复用库中的 Qwen smart-resize，尺寸按 32 像素对齐，最多 980 个 32×32 patch。980 是图片像素预算，不是供应商计费 token 的保证。转换后的图片不冒充历史请求中的原始 bytes。
- 目录名使用来源 `task_id`；`record_id` 是稳定来源身份。图片沿用来源文件名，同名异内容时追加步骤后缀；相同内容只保存一次。相对图片路径不含 base64、data URL 或机器绝对路径，图片摘要放在 `metadata.json.image_hashes`。原始回复与回执中的历史定位原样保留。
- `metadata.json` 使用 `schema_version=opencua-offline.v1`，平铺来源定位、采集版本 / 时间、快照摘要、`split`、`do_not_train`、图片 profile/hash 和必要 App 上下文。额外截图使用 `auxiliary_images`，不自动赋予动作后状态或成功含义。整个目录可移到仓库外读取，不依赖来源索引的位置。
- 有独立来源执行证据时，保存 `value.execution_result` 和 `value.recorded_execution`；不能根据模型回复补造。OpenCUA 示例中的 `value.code` 是其原始演示动作，这里的模型提议与已有执行记录继续分开。历史 VQA / 平台判词从固定 Git 版本追溯；当前事实包不带参考答案。
- 导出器用连续 `index` 表示包内位置，另以可选 `source_index`、`step_id` 保留已有来源步骤身份，并保留原 `runtime` 与真实重试输出。旧包没有这些字段时维持缺证，不根据包内位置补造原步骤身份。
- 详细读取视图分别展示 `recorded_execution`、`source_execution_receipt` 与 Backflow 的 `execution_receipt`。本地回执中的 `status=success` 只保留来源声明，不自动变成 ACK 确认、动作效果或任务成功；旧回执中的机器路径只作 provenance，不作为已绑定的动作后帧。
- 已记录的 code / normalized_tool_call 在内存投影中恢复给现有消费者，并以 `field_sources` 指向 `value.recorded_execution`；原始模型提议仍单独保留在 `raw_model_output` / 解析后的 `tool_call`。恢复来源动作不补造 Runtime dispatch 或执行确认。
- 包中不重复保存 workspace、task、evidence、完整模型请求、回执或 runtime trace 的投影文件。消费者按需生成读取视图，评测、诊断、编译产物写入各自运行目录。严格传输取证需要另行获取原始采集。

收录与资格由来源索引管理：默认 `do_not_train`、`human_gold=false`、`acceptance_eligible=false`。平台快照标签属于来源记录，不代表当前平台状态或独立人工 Gold。仅在新起态、路径、证据类型或失败边界有增量时打包，不能以数量作为扩充目标。

现有 44 个来源包包含 15 个本地采集包和 29 个 EA 平台来源包，共 465 个步骤、462 个步骤截图绑定。3 个缺帧保持 `null`；459 步保存原始模型输出，其余 6 步保留原文缺失及来源字段，其中 3 步来自人工逐步记录。两次失败重试的真实回复单独保留。

当前入口统一为 `trajectory.json`，不并列保存 clean-v2 等工作版本。来源索引的 `offline_bundle` 分别固定轨迹与元信息的 byte hash；`parent` 固定历史 Git revision、路径、hash 与旧来源行版本。格式更新增加来源和消费者 `record_version`，并同步 ORM / Agentic Review 的 32 条引用与 Compile 效果资产的 2 条引用。历史运行结果仍绑定历史输入。

父包采用三字段格式时，`parent.metadata_byte_sha256` 必须绑定同一 Git revision、同一目录的 `metadata.json`。父包读取只使用固定 Git blob，不借用工作树当前 sidecar；缺少或不符的摘要会阻断校验。旧内嵌元信息父包仍按其原始轨迹摘要恢复。事实等价检查继续用于无损格式迁移，不能把新增观测或重导出内容当成同一迁移；新的来源采集需要自己的版本、定位与消费者绑定，不覆盖历史运行。

清洗统计、缺证列表和迁移回执写入 ignored 本地运行目录，检查时现场计算，不在每个包内重复存一套报告。只有逐项事实、媒体与消费者读取一致、当前引用已迁移且历史版本可恢复，才删除旧文件。已有 463 张 JPG 未复制或重新编码。

209 步保有来源执行回执，但全部缺少 Runtime dispatch 与原步骤 ID/index。旧回执中的 209 个动作后截图路径尚未绑定为可携带的帧，继续作为缺证报告；不能把下一步骤截图自动填入。结构清洗不重审标签、不补造原始请求、不产生新的模型评估结果。

## 数据防卫

入口与所有权规则见 [benchmark 数据防卫](../benchmark/README.md#数据防卫)。从仓库根目录设置 `PYTHONPATH=src`，使用 `dl2` 环境执行：

```text
python -m offline.benchmark.catalog --repo-root .
python -m offline.trajectory_tools.clean_dev --catalogue data/trajectory_evidence/sources.jsonl --repo-root . --check-only
```

第二条只读检查身份、Dev 资格、轨迹及元信息摘要、历史父包事实等价、JPG、缺证与当前消费者引用，并拒绝多余 JSON、图片或未登记包。历史 Git commit 必须可读；CI 获取完整历史执行相同检查。通过只表示输入完整，不表示任务成功、模型质量或训练准入。
