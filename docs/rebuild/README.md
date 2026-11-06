# EvoNext 全量重构规格 · 0.2

本目录是 2026-11-06 对话交付的完整重构文档的入仓修订版，不是另一份并行路线图。原始生成文件的摘要见 `SOURCE_MANIFEST.json`。01/02/04/05/06/07 和合成合同资产保留原需求与验收主体；00/03/本页按最新决定重写，补充 08。旧私有仓库的内部审计链接不放入公开实现输入。

本包规定目标；当前实现和证据只由 [../ACCEPTANCE.md](../ACCEPTANCE.md) 记录。目标表中的“必须支持”不表示已经实现。文档中的候选 API 不等于现役 OpenAPI。

## 已确认、不能被旧草稿覆盖的决定

Mongo + MinIO + PostgreSQL 保留；不再推荐把 Task 全量迁 PG。OpenCUA-shaped `task_id / instruction / traj` 及现有 sidecar 保留，新增控制对象不写进原始轨迹。Langfuse 做模型观测，不另建完整 tracing/Prompt 管理后台。复用 Celery，不引入 pg-boss 或第二个调度器。

在 `src/evonext/` 中，skills 与 runtime 是一级业务模块，不放 offline，也不把 Skill 变成 Runtime 的私有子模块。这个 Python 命名空间包装不降低其产品地位。Workshop 维护候选；Runtime 消费冻结版本；Evaluation 独立评效果；设备、云 batch 和训练集群仍通过适配器接入。不得复制旧实现或恢复已退役的平行链路。

## 阅读顺序

| 文件 | 用途 |
|---|---|
| [00_REVIEW_AND_GAPS](00_REVIEW_AND_GAPS.md) | 本次审查、冲突修正、取舍与未完成范围 |
| [01_PRODUCT_PRD](01_PRODUCT_PRD.md) | 全量用户流程和功能需求，保留稳定需求编号 |
| [02_DOMAIN_CONTRACTS](02_DOMAIN_CONTRACTS.md) | 身份、版本、证据、人审、Case、评估和数据集语义 |
| [03_ARCHITECTURE](03_ARCHITECTURE.md) | 当前分层、存储职责、执行与依赖方向 |
| [04_API_AND_WORKBENCH](04_API_AND_WORKBENCH.md) | 目标接口、前端流程和旧消费者迁移 |
| [05_CLEANROOM_MIGRATION](05_CLEANROOM_MIGRATION.md) | 独立实现、隔离验证、单写切换和回退 |
| [06_ACCEPTANCE](06_ACCEPTANCE.md) | AC-001–063 与 SEC-01–06，保留原验收范围 |
| [07_IMPLEMENTATION_PROMPT](07_IMPLEMENTATION_PROMPT.md) | 交给后续 Codex 的实施任务书 |
| [08_SKILLS_RUNTIME_AND_PIPELINE](08_SKILLS_RUNTIME_AND_PIPELINE.md) | AIHOT/OpenClaw 适配、Workshop/Runtime 合同和新增 Gate |
| [examples](examples/README.md) | 9 份合成业务对象、独立 oracle、哈希/身份校验 |

实现 Agent 按 README → 01 → 02 → 03 → 08 → 当前工作包 → 06 阅读。不要求为了改一个模块读取所有历史讨论。最新明确用户约束高于旧草稿，但不能改写历史运行的真实证据。
