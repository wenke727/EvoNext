# EvoNext

面向 GUI Agent 的轨迹工作台与能力进化控制面。重新实现内部结构，保留数据、事实语义和外部协作边界，不复制旧平台实现。

## 完整重构文档

[docs/rebuild/README.md](docs/rebuild/README.md) 已收录完整 PRD、领域合同、架构、API/工作台、迁移、AC-001–063、实施任务书和原合成合同样例；按 Mongo/MinIO/PG、OpenCUA、Langfuse 的最新约束修订。AIHOT/OpenClaw 借鉴与取舍见 [ADR-001](docs/adr/0001-aihot-openclaw.md)。

## 当前交付

这是 **M0/M1 工程底座**，不是已经完成生产替换的全功能平台。

**只读工作台阶段完成（2026-11-07）**：真实离线数据浏览、左栏、来源 ORM/grader、Grid/小图导航、重试折叠、marker、显示设置、快捷键与打点原文检索已验收收口。当前版本不宣称完整替代旧平台；真实 Langfuse 联通、编辑/审核、治理管道和其余低频字段留待独立工作包。范围、旧版差异与验证边界见 [验收记录](docs/ACCEPTANCE.md)。

已实现的基础纵向切片：OpenCUA JSON / ZIP 导入 → Mongo 不可变快照 → MinIO 媒体 → React 单步证据浏览 → JSON / ZIP 导出。另有旧平台 HTTP 桥接、PG 操作回执与 Alembic 迁移、Celery 校验 Worker、可配置模型客户端及 Langfuse generation 打点。新增本地 Skill 候选维护（版本/CAS/diff/Undo/固定导出）、Runtime 冻结消费与授权合同、严格策略模板、PG 收费调用恢复与请求预算。自动学习、实际设备执行和聚合引擎尚未接通。内存模式只用于明确选择的本地演示和测试，生产配置不会失败后偷偷切换内存。

核心约束：

- 轨迹继续是 `task_id / instruction / traj`。现有扩展字段、原始模型输出、步骤身份和执行回执保留；不引入替代它的新轨迹格式。
- Mongo 保存轨迹事实；MinIO 保存对象字节；PG 保存本平台明确拥有的关系型控制记录。当前包含操作回执与 `evonext.model_call_receipts`，不迁移旧平台数据库。
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
npm ci
npm run dev
```

打开本地 5173 端口，点击“连接”。演示不需要 API Key。导入 `examples/trajectory.json` 可体验缺图/缺证据的真实展示，不会伪造成功标签。

轨迹详情优先迁用旧 workbench 的 React 只读组件和原样式（[ADR-002](docs/adr/0002-workbench-ui-reuse.md)）：任务信息侧栏、可调整的小图条、Grid/单步、截图动作标记与近景、Agent 字段和固定底栏。Step 使用 0-based 显示序号；方向键定位，Grid 中 Enter 打开，Alt+G 切换，H/? 查看快捷键。小图默认在上方，可切换到底部。坐标显示配置可选 0–1000 / 图片像素 / 未声明，字段解析注明来源且不回写证据。Grid 分页与有限小图窗口避免一次加载全部图片；快照/步骤/view 固定链接可刷新读回。旧平台读取入口要求固定版本，截图仍需显式绑定。

左栏支持只读 ORM/grader 来源结果、统计筛选与按源步骤定位；图例、徽标和来源状态色共用证据投影。没有携带评估结果的真实离线包会明确说明缺失，不推断为未评估。可切换当前/下一步及包内已绑定媒体对照，未绑定的历史路径不会访问。当前支持范围和对照旧 React 的差异台账见 [验收记录](docs/ACCEPTANCE.md)。

生成带 sidecar 的合成包：

```bash
mkdir -p .local
cd examples
python -m zipfile -c ../.local/synthetic.zip trajectory.json metadata.json
cd ..
evonext validate-bundle .local/synthetic.zip
```

## 默认读取旧库与 ID 定位

配置 `EVONEXT_LEGACY_ENV_FILE=/absolute/local/path/to/EvoLoop/src/.env` 后，工作台默认显示旧 Mongo 任务列表，顶部可按 Task ID 打开；版本留空读取当前版本，填写 0 可定位版本零。Mongo/MinIO 仅只读访问，不运行旧 DAL 初始化或写入；完整读取结果由新 Evidence owner 固定。该 profile 与边界见 [ADR-004](docs/adr/0004-legacy-source-navigation.md) 和 [兼容合同](docs/COMPATIBILITY.md)。不要把旧配置文件或真实数据加入仓库。

本地只读预览可以继续使用 `evonext serve --demo`（新捕获仅存内存），前端 `npm run dev`。需要隔离端口时，后端指定 `--port 8001`，前端设置 `EVONEXT_API_PROXY=http://127.0.0.1:8001 npm run dev -- --port 5174`。顶部导入/本地快照仍作为次级入口保留。

