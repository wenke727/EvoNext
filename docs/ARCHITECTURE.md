# 架构入口

完整架构唯一维护在 [rebuild/03_ARCHITECTURE.md](rebuild/03_ARCHITECTURE.md)。

Skill/Runtime 与处理闭环见 [08](rebuild/08_SKILLS_RUNTIME_AND_PIPELINE.md)，AIHOT/OpenClaw 固定基线和采用/不采用理由见 [ADR-001](adr/0001-aihot-openclaw.md)。

当前源码从扁平文件调整为 app、contracts、evidence、operations、providers、compat、skills/workshop、runtime。Mongo/MinIO/PG 与 OpenCUA 交换不改；内部 Python import 路径不继续保留旧 shim。CLI `evonext` 和现有 HTTP 入口保留，Docker/Worker 启动模块随本次一起更新。

代码实现、假服务测试、实库联通和生产采用分别报告，见 [ACCEPTANCE](ACCEPTANCE.md)。
