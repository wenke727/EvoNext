{% include 'shared.md' %}
逐项检查以下固定任务义务；不增删义务，不用一项完成代替全部完成。
任务义务：{{ obligations }}
实际交付证据：{{ evidence }}
返回 JSON：checks[{check_id,judgment,reason,evidence_refs}]。
judgment 为 pass/fail/unknown/not_applicable/not_assessed。
本模板是待校准的初始策略，不是已验收的评估器。
所有义务均为必需项，每个 check_id 恰好返回一次。所有 pass/fail 必须引用交付的 evidence_id。
只按输入中声明的时间关系解释截图，不能将动作前帧重命名为执行后态。仅对图像能够支持的义务判断；缺派发历史、过程约束或后态时保留 unknown。
输入没有原 Agent 的输出与过程，本 profile 不评价回复内容、动作是否执行或中途改令。未能看到的事实不能推断成功。
每个检查都给 reason 和 evidence_refs。无法判定使用 unknown，不使用 not_applicable 跳过必需义务。
