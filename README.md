# EvoNext

面向 GUI Agent 的轨迹工作台与能力进化控制面。重新实现内部结构，保留数据、事实语义和外部协作边界，不复制旧平台实现。

## 完整重构文档

[docs/rebuild/README.md](docs/rebuild/README.md) 已收录完整 PRD、领域合同、架构、API/工作台、迁移、AC-001–063、实施任务书和原合成合同样例；按 Mongo/MinIO/PG、OpenCUA、Langfuse 的最新约束修订。AIHOT/OpenClaw 借鉴与取舍见 [ADR-001](docs/adr/0001-aihot-openclaw.md)。

## 当前交付

后续顺位统一见 [当前路线图](docs/ROADMAP.md)，Workshop 的标准召回、按需取证、短指南及任务收尾/空闲双触发设计见 [模块合同 §10](docs/rebuild/08_SKILLS_RUNTIME_AND_PIPELINE.md#10-标准学习闭环相关经验召回按需取证与短指南目标规格)。手工触发的标准学习首片已接通，后台双触发仍为目标；当前交付以 ACCEPTANCE 为准。

这是 **M0/M1 工程底座**，不是已经完成生产替换的全功能平台。

**只读工作台阶段完成（2026-11-07）**：真实离线数据浏览、左栏、来源 ORM/grader、Grid/小图导航、重试折叠、marker、显示设置、快捷键与打点原文检索已验收收口。当前版本不宣称完整替代旧平台；真实 Langfuse 联通、编辑/审核、治理管道和其余低频字段留待独立工作包。范围、旧版差异与验证边界见 [验收记录](docs/ACCEPTANCE.md)。

已实现的基础纵向切片：OpenCUA JSON / ZIP 导入 → Mongo 不可变快照 → MinIO 媒体 → React 单步证据浏览 → JSON / ZIP 导出。另有旧平台 HTTP 桥接、PG 操作回执与 Alembic 迁移、Celery 校验 Worker、可配置模型客户端及 Langfuse generation 打点。本地 Skill Workshop 提供多文件候选、草稿复核/CAS 提交、显式学习与精简、版本/diff/Undo/固定导出；Runtime 消费冻结合同。学习复用 PG 收费回执、请求预算和 Celery，模型结果不自动提交。后台自主学习、实际设备执行和聚合引擎尚未接通。内存模式只用于明确选择的本地演示和测试，生产配置不会失败后偷偷切换内存。

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

工作台底栏“评估输入预览”可核对完整轨迹步数、首轮图片选择与缺证。API 使用 `POST /api/v1/snapshots/{snapshot_id}/evaluation-input`，请求体 `{}` 使用默认策略；可配置 `images`（auto/all/last_three）、`include_think`、`max_images` 和 `max_text_bytes`。CLI 使用 `evonext prepare-evaluation examples/trajectory.json` 或传入可移植 ZIP。预览负责输入准备，Fast Judge 的实际运行入口见下文，有界 Investigator 的模式与离线验证入口见文末。

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

顶部 **Skill Workshop** 打开候选库和草稿箱。设置 `EVONEXT_WORKSHOP_ROOT` 为明确的本地绝对目录，并配置 `EVONEXT_WORKSHOP_OWNER`、`EVONEXT_REVIEW_OPERATOR_ID`；API 与 Worker 须在同一主机共享该目录。手工编辑、逐文件 diff、复核和提交无需模型。显式学习/精简还需要 PG、Celery 和已启用的 gateway；步骤、可选截图与固定 Case 审核版本由操作者选择，先预览再提交。CLI `evonext workshop-api` 复用相同 HTTP 用例。完整请求与边界见 [Workshop 操作合同](docs/rebuild/08_SKILLS_RUNTIME_AND_PIPELINE.md#9-workshop-草稿学习与精简)。

“从相关经验学习”只需任务主题或已注册的来源快照：自动检索相关来源、选连续步骤，并允许模型按需读取已绑定截图。默认 4 条、最多 8 条；预览显示实际条数、独立来源族、缺额、来源标签与请求字节。Skill ID 留空时查找已有方法，存在明确匹配则基于固定版本修补；歧义需要指定 ID。模型产物留在草稿箱，提交候选仍是单独操作。

```bash
# learning.json: {"operation_id":"stable-learning-id","topic":"账号主页的作品排序","source_limit":4}
evonext workshop-api learning-preview --file learning.json
# 明确开启模型、PG 回执和 Worker 后提交；恢复时复用同一个文件和 operation_id。
evonext workshop-api learn --file learning.json
evonext workshop-api status --id stable-learning-id
```

当前检索只覆盖已注册工作区的有界快照范围，采用词项重合，不承诺语义检索质量。尚未连接任务结束、空闲整理、设备执行或自动采用；详细限制见 [§10.8](docs/rebuild/08_SKILLS_RUNTIME_AND_PIPELINE.md#108-手工触发首片的现役合同)。

前端依赖已固定在 `web/package-lock.json`，使用 `npm ci` 安装。Python 依赖仍采用版本范围；可复现部署另行验收。

## 文档入口

[架构](docs/ARCHITECTURE.md) · [兼容与互通](docs/COMPATIBILITY.md) · [完整能力路线](docs/ROADMAP.md) · [运维](docs/OPERATIONS.md) · [验收](docs/ACCEPTANCE.md)

这是公开仓库：不提交生产轨迹、截图、真实配置、密钥、内部主机信息或旧私有实现。项目许可证由仓库所有者另行决定；本次没有替所有者选择开源许可证。

Fast Judge 首片可通过 `evonext evaluate <snapshot_id> --operation-id <stable-id>` 执行。HTTP 使用 `POST /api/v1/snapshots/{snapshot_id}/evaluations`，请求体包含 `operation_id`，可附 `options` 和 `obligations`（检查 ID 到完成标准的映射）。默认以原任务指令作为一项义务。`GET /api/v1/evaluations/{operation_id}` 读回状态与结果。HTTP 提交需现有 Celery Worker 消费 `evonext.bulk`，CLI 同步执行。须配置持久存储和模型凭据并显式启用模型调用；同一 operation_id 用于恢复已有请求，needs_attention 应先核对收费回执。前端输入弹窗提供运行和读回入口。真实服务及语义校准的未验范围见 ACCEPTANCE。

核心调查支持 `investigation=auto/off/always`，默认对未知结果追加取证；always 可搭配 `focus_positions` 调查指定步骤。工作台输入弹窗可选择调查当前步骤。CLI 可执行 `evonext evaluate <snapshot_id> --operation-id <stable-id> --investigation always`。无需业务 PG 的离线合成验证使用 `evonext replay-evaluation examples/trajectory.json --responses examples/synthetic-evaluation-responses.json`。重放输出明确标记合成模型；真实模型语义质量另行校准。
