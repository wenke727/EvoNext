# 验收记录与剩余 Gate

本次为代码框架交付，不是生产替换。测试材料全部合成，没有读取目标服务数据、执行真实模型或操作手机。

## 已执行

Python 3.13.5 执行 `pytest -q`：**61 passed / 3 skipped**。`python -m compileall -q src migrations` 通过。该环境包含 FastAPI/Pydantic/HTTPX/SQLAlchemy，但没有 PyMongo、MinIO、Celery、Langfuse、psycopg，且不能连接外部包注册表。

离线通过的行为覆盖：

| 范围 | 验证内容 |
|---|---|
| 数据 | 三字段主体、未知扩展、原输出空白、长字符串 ID、版本 0、sidecar 版本、冲突版本不猜测 |
| 包 | JSON/metadata/媒体逐字节往返、重复导入、hash 核对、空截图、缺图不补造 |
| 边界 | 非法 JSON、重复 key、非有限数、无效 Unicode、危险路径、symlink、重复/陌生 ZIP 成员、展开体积上限 |
| API | 鉴权、错误不回显输入、完整纵向路径、分页、媒体绑定、缺图导出拒绝、请求体限制、OpenAPI body |
| 旧平台 | 固定版本 HTTP 合同、版本不符拒绝、默认只预览、写回双重开关、POST 超时不重试、历史动作不自动转译 |
| 模型/追踪 | 假传输下的有界调用、实际模型 ID、usage、默认不采集内容、追踪故障不吞模型错误或重复调用 |
| Worker 核心 | 确定性完整性校验和幂等回执；完整性通过不是任务成功；PG 表归属检查 |

## 明确未执行

真实 SDK 形状检查有 2 项 skip（Langfuse、Celery），实库集成有 1 项 skip。它们不是通过。前端 npm install/build、实际浏览器验收、ruff、Docker build、真实 Mongo/MinIO/PG、broker 重启、Langfuse 送达、两平台端到端兼容均未在此容器执行。

GitHub CI 配置会安装依赖，并执行 Python 3.11/3.12、SDK 形状检查、lint 和前端构建。CI 的实际结果以 Actions 页面为准，不能从本文件推定成功。

## 隔离服务验收

先创建名字包含 test 的独立 Mongo 数据库、MinIO bucket 和 PG 数据库，执行本平台迁移，再显式设置 `EVONEXT_INTEGRATION=1`，运行 `pytest -m integration`。测试仅写合成对象，不自动删除已有数据；严禁对生产名字/凭据绕过校验。

当前 integration 测试只覆盖存储和 PG 回执；broker 重投、模型服务与 Langfuse 需要另外的环境验收。缺少配置不能用 mock 结果替代。

## 可替代性 Gate

1. 真包往返：至少覆盖 raw-only、原生动作、历史扩展、缺图、辅助图、版本 0、长轨迹；核对源文件/媒体摘要，不公开真实材料。
2. 旧读新、新读旧：逐消费者冻结格式与字段保真；HTTP 投影先审转换损失，再做目标端 readback。
3. 浏览器：导入、切换、固定步骤、截图、原始输出/实际执行区分、导出、401/500/断线和 200/2000 步导航。
4. 持久化：API/Worker 重启、重复消息、对象上传失败、Mongo 写失败、PG 回执冲突，逐项记录真实恢复结果。
5. 后续 Review/Case：多人 CAS、机器结果不覆盖人审、固定 locator 与旧版本可回溯。
6. 真实进化实验：状态恢复核验、新 trial、独立评估和完整分母；不能用本次存储测试宣称能力提升。

本轮没有编辑旧仓库、迁移旧数据、切换线上服务或发布模型。
