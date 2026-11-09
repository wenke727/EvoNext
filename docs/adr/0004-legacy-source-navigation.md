# ADR-004 · 旧源只读默认入口与顶部任务定位

状态：已实施（2026-11-08）。用户明确要求默认读取旧数据库，并把旧顶部导航按新架构迁入；这是对先前仅手动 HTTP 导入入口的增补，不授权旧集合写入、启动迁移或生产切换。

## 决定

前端保留现有 React 工作台，顶部以 Task ID／可选来源版本定位为主入口；导入和本地快照退入次级菜单。配置旧源后，启动页面自动只读列出旧任务；只有操作者打开任务时才读取完整版本及媒体，并交给新 Evidence owner 固定快照。搜索失败保留当前已打开证据。

`compat.mongo_source.LegacyMongoSource` 使用官方 PyMongo/MinIO 客户端，只暴露 list/fetch/capture；不导入旧 DAL，不创建索引、桶或迁移，不修改 Latest/History/Raw 或旧媒体。源配置通过显式受信 `EVONEXT_LEGACY_ENV_FILE` 引用本地 dotenv，仅消费命名的 Mongo/MinIO 键；配置路径与凭据不进入前端，不复制旧部署设置。没有配置时保持原有快照模式；配置失效时返回明确错误，不静默换数据源。

新捕获仍由 EvidenceService 接收，沿用新平台独立 Mongo/MinIO owner；本轮真实预览显式使用 localhost demo，所以新快照和媒体只存内存，重启丢失。没有对生产新库执行写入，也没有以此验收持久化或多人权限。

## 固定版本与字节边界

支持 profile `evoloop.mongo-read.v1`。留空版本读取一次 Latest 文档，并以文档中的明确版本固定；指定版本先读 History，再只允许同版本 Latest，不回退其他版本。版本 0、字符串 Task ID 与所有未知字段保留。Mongo BSON 没有原始 JSON 文件字节：使用带类型信息的 Extended JSON 投影，并将BSON Int64 及超出 JS 安全范围的整数表示为 `$numberLong`；这项转换在 sidecar 中声明，不假装原文件字节无变化。

原截图 locator 不改写；只用已配置 MinIO origin 下的图片桶及旧 VLM 桶（VLM_MINIO_BUCKET，旧约定默认 vlm-api） 读取无 URL 凭据、无 query/fragment 的对象，实际图片字节按 hash 绑定到固定快照。无法绑定的 locator 明确缺图，不访问任意来源 URL。读取受步骤数、单文件与总字节上限约束。保留原 URL 的该 profile 目前支持 JSON 导出；可移植 ZIP 需要单独显式 locator 投影，页面不提供会误导成功的包导出入口。

实际 API/CLI、合成测试和只读真实来源的验证见 ACCEPTANCE.md；协议范围只在 COMPATIBILITY.md 维护。
