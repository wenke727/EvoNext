# 09 · 步骤级 Case 与纠正工作台

此前在此评审的 v0.1 草稿已撤回。当前开发规格为 [PR #4 的 09 v0.3](https://github.com/wenke727/EvoNext/blob/13d834807e1a858c265dffc75fed415799d92d45/docs/rebuild/09_REVIEW_CORRECTION_WORKBENCH.md)。

每个 Case 对应固定快照中一个步骤上的一个问题，可细化至该步的模块调用或批量子动作。同一 Case 内的纠正候选全部绑定该步并逐项审核。其他步骤的纠正分别创建 Case，可引用同一失败事件或诊断。整体 Outcome 和首错调查由 Evaluation / Diagnosis 持有。
