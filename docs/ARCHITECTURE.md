# 架构与技术决策

状态：foundation；目标架构不等于全部功能已实现。

## 1. 产品边界

EvoNext 是 GUI Agent 的证据资产、审阅治理与改进实验控制面，不接管所有 Runtime、训练和模型服务。产品主线是：需求 → 执行证据 → 评估/诊断 → 人工确认问题 → 选择干预 → 新执行/独立验证 → 采用或撤回 → 下一轮证据。

内部采用模块化单体。API 和 Worker 是同一 Python 包的两种进程；前端只消费应用 API。一个领域只有一个业务写入权威，不因为页面、CLI、任务队列或模型不同就再建一份状态机。

```text
React 工作台 / CLI / 兼容客户端
                 |
          FastAPI 应用用例
          /       |       \
   Mongo 证据   MinIO 媒体   PG 控制记录
                 |
       Celery 独立消费者（显式任务）
                 |
      模型 / 评估器 / 外部执行端口
                 |
       Langfuse 模型 generation / trace
```

## 2. 存储职责

| 存储 | 本轮实现 | 后续职责与禁止事项 |
|---|---|---|
| Mongo | 一个新 collection 中原子保存不可变快照及其 metadata/media manifest；原 JSON 字符串保留字节 | 旧 Task/History/Raw 不修改。未来修订/Case 接入须先确定唯一 owner；不复制多套 latest 真值 |
| MinIO | 按 SHA-256 存图片字节；业务快照记录绑定 | 后续大文件、导出包；不把 presigned URL 当作永久身份，不自动重新压缩历史截图 |
| PostgreSQL | `evonext.operation_receipts`，显式 Alembic 迁移 | 实验关系、运行/结果账本及必要投影按实际切片增加；不复制整份轨迹或取代 Mongo |
| Redis / Celery | 已有 broker 上的独立 `evonext.high` / `evonext.bulk` 队列 | 只负责投递；业务事实由 Mongo/PG 持有，不把 Celery SUCCESS 当成 Agent 任务成功 |
| Langfuse | 模型 generation、usage、关联 ID；内容采集默认关闭 | 独立模型观测产品；不作为原始轨迹或审核结果唯一存储，不再造完整时序查看器 |

`MongoSnapshots` 的新 collection 是包装快照的内部存储，不是旧 Latest/History 的替代表结构。它保留原 trajectory JSON 字节，导出仍是原三字段主体及原有扩展字段。旧应用不会自动读取新 collection；互通通过包或显式 HTTP adapter 完成。

媒体先写 MinIO，完成校验后一次性写 Mongo manifest。失败允许留下未引用对象，但不返回完整导入成功；垃圾回收必须另有引用扫描和保留期，不能在失败路径删除可能被复用的对象。本轮无跨库事务假设，也不做同步双写。

## 3. 领域边界

| 领域 | 拥有 | 不拥有 |
|---|---|---|
| Evidence / Ingestion | 来源、原文、版本、媒体绑定与快照 | 人工批准或任务成功结论 |
| Review / Case | 人审修订、问题定位、认领分诊、失败闭环 | 修改原始执行事实、自动训练授权 |
| Evaluation / Diagnosis | 冻结输入、逐项判断、证据充分性、原因假设 | 恢复手机、生成已批准 Skill、生产发布 |
| Dataset / Governance | 冻结成员、用途与污染隔离、导出 manifest | 以动态 tag 替代版本化数据集 |
| Experiment / Improvement | 干预选择、baseline/candidate、完整分母、采用/回退记录 | 把模型自评或一次成功冒充普遍收益 |
| Runtime / Recovery adapter | 明确范围的执行请求及新 trial 接回 | 通过评估重试再次执行有副作用的操作 |
| Skill / Training adapter | 固定版本资产交接、消费与反馈引用 | 自己授予独立验收、训练或 serving 权限 |

这些是职责边界，不要求每个框预建一个服务或包。本轮没有建立空的 Review、Skill、Training “实现”。

## 4. 开源工具取舍

HTTP/Schema 使用 FastAPI/Pydantic，页面使用 React/TypeScript/Vite，存储使用 PyMongo、MinIO Python SDK、SQLAlchemy/Alembic，任务投递使用 Celery，模型观测使用 Langfuse。

模型客户端只是 HTTPX 的受控薄适配器，连接已有兼容服务。只有多供应商路由、配额和计费真的成为需求时才引入外部模型网关；不为“平台完整”预建一套。暂不引入第二种消息队列、Kubernetes、通用 DAG、全量事件溯源或向量数据库。检索需求明确后再接成熟检索工具。

## 5. Langfuse 边界

本轮选择 Python SDK `>=4.7,<5` 的 OTel generation 接口，是兼容部署的有意选择，不宣称它是最新主版本。官方兼容矩阵指出 SDK v4 可用于满足最低版本条件的旧自托管服务；SDK v5 有更高服务端要求。接入现有实例前必须核对服务端版本。

默认只记录模型身份、调用关联、用量和状态，不上传输入/输出正文；`EVONEXT_TRACE_CONTENT=true` 必须经数据使用范围确认。追踪失败不重跑模型，不修改业务结果，不吞掉真正的模型异常。缺失 usage 为未知，不填 0；当前代码不自行估造价格。

参考：
- https://langfuse.com/docs/compatibility
- https://langfuse.com/self-hosting/upgrade/versioning
- https://langfuse.com/docs/observability/sdk/instrumentation
- https://docs.celeryq.dev/en/stable/userguide/tasks.html
- https://github.com/xlang-ai/OpenCUA

## 6. 明确的基础阶段限制

当前为单 workspace/API Key 身份，不宣称多租户/RBAC 已完成；真实协作接入优先采用成熟身份系统，仍需落实来源级授权。列表以不可变快照 ID 分页，不定义旧 task 的 latest。详情目前整体读取，200/2000 步浏览与懒加载性能仍需专项验收。PG schema、Langfuse 端到端、broker 重投和目标环境接入不由内存测试代替。
