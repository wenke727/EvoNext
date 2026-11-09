# 配置、部署与故障边界

## 安全默认

正式模式必须设置 API Key，不会匿名开放业务数据。当前是单 workspace 管理密钥，不是完整多租户身份体系。公网部署还需 TLS/网关、限流、来源级权限、备份和审计验收。演示只用于 localhost 的合成数据，不能连生产或用作多用户服务。

密钥和地址由 `.env`/环境变量提供，绝不能使用 `VITE_*` 变量把服务端秘密编译到浏览器。前端 API Key 仅驻留当前页面内存，不放 URL/query/localStorage。日志不得打印模型输入、认证头或连接串。

## 存储初始化

模型 HTTP 请求的字节预算与模型 token 上下文是不同限制。网关使用
`EVONEXT_MODEL_MAX_REQUEST_BYTES`（默认 1 MiB），评估请求使用
`max_request_bytes`（默认 950 KiB，初始评分及追加取证共用）；均允许显式设置至
16 MiB。实际请求必须同时满足两处限制，计入 JSON、文本、base64 图片及消息历史。
增加字节预算不代表模型支持更多 token；图片仍需声明编码、缩放和原始来源。

连接现有服务，但使用隔离的 Mongo collection、MinIO bucket 和 PG `evonext` schema 开始验收。API 不会自动迁移旧库、创建 bucket 或修改旧索引。操作员显式创建 bucket 并配置访问策略；`alembic upgrade head` 只管理本平台回执表及独立版本表。

Mongo 快照单文档原子接受；图片已上传而快照失败时留下可核对的未引用对象。不要同步删除对象“回滚”，因为同 hash 的图片可能已被其他快照引用。未来 GC 需要保留期、完整引用扫描与单独授权。

当前 JSON 成员上限 8 MiB、完整 ZIP/展开总量 64 MiB、单快照 JSON 合计 12 MiB；Media manifest 额外占用 Mongo BSON 空间。大规模生产轨迹应通过单独的大对象/流式切片验收，不直接无限调大限制。

## 队列与回执

运行 `evonext enqueue-integrity <snapshot_id>` 只提交一个可重算的完整性校验，不调用模型或设备。Worker 校验冻结内容和绑定媒体，向 PG 写 `storage_integrity.v1` 回执；`agent_outcome` 始终为 `not_assessed`。

使用 Celery 传 ID、独立队列和有限技术重试。重复计算可以发生，确定性 operation_id 的同内容写入幂等，异内容冲突不覆盖。Broker 提交成功不是业务任务完成；当前没有通用 Job UI 或自动补投平台，需通过回执核对，未取得回执时显式检查/重新投递这个纯校验任务。不得把同样重试策略直接用于手机支付、外部发布或训练任务。

默认不开 `task_reject_on_worker_lost` 的无限重投；主机/消费者强杀场景须在后续真实 broker 验收中补齐可核对的操作规程。没有 exactly-once 模型调用或外部副作用保证。

## Langfuse

先核对现有服务版本，再开启 `EVONEXT_LANGFUSE_ENABLED=true`。本项目 SDK v4 使用 generation/OTel 路径；不调用旧 trace/generation ingestion API。若实例不满足官方最低版本，不自动替用户升级服务器。

模型调用仅由显式 `evonext model-probe --operation-id <stable-id> --text "..."` 或后续应用用例触发。probe 会真实调用配置的模型并可能计费；本次没有执行。`EVONEXT_TRACE_CONTENT=false` 是默认值，开启正文采集前确认数据授权和脱敏策略。Langfuse 不可用时业务结果不能被重复推理；关闭进程时 flush，具体送达仍需目标环境验收。

## 前端与服务

开发用 Vite 代理 `/api`、`/health` 到本地 8000。生产应构建静态文件并由现有网关/Nginx 同源托管；不把 Vite dev server 当生产服务器。本轮未附带新的整套网关、证书或身份平台。

Docker 构建与 npm 依赖安装需要可联网环境。首次成功安装后固定 Python 和 npm 锁文件，并记录镜像 digest，再验收可复现部署。不要因为版本范围能解析就宣称依赖供应链已审计。

## 诊断与恢复

`/health/live` 只证明进程存活；鉴权后的 `/health/ready` 分项检查持久资源，不代表业务全链路或生产签署。PG configured 时会核对回执表可读，而不仅是 TCP 可连接。缺服务返回 unavailable，不静默改内存。

旧平台 POST 响应丢失属于结果不确定，先按目标 Task ID 和来源核对，不自动重发或覆盖。演示数据丢失是已声明的易失性，不是恢复能力。所有旧数据库迁移、生产发布、批量修复和 destructive cleanup 都不属于本次默认操作。

## 本轮增加的模型回执与本地资源

模型调用默认关闭；显式设置 EVONEXT_MODEL_CALLS_ENABLED=true，并执行 Alembic 0002，才能让正式 ModelGateway 发送。已收到的响应包含原始内容，保存在授权 PG 账本，即使 Langfuse trace_content=false 也是如此。上线前设置账本权限、脱敏/保留策略和备份；本轮没有自动清理任务。3 个请求数预算共享稳定 deployment/account scope；不是精确费用限额。

sending/unknown 不自动过期重发，也没有自动 reconciliation UI。先核对供应商请求/业务记录，再决定显式新尝试身份。应用无法保证供应商 exactly-once。收到的无效 JSON 与非 2xx 也保留，不反复付费直到解析成功。

Workshop 使用明确 owner 和本地 FileLock，不支持未经验证的 NFS 多主机锁。目录不应由不可信用户同时修改；此本地模型不是完整远程 ACL。restore 是候选版本恢复，不是手机状态回滚。

启动路径已变为 evonext.app.api:create_app / evonext.app.worker:app。使用旧模块路径的 systemd/脚本须显式更新；HTTP 路径与 evonext CLI 名称未改。未部署到旧生产环境。
ModelGateway preserves a 4096 output-token default. A caller can explicitly
configure `model_max_output_tokens` (up to 32768) and provide temperature or
reasoning_effort for a reviewed model experiment. Generation options are part
of the exact request hash and receipt identity; they do not enable paid calls.