CLI 使用 `evonext inspect-source --env-file /absolute/local/path/to/source.env --limit 10` 查看来源列表；增加 `--task-id TASK_ID --version 0` 可检查固定任务和截图读取，结果明确为临时内存检查，不持久化。需要安装声明的 infra 依赖。来源 URL 保持原样，当前只提供 JSON 导出；完整可移植 ZIP 的 locator 投影另行实现。

## 接入现有基础设施

```bash
pip install -e '.[infra,tracing,dev]'
cp .env.example .env
# 填写 API Key 与已有 Mongo / MinIO / PG / Redis / Langfuse 地址和凭据。
# 明确创建隔离 MinIO bucket，并授予最小权限；应用不会自动建桶或改旧集合。
alembic upgrade head
evonext serve
# 可选：独立消费者，队列名与旧平台隔离。
celery -A evonext.app.worker:app worker -Q evonext.high,evonext.bulk --concurrency=2
```

`compose.yaml` 只定义新应用/Worker，不另部署或替换已有存储和 Langfuse。容器内 `127.0.0.1` 不是宿主机，必须设置容器可达的服务地址。`docker compose --profile worker up --build` 不等于获准连接生产库。

## 目录

```text
src/evonext/
  app/            API / CLI / Worker 装配
  contracts/      数据与消费合同
  evidence/       证据、存储适配与统一导入用例
  operations/     操作回执与完整性检查
  providers/      模型、策略、收费回执与 Langfuse
  compat/         旧系统 HTTP 适配
  skills/workshop/ 候选方法维护，不放 offline
  runtime/        固定上下文/授权/恢复/消费合同
policies/gui/      可版本化的规则与 Prompt
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
cd web && npm test && npm run build
```

本轮离线测试和实际 CI 状态记录在 [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)。保留基线测试并增加分层、策略、调用恢复、Workshop 和 Runtime 合同回归。实库/设备/真实语义未测不得算通过；配置 CI 不等于本轮 CI 已通过。

本地候选操作与 Runtime 准备命令见 [08](docs/rebuild/08_SKILLS_RUNTIME_AND_PIPELINE.md)。`prepare-trial` 仅产计划，不执行。模型 probe 需要显式开启 `EVONEXT_MODEL_CALLS_ENABLED`、PG 迁移和稳定 `--operation-id`；同一请求复用已收到响应，结果未知不自动重发。

前端依赖已固定在 `web/package-lock.json`，使用 `npm ci` 安装。Python 依赖仍采用版本范围；可复现部署另行验收。

## 文档入口

[架构](docs/ARCHITECTURE.md) · [兼容与互通](docs/COMPATIBILITY.md) · [完整能力路线](docs/ROADMAP.md) · [运维](docs/OPERATIONS.md) · [验收](docs/ACCEPTANCE.md)

这是公开仓库：不提交生产轨迹、截图、真实配置、密钥、内部主机信息或旧私有实现。项目许可证由仓库所有者另行决定；本次没有替所有者选择开源许可证。
