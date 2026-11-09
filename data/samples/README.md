# 离线轨迹包格式约定

共享事实统一放在这里，benchmark 只维护评测题、合同、标签和引用。来源索引是 [sources.jsonl](sources.jsonl)，登记 74 条 Dev 来源：44 条已打包（15 条本地、29 条 EA），30 条明确为 `not_packaged`。来源池不是已审 benchmark。

轨迹顶层采用 OpenCUA [原始示例](https://github.com/xlang-ai/OpenCUA/blob/main/data/cot-generate/gen_cot_example/raw_example.jsonl) 的三个字段；它的 [可视化说明](https://github.com/xlang-ai/OpenCUA/blob/main/data/vis/README.md) 也将轨迹与元信息分开。这里沿用每包一个 JSON 的布局，并保留手机执行所需的原始输出与独立回执。

```text
sources.jsonl                 # 唯一来源索引、资格与当前文件摘要
trajectory/<task_id>/
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
      "step_type": "agent",
      "user_interrupt": "用户跟进",
      "value": {
        "thought": "xxxx",
        "action": "操作语意",
        "tool_call": {"name": "mobile_use", "arguments": {"action": "click", "coordinate": [500, 500]}}
      }
    }
  ]
}
```

以上为字段位置示意，不是一次真实采集，也不要求所有来源都提供解析后的三个字段。`step_type` 可为 `agent / human / retry`；缺失时只在读取视图中默认显示为 `agent`，不回写原始证据。`tool_call` 使用工具调用结构替代旧 `code`；本项目 mobile_use 新采集约定采用 0–1000 归一化坐标，不能据此改写历史来源的坐标协议。

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

## 核心字段补充建议与存储边界

本节对照旧实现的任务轨迹契约、步骤读取模型与离线打包器，整理共享事实应覆盖的信息。它是字段补充建议，不代表现有 44 包已经具备这些证据，也不新增强制字段或触发历史迁移。正式互通规则仍以 [兼容与互通合同](../../docs/COMPATIBILITY.md) 为准，身份与证据语义见 [领域合同](../../docs/rebuild/02_DOMAIN_CONTRACTS.md)。

Mongo 与本地 JSON 共用同一事实模型：`trajectory.json` 保持 `task_id / instruction / traj`，来源和采集上下文继续放 `metadata.json`；Mongo 内部 wrapper 可以分别持有两部分原文与索引，不要求把数据库文档直接作为交换文件。MinIO 保存媒体和其他对象字节。后续 ORM、grader、人审、治理及 trace 分析生成的记录由 PG 持有，按固定输入关联，不回填到原始轨迹。

### 优先明确的步骤事实

下表路径相对 `traj[]`。已有字段有来源才保留；缺少记录不能按默认值、相邻步骤或模型叙述补造。

| 字段 / 信息 | 建议与语义 |
| --- | --- |
| `index`、`source_index`、`step_id` | 包内顺序、源序号、源步骤 ID 分开；新采集应提供稳定步骤身份，旧包保持缺证。PG 结果关联 snapshot 与源步骤，不能仅靠 task_id 或显示序号。 |
| `value.raw_model_output`、`value.recorded_fields` | 原始输出是直接证据，解析字段不是原文替代物；保留缺失、空串与解析失败的区别。 |
| `value.thought / action / tool_call` | 明确是来源记录的解析结果还是修订后的业务动作。旧版 `tool_call` 可能经过人工修订，不能一律称为模型原始提议；原提议由原始输出及固定来源证明。结构化调用保留 name、arguments、调用 ID、批量顺序和未知字段；历史字符串不静默转换。 |
| `action_source_ref` | 如来源已有，保留原始动作所指的固定版本、步骤与 hash；缺失时不绑定到当前 latest。新增修订不得覆盖原模型提议或已发生的派发。 |
| `runtime.dispatched_action` | 实际下发的动作，与 `tool_call` 分开。历史 `runtime.executed_action` 保留原字段，它的名字不证明已执行；兼容读取注明来源路径。 |
| `runtime.action_transformation` | 保留 source、reason_code 等真实转换记录，解释提议与下发为何不同，例如 Harness 将 terminate 改发 wait。不能由两个动作的差异反推转换原因。 |
| `value.recorded_execution`、`value.execution_result`、`runtime.execution_result` | 分别保留已有来源动作记录和执行返回；不合并成单个 success。读取视图中的 `source_execution_receipt / execution_receipt` 不是要求每包另存一套投影。 |
| `runtime.retry`、`value.rejected_model_outputs` | 前者保留真实步骤替代关系（如 retry_of_step_id / retry_of_step_index、source、reason_code）；后者保留同次决策解析重试的真实回复。两类重试不混用，不用 `step_type=retry` 猜关系。 |
| `user_interrupt`、`take_over` | 前者是用户新输入；后者保留 category、summarize、continue_goal、input 等接管事实。`step_type=human` 既不证明人工实际执行了动作，也不等于一次人工审核。 |
| `activity` | 保留 app_name、package_name、activity_name 等源 App 上下文；任务级 App 列表不能替代逐步实际前台 App。 |
| `image` 与已绑定后态 / 终态 | 现有 image 只表示动作前帧。新采集需明确后态 / 终态的 frame relation、关联动作或步骤、媒体 hash；具体扩展结构另行冻结，现有 auxiliary_images 仍不自动获得后态语义。 |
| `trace_ref` / `runtime.trace_ref` | 保留明确的 trace_id、observation_id 等来源引用。它们是事实定位信息；完整模型时序由 Langfuse 承担，后续分析结果放 PG，不复制整份 trace 到每步。 |

### 采集上下文与待补齐信息

以下放置建议沿用现有 sidecar，新增结构需在采集与消费切片中一起确定，不假设当前读取器已经支持。

| 信息 | 现有位置 / 补充建议 |
| --- | --- |
| 来源身份与版本 | 保留 `metadata.record_id / origin / source_snapshot / _version_info`；来源版本 0 有效。明确 source system 与 source key 的命名空间，避免不同来源同名 task 混淆。来源版本、包 snapshot hash、人审版本分别表达。 |
| 执行身份与血缘 | 保留 `origin.run_id`、已有 `source_metadata.lineage` 与 `family_id`；新采集明确 trajectory / trial / session 身份及父运行引用。同任务重新执行产生新证据，不能只更换 task_id 后复用旧后缀。治理后才发现的分组或关联放 PG。 |
| 采集时间与环境 | 保留 created_at 和已有源步骤事件时间；新采集明确时区、采集时刻、环境 / App 版本及相对日期锚点。导入时间、文件 mtime 不冒充执行时间；旧 `runtime.current_time` 只有时分秒时不能独立确定日期。 |
| 模型与动作协议 | 补充实际可核验的 provider / model、Agent / Harness 版本、policy / 工具 schema 版本及坐标空间声明。任务级共享配置放 sidecar，逐步切换须能从步骤引用区分；声明版本与实际响应版本分开，不收集密钥。旧 action_schema_version 如需携带应在 sidecar 显式保留；不是离线包 schema_version 的别名。 |
| 终态报告 | 旧 `client_report` 中的 terminal_step_id、error_type、error_response 等属于 producer 原始报告，应有来源绑定地保留到 sidecar；新采集区分正常结束、取消、预算耗尽、异常、请求接管后停止。执行器声称完成与 grader 判断任务成功分别记录。 |
| 媒体变换与坐标 | 已有 image_profile / image_hashes 保留。新采集如变换截图，应明确原媒体与包内媒体的 hash、尺寸、变换及坐标所依附的图像；包内尺寸可由图片读取，不能用它冒充模型当时看到的原图尺寸。历史 0–999 / 像素坐标不按本项目 0–1000 默认约定自动改写。 |
| 已注入的上下文 | 保留来源已有的 guidance_injected、相对时间锚点和固定 Skill / 上下文引用；无法恢复实际请求时明确未知。不能将已注入提示的运行误称为无辅助 baseline，也不要求把完整模型请求复制进每包。 |

### PG 中的派生记录

- ORM / grader 的评分、理由、逐项判断、诊断和运行状态放 PG；至少绑定 `snapshot_id`、grader / spec 版本、运行与独立重复身份，并按需定位源 step_id / source_index。仅同 task_id 或同版本号不能证明使用了相同输入。
- 人工审核、注释、纠正建议、Case、采用决定与训练资格分别由对应 owner 维护。纠正动作可作为独立建议；实际修改轨迹事实时创建新 revision / snapshot，原始 dispatch 和结果不变。
- trace 派生的耗时统计、成本汇总、失败模式和聚合特征放 PG，并记录输入引用、计算规则版本及缺证状态。来源 runtime 中已经记录的 latency、risk_control 等仍原样保留；新增离线评分不写成运行时已经作出的决定。
- 不把旧 `evaluation / rating / quality / routing / lifecycle_stage`、步骤正确性标签或 `display_fields` 一并升格为新轨迹必填项。旧 JSON 已携带的字段仍须无损保存，按来源信息只读展示；新生成的判断由 PG 持有。当前已去参考答案的事实包继续保持隔离。
- 缺失、`null`、`false`、`0`、空字符串和空数组分别保留；未知字段包含嵌套字段。验证视图可以提供读取默认值，但不得把默认值、解析投影或 PG 查询结果序列化回原始证据。

## 现有包与历史迁移记录

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
