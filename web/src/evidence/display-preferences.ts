export const DISPLAY_OPTIONS = [
  { key: "bbox", label: "坐标框（BBox）", group: "轨迹视图", default: false },
  { key: "time", label: "任务与采集时间", group: "任务信息", default: false },
  { key: "evaluation", label: "ORM / grader 评估结果", group: "任务信息", default: true },
  { key: "agent", label: "Agent 思考、动作与工具调用", group: "步骤字段", default: true },
  { key: "followup", label: "用户跟进", group: "步骤字段", default: true },
  { key: "rawOutput", label: "模型原始输出与此前回复", group: "步骤字段", default: true },
  { key: "execution", label: "实际执行记录与独立回执", group: "步骤字段", default: true },
  { key: "runtime", label: "Runtime / dispatch / 观测", group: "步骤字段", default: true },
  { key: "fullStep", label: "完整步骤原文", group: "步骤字段", default: true },
] as const;

export type DisplayKey = (typeof DISPLAY_OPTIONS)[number]["key"];
export type DisplayPreferences = Record<DisplayKey, boolean>;

// Persist only known display switches, never source content or credentials.
export function readDisplayPreferences(value: unknown): DisplayPreferences {
  const saved = value && typeof value === "object" ? value as Record<string, unknown> : {};
  return Object.fromEntries(DISPLAY_OPTIONS.map(option => [
    option.key,
    typeof saved[option.key] === "boolean" ? saved[option.key] : option.default,
  ])) as DisplayPreferences;
}
