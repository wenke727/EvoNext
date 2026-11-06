# EvoNext

面向 GUI Agent 的轨迹工作台与能力进化控制面。重新实现内部结构，保留数据、事实语义和外部协作边界，不复制旧平台实现。

## 当前交付

这是 **M0/M1 工程底座**，不是已经完成生产替换的全功能平台。

已实现的纵向切片：OpenCUA JSON / ZIP 导入 → Mongo 不可变快照 → MinIO 媒体 → React 单步证据浏览 → JSON / ZIP 导出。另有旧平台 HTTP 桥接、PG 操作回执与 Alembic 迁移、Celery 校验 Worker、可配置模型客户端及 Langfuse generation 打点。内存模式只用于明确选择的本地演示和测试，生产配置不会失败后偷偷切换内存。

核心约束：

- 轨迹继续是 `task_id / instruction / traj`。现有扩展字段、原始模型输出、步骤身份和执行回执保留；不引入替代它的新轨迹格式。
- Mongo 保存轨迹事实；MinIO 保存对象字节；PG 保存本平台明确拥有的关系型控制记录。本轮只有 `evonext.operation_receipts`，不迁移旧平台数据库。
- 新快照使用独立 `evonext_` collection。旧数据可通过已有 HTTP API 按固定版本读取；不允许两套平台直接并发修改旧 Latest/History。
- ZIP 的原始 `trajectory.json`、`metadata.json` 和图片逐字节保留。快照 ID 是版本化字节包身份，不冒充原 Task ID 或旧版本号。
- 旧平台上传是 `traj → steps + multipart` 的显式投影，默认只预览；不能把 HTTP 成功当成无损同步或审核完成。
- 模型追踪使用 Langfuse，不另建模型时序/费用可视化平台。启动、导入、浏览和普通测试不调用付费模型或设备。

## 本地演示

Python 3.11+；前端使用 Node 22.12+。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
evonext serve --demo
```

Windows 的环境激活命令为 `.venv\Scripts\activate`。演示只绑定 localhost，重启后内存数据丢失；不能用它验收持久化。

另开终端：

```bash
cd web
npm install
npm run dev
```

打开本地 5173 端口，点击“连接”。演示不需要 API Key。导入 `examples/trajectory.json` 可体验缺图/缺证据的真实展示，不会伪造成功标签。

生成带 sidecar 的合成包：

```bash
mkdir -p .local
cd examples
python -m zipfile -c ../.local/synthetic.zip trajectory.json metadata.json
cd ..
evonext validate-bundle .local/synthetic.zip
```

## 接入现有基础设施

```bash
pip install -e '.[infra,tracing,dev]'
cp .env.example .env
# 填写 API Key 与已有 Mongo / MinIO / PG / Redis / Langfuse 地址和凭据。
# 明确创建隔离 MinIO bucket，并授予最小权限；应用不会自动建桶或改旧集合。
alembic upgrade head
evonext serve
# 可选：独立消费者，队列名与旧平台隔离。
celery -A evonext.worker:app worker -Q evonext.high,evonext.bulk --concurrency=2
```

`compose.yaml` 只定义新应用/Worker，不另部署或替换已有存储和 Langfuse。容器内 `127.0.0.1` 不是宿主机，必须设置容器可达的服务地址。`docker compose --profile worker up --build` 不等于获准连接生产库。

## 目录

```text
src/evonext/       应用、数据契约、存储适配、旧平台桥接、模型/追踪、Worker
web/              React + TypeScript + Vite 工作台
migrations/       本平台 PG schema 的显式 Alembic 迁移
schemas/          只读格式视图与评估结果的 JSON Schema
examples/         只有合成数据
tests/           离线契约测试及显式选择的基础设施联通测试
docs/            架构、兼容协议、交付路线、运维与验收边界
```

API 由 FastAPI 生成 `/openapi.json` 和 `/docs`。JSON 导入只保证结构不丢字段；需要原文件字节保真及图片可携带时，使用 ZIP 包。

## 测试与实现状态

```bash
pytest -q
python -m compileall -q src migrations
# 安装 dev 依赖后：
ruff check .
cd web && npm run build
```

创建本框架时，本地运行 **61 passed / 3 skipped**：两个 skip 是当前执行容器未安装 Langfuse/Celery 的真实 SDK 形状检查，一个是未配置隔离实库的 integration 测试。Python 语法编译已通过；这不代表真实 Mongo/MinIO/PG、Langfuse 送达、设备恢复或旧平台端到端已验收。

该执行容器无法访问包注册表，前端依赖安装/构建未在本地执行。CI 已定义 Python 3.11/3.12 契约测试、SDK 检查、lint 和前端构建；**以实际 Actions 结果为准，不将“配置了 CI”写成“CI 通过”**。依赖锁文件尚未生成，首次可联网构建后应提交锁定版本，再进入可复现部署验收。

## 文档入口

[架构](docs/ARCHITECTURE.md) · [兼容与互通](docs/COMPATIBILITY.md) · [完整能力路线](docs/ROADMAP.md) · [运维](docs/OPERATIONS.md) · [验收](docs/ACCEPTANCE.md)

这是公开仓库：不提交生产轨迹、截图、真实配置、密钥、内部主机信息或旧私有实现。项目许可证由仓库所有者另行决定；本次没有替所有者选择开源许可证。
