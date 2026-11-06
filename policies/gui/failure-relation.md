{% include 'shared.md' %}
比较两个失败证据窗口，不因文本相似、同一 App 或同名错误就判为同一根因。
窗口 A：{{ evidence_a }}
窗口 B：{{ evidence_b }}
给出关系 candidate_same_mechanism / related_symptom / unrelated / unknown，
并说明支持证据、反例、环境与版本差异。不合并、删除 Case，不修改原始数据。
本模板只提出分组建议，不授予治理操作权限；关系模型仍需独立校准。
