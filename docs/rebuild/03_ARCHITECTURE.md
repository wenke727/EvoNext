# 03 · 目标架构、当前分层与存储权威

版本 0.2。模块化单体 + 独立 Worker；目录是一种可改进的组织方式，业务身份、写入责任和可观察行为才是硬约束。不能为每个名词再建一套服务、工厂或状态表。

## 1. 系统主线

```text
Rollout / 旧平台回流 / 文件 / 云端 batch
                    ↓
         Evidence 接入与来源冻结
                    ↓
       完整性检查 → 按需评估/诊断
                    ↓
         人工 Review / Case 确认
                    ↓
       最小干预与失败模式派生分组
          ↙                      ↘
 Skill Workshop 候选         Harness/Tool/Weight 等
          ↘                      ↙
        Runtime 固定上下文与受控新 Trial
                    ↓
           独立评价、采用/撤回
                    ↓
      数据集/技能反馈与下一轮执行证据
```

本图包含目标能力。当前真正可运行的部分见实施状态，不把箭头画出来当成集成完成。

## 2. 源码布局

```text
src/evonext/
  config.py                 启动配置；无隐式生产默认
  contracts/                轨迹/Skill/Runtime/结果传输合同
  app/                      HTTP、CLI、Worker 入口与装配
  evidence/                 导入、不可变快照、媒体与共享应用用例
  evaluation/               冻结 Outcome 请求、逐义务结果及单次执行
  operations/               操作回执与纯完整性验证
  providers/                模型传输、策略渲染、收费回执、Langfuse
  compat/                   旧平台和协议边界
  skills/
    workshop/               候选版本、编辑、diff、归档、Undo、固定导出
  runtime/                  会话/上下文/授权/回执边界；不依赖 Workshop 存储
policies/gui/               Prompt 与非秘密策略配置
web/                       React/TypeScript 工作台
migrations/                唯一 PG 迁移链
examples/                  现役可导入的合成样例
```

后续 Review、Evaluation、Dataset、Experiment 功能落地时按领域增加模块；现在不预建空目录。每个领域可以包含自身用例和基础设施适配，不强制再套 domain/application/infrastructure 三重目录。模块跨进程不是微服务要求。

`skills` 和 `runtime` 是同一 Python 包下的一级领域，与 `evidence`、`providers` 并列；不放 `offline`，不建立容易冲突的全局 Python 包 `skills`。根目录 `examples/skills` 是样例资源，不是第二个技能库。

OpenClaw 当前 runtime 位于 src/agents、传输位于 src/llm，Workshop 是 bundled plugin；本项目借鉴责任划分，不声称它原生采用 src/skills/workshop。详见 ADR 的固定源码基线。

## 3. 依赖方向

app → 所属业务用例 → contracts/端口；数据库和网络只在适配器中发生。contracts 不导入 app、providers、存储客户端。Runtime 只消费 SkillBundle/SkillRef，不导入 Workshop 库；Workshop 不调用设备、评分器或 Runtime。providers 不导入 app 或业务页面。前端只经 HTTP，不直连 Mongo/PG，也不获取服务端密钥。

前端迁用旧 workbench 已有 React 只读视图的范围及来源见 [ADR-002](../adr/0002-workbench-ui-reuse.md)。原视图和样式放在 web/src/workbench，新快照/认证/来源适配留在 evidence；不迁旧 DOM host、旧写入路径或后端。

前端由 App 负责会话/选中快照，独立工作台、评估、图例、来源上下文与证据对照组件消费纯读取投影。组件不依赖旧 DOM host 或 window 业务状态；来源评估读取 profile 不引入第二个评估事实 owner。

前端 evidence/EvidenceClient 统一证据 API 调用；MediaCache 只管理会话内媒体请求和临时 Blob，不持有业务事实或解释旧来源 URL。轨迹视图只消费该客户端，后端 SnapshotRepository/AssetStore 仍是事实/字节的访问端口，不增加跨库通用 ORM/DAL。

DAL 最小读取设计见 [ADR-003](../adr/0003-evidence-data-access.md)：SnapshotRepository 合并提供原文、轻量 index 与列表，AssetStore 管字节；先消除概要/图片路径的全文读取。步骤投影按测量决定，导入恢复独立后置；实施证据见 ACCEPTANCE。

同一个导入用例由 EvidenceService 持有，HTTP 只做限流/认证/参数和响应。Worker 只投递和调用已注册的业务函数。CLI 不能成为绕过验证与访问控制的隐藏写路径。架构测试检查核心导入方向与读取无副作用；它不是任意运行时行为的形式证明。

## 4. 存储分工——已决，不再重新选型

| 事实/产物 | 权威位置 | 约束 |
|---|---|---|
| 原始轨迹、Task 快照与版本来源 | Mongo | 保留 OpenCUA JSON 与原字段；新 collection 隔离；旧 latest/history/raw 不被直接双写 |
| 图片、冻结包、较大产物 | MinIO | 字节/hash/version 明确，签名 URL 只是 locator；不重压历史图片冒充原 bytes |
| 操作、收费调用、实验/运行/数据集关系 | PostgreSQL | 每类事实一个 owner；不复制整份轨迹；只追加本平台 schema 的迁移 |
| 本地 Skill 候选 | 明确 owner 的 Workshop 文件目录 | 成熟 FileLock + 原子指针；不可变 revision；不是多机分布式生产库 |
| 队列 | Celery / 既有 Redis | 传 ID；不是任务成功、评分或审核权威 |
| 模型观测 | Langfuse | trace/usage/版本关联；不是设备状态或业务事实源 |

