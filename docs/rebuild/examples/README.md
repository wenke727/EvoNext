> 本目录是未来业务对象的合成合同示例，不是现役 OpenCUA 上传格式。实际可导入样例见仓库 `examples/trajectory.json`；TaskRevision/Job/Eval 示例通过不表示对应 API 已实现。

# 合成合同示例（Synthetic Only）

这组样例**不是现实 GUI 轨迹、真实手机截图、人工 Gold 或模型评分**。它们专门验证对象之间的 ID、version、source/媒体 hash、审核独立性、Evidence delivery、Evaluation 全分母、Snapshot 冻结与干预交接。`step_0_before.txt`、`step_0_dispatch.txt`、`step_1_after.txt` 是人为编写的事件文字，不是实际观察到的屏幕图像。示例里点击获得了工具 ack，但后态仍是 OFF，用于证明 `dispatched != effect`。本包不依据这些 mock 产出真实的模型准确率。

| 文件 | 测试价值 |
|---|---|
| `source_rollout.synthetic.v1.json` | 大于 JavaScript 安全整数的字符串 task_id；step ID 非连续；proposal/dispatch/后态分开 |
| `ingestion_receipt.synthetic.v1.json` | 唯一 source hash、幂等导入和完整 Job 计数 |
| `task_revision.synthetic.v1.json` | raw→derived revision；`revision=1` 仍是 unreviewed；证据索引及字节哈希 |
| `review_case.synthetic.v1.json` | 人审独立 approved；一个 Case 有 review/locator/bad_case membership，根因仍可 unknown |
| `evaluation_run.synthetic.v1.json` | 工具被派发 pass，不代表目标达成；Goal fail；实际模型调用数为 0（模拟记录） |
| `dataset_snapshot.synthetic.v1.json` | 固定来源、Review/Case/Trial 引用、members hash；污染 unchecked 禁止 formal train |
| `intervention_handoff.synthetic.v1.json` | 归因不足时返回 needs_evidence，不生成 Skill/Trial 或授权执行 |
| `evaluation_matrix.synthetic.v1.json` | 12 个 Requested Check，3 pass / 2 fail / 2 unknown / 1 NA / 4 not_assessed |
| `hidden_oracle.DO_NOT_SEND_TO_MODEL.json` | 合成测试预期；只用于测试 harness，永不进入 judge/生成器输入 |
| `evidence/*.txt` | 真实存在的测试字节对象，content SHA256 与 manifest 一致；无图像假冒成功 |

注意：这里共 **9 份 JSON**（包括 hidden oracle）。`evaluation_matrix` 是独立协议示例，不是把另一个 12 项的 Dataset 成员偷偷塞入已有的 1 项 Snapshot。需要真实批次案例时，先产生另外一份明确的 DatasetRevision、每项 frozen input 和请求身份。

运行校验：

```bash
python docs/rebuild/examples/validate_examples.py
```

如果修改事件文字或 source payload，使用：

```bash
python docs/rebuild/examples/build_fixtures.py
python docs/rebuild/examples/validate_examples.py
```

JSON 的结构验证不是完整 JSON Schema 与端到端行为验收。真正的图片、跨库一致性、独立人审与外部 Runtime 只能在有允许的来源/环境时验证；缺失时应报告 `not_run`，不能把 synthetic fixture 当成真实实验。
