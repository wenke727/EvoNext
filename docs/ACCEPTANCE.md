# 实施状态与验收证据

本页是当前交付事实；`docs/rebuild/` 是全量目标。测试通过不能替代语义质量、目标环境或生产替换签署。

## 本轮本地检查

环境：Python 3.13.5；当前离线容器不能解析 GitHub 或访问依赖注册表。工作树基线取用户提供的源码包，原始 Git tree 为 `7179532604aeb5cfa9b2d0109cf8becf1e2c30e9`，与远端 `c887ac5` 一致，避免在未知副本上修改。

提交前执行 `PYTHONPATH=src pytest -q`：**104 passed / 3 skipped**。保留全部基线行为测试，并增加分层依赖、政策版本、收费调用恢复/预算、Workshop CAS/Undo/hash、Runtime 冻结/权限/回执及原规格示例校验。`python -m compileall -q src migrations` 通过；`docs/rebuild/examples/validate_examples.py` 验证 9 份 JSON 合同样例的身份、hash、分母和 Gold 隔离。

3 个 skip 是未安装 Langfuse/Celery 的真实 SDK 形状检查与未配置隔离真实存储的 integration 测试。没有偷偷用内存结果替代实库。

## 本轮可用范围

| 部分 | 已写且离线验证 | 仍未完成 |
|---|---|---|
| 重构文档 | 完整 00–08、原 AC-001–063/SEC-01–06、合成样例、来源摘要和 ADR | 全部目标能力的实施与生产签署 |
| 分层 | app/contracts/evidence/operations/providers/compat/skills/runtime；旧扁平实现路径退出 | 使用旧 Python 启动路径的外部脚本需要更新 |
| 数据链 | 原 JSON/ZIP 导入浏览导出与 HTTP 兼容行为回归；共用 EvidenceService | 真实旧新往返、多人权限、2000 步浏览器体验 |
| Policy | 依赖内容 hash、严格变量/静态 include、冻结配置、禁止 secret config | 正式 grader 校准、自动发布到 Langfuse |
| 模型调用 | 发送前回执、received 复用、unknown 不重发、独立 repetition、预算原子规则；真实 PG adapter/migration 已写 | PG 多进程/断电/重启/超时真实故障验收，货币计费、自动 reconciliation UI |
| Workshop | 候选 create/patch/no_change、CAS、history/diff、archive/Undo、owner/hash 校验和固定导出 CLI | 模型学习/视觉复核/merge、反馈 UI、多人生产权限、独立质量 |
| Runtime | none/raw/skill 固定上下文、local/cloud target、恢复请求、精确 grant、回执关联 | 实际设备 adapter、会话持久执行/租约、复位/teacher rollout、独立效果 |
| 失败聚合 | 版本化关系模板与禁止自动合并 Case 的合同 | 候选检索、聚合引擎、人工分组与校准 |

## CI 的准确口径

基线 `c887ac5` 的 GitHub Actions 曾通过 Python 3.11/3.12、63 项非实库测试、Ruff 和前端构建。本轮创建提交时不得把基线成功挪用为新提交结果；新结果以对应 commit 的 Actions 为准。本地未执行 Ruff/前端构建/Docker build，不能记为通过。

## 隔离服务与后续 Gate

实库测试必须显式 `EVONEXT_INTEGRATION=1` 并使用含 test 的隔离数据库/bucket，先运行本平台 Alembic。现有实库测试不覆盖完整模型回执、资源租约或真机恢复。

下一步：真实脱敏 OpenCUA 往返 → 浏览器/持久化与兼容验收 → Review/Case → 一个独立 Outcome grader → 受控 Skill/Runtime 新 trial。Runtime prepare、签名/关联核验和文件 Undo 都不证明手机恢复成功。

本轮没有改变旧平台、写入生产数据库、执行付费模型/真机、训练或生产发布。PG 新迁移未在目标环境执行。原始模型响应将持久存于授权 PG，必须补访问与保留策略后才能生产启用。
