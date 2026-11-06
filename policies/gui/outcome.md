{% include 'shared.md' %}
逐项检查以下固定任务义务；不增删义务，不用一项完成代替全部完成。
任务义务：{{ obligations }}
实际交付证据：{{ evidence }}
返回 JSON：checks[{check_id,judgment,reason,evidence_refs}]。
judgment 为 pass/fail/unknown/not_applicable/not_assessed。
本模板是待校准的初始策略，不是已验收的评估器。