当前 Mongo wrapper 保存原 JSON 字符串和摘要以支持 byte-preserving 包；它不要求所有查询都解析全文。新增 App/model/source/Case/评价索引应为按快照绑定的可重建投影，不改变 OpenCUA 交换格式，不再造第二个 Task 真值。

MinIO 上传在前，Mongo manifest 原子接受在后。失败可以留下待核对的未引用对象，不能先把不完整任务显示为成功，也不能立即删掉可能被别的快照复用的 hash 对象。Mongo/PG/MinIO 之间不假定分布式事务；明确 owner、receipt、补核对与保留期。

本地 Workshop 只支持一个受信 owner 的本地持久目录；同目录检查 owner，跨进程通过 FileLock 和 expected_revision 保护。网络文件系统、多主机锁、权限继承及备份恢复另行验收。后续接已有 Workshop 时使用同一 SkillBundle，不并行维护两份活跃资产。

## 5. 模型调用与恢复

供应商调用先固定操作身份、scope、输入 hash、endpoint/model、policy hash、repetition_id 和输出预算。PG 在短事务中按账户/部署 scope 锁定预算检查与发送占位；事务结束后才网络请求。响应先写 PG，再解析和写业务结果。

同 key 的 received 响应复用，不重复计费；malformed JSON 或非 2xx 也先保留原响应，不为了让解析通过自动重新调用。sending/unknown 不自动重发；需操作员核对或明确的新尝试身份。PG 写入异常不能触发模型补跑。新独立评分使用新的 repetition_id；缓存命中不计独立样本。

当前预算是每分钟/小时/日的请求数，以及输入字节、输出 token 上限；不是精确货币预算。scope 默认覆盖部署的全部模型，避免换模型绕过限额。缺失 usage/cost 保持未知。原响应会进入授权 PG 的受限账本，即使 Langfuse 正文采集关闭也是如此；上线前必须配置访问控制、脱敏/保留和删除策略。

没有 provider exactly-once 保证。timeout 可能已计费；sending 长期不结束也不能自行判断供应商没收到。当前没有自动 reconcile UI 或陈旧请求放行任务。收到响应后的解析可以重复，设备副作用不能照用此重试策略。

## 6. 策略与成熟工具

Prompt/规则文件在 policies 下，Jinja2 SandboxedEnvironment + StrictUndefined 只渲染已审查本地模板，静态 includes 有路径/循环/数量限制。policy 版本覆盖全部模板依赖及非秘密 config；最终输入另算 hash。可信模板不是用户可上传执行的代码。修改后产生新身份，不改历史结果。

Git 是初始规则编辑源。Langfuse Prompt 发布/版本标签和实验比较是后续可复用能力；本轮尚未实现自动发布同步，不能声称存在两套自动一致的编辑器。默认不采集模型输入输出正文；追踪故障不能吞业务异常或重跑调用。

FastAPI/Pydantic、React/TypeScript/Vite、PyMongo、MinIO SDK、SQLAlchemy/Alembic、Celery、Langfuse、Jinja2/PyYAML/FileLock 分别承担成熟基础能力。AIHOT 的 TypeScript/pg-boss 不进入 Python 主线。暂不引入全量 workflow/DAG、第二 Broker、知识图谱、向量数据库或动态插件市场。

## 7. 业务异步边界与规模

完整 Import/Evaluation/Experiment 状态各自由领域拥有；收费回执只管外部调用，不替代业务 Run。一个 Request 不再外套一个重复真值的 Job。模型调用期间不持 DB 锁。纯评估 retry 复用冻结执行证据，不再次操作设备。已保存 Record 而摘要投影失败，只补投影。

本地 target 为具体 device，云 target 为 batch 资源，两者分开表达；资源租约、抢占、复位和实际并行度由执行 owner 负责。API 不阻塞等待长执行。当前 Runtime 仅 prepare 与 grant/receipt 验证，不提供已执行假回执。

性能目标保留原 06：50/200/2000 步、1k/10k 请求与分页实测；禁止每项完成重写全量批次或对每个 grader 复制所有图文。阈值是待测目标，不继承 AIHOT 的生产跑分。

## 8. 访问与生产切换

现役 API Key 是单 workspace 管理身份，不是完整 RBAC。多源数据与多人审阅接入前必须落实来源级权限、撤权、签名媒体、删除与审计。业务回执与原输出同样受访问限制；哈希不是匿名化。

两平台互通先经完整包和已冻结 HTTP 合同；不要直接并发写旧库。原始 JSON/图片的无损保存不证明旧系统已经能读所有新控制记录。迁移与反向互通、readback、单写切换和回滚均按 05/06 单独验证。
