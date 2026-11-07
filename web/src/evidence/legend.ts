import type { Detail, Step } from "./client";
import { projectStep } from "./projection.ts";
import { record } from "./evaluation.ts";
export const LEGEND = {
  current: {
    label: "当前步骤",
    hint: "当前打开的步骤或 Grid 光标，不代表正确或通过",
    icon: "□",
    color: "#0d6efd",
  },
  sourceCorrect: {
    label: "来源正确标记",
    hint: "value.last_step_correct=true；不是新评估或人工审核",
    icon: "✓",
    color: "#28a745",
  },
  sourceError: {
    label: "来源错误标记",
    hint: "来源 error/error_reason 字段；不自动判为任务失败",
    icon: "✕",
    color: "#dc3545",
  },
  takeover: {
    label: "接管记录",
    hint: "来源 take_over 或 Runtime 明确接管记录",
    icon: "◇",
    color: "#d89a18",
  },
  takeoverProposal: {
    label: "接管提案",
    hint: "模型提出接管，不等于实际已接管",
    icon: "◇",
    color: "#d89a18",
  },
  multiEnd: {
    label: "多终止点",
    hint: "同一轨迹存在多个 terminate 提案，不自动判为错误",
    icon: "◆",
    color: "#0ea5b7",
  },
  followup: {
    label: "用户跟进",
    hint: "来源 user_interrupt 字段有内容",
    icon: "▤",
    color: "#777777",
  },
  human: {
    label: "主动操控",
    hint: "来源 step_type=human；不补造期间设备操作",
    icon: "♧",
    color: "#777777",
  },
  retry: {
    label: "重试记录",
    hint: "来源 step_type=retry 或 Runtime 重试记录",
    icon: "↻",
    color: "#777777",
  },
  modelRetry: {
    label: "模型重试",
    hint: "存在 rejected_model_outputs，原始失败回复仍保留",
    icon: "↻",
    color: "#777777",
  },
  security: {
    label: "来源安全标记",
    hint: "Runtime security_flag=true；不从图片外观推断",
    icon: "▣",
    color: "#555555",
  },
  teacher: {
    label: "Teacher 来源",
    hint: "存在明确 Teacher 辅助/来源记录，不表示已独立验证",
    icon: "T",
    color: "#9d713a",
  },
  risk: {
    label: "风控记录",
    hint: "Runtime 携带 risk_control 记录；详见步骤原文",
    icon: "△",
    color: "#b26a40",
  },
  missing: {
    label: "缺图",
    hint: "当前步骤缺少截图或媒体未绑定，不以相邻图片填补",
    icon: "⊘",
    color: "#999999",
  },
} as const;
export type LegendKind = keyof typeof LEGEND;
const meaningful = (value: unknown) =>
  typeof value === "string" ? value.trim().length > 0 : value === true;
export function stepSignals(
  step: Step,
  detail: Pick<Detail, "missing_media">,
  multipleEndings: boolean,
): LegendKind[] {
  const flags: LegendKind[] = [];
  const value = step.value ?? {};
  const runtime = record(step.runtime);
  const teacher = record(value.raw_teacher_proposal);
  const actions = projectStep(step).actions;
  if (value.last_step_correct === true) flags.push("sourceCorrect");
  if (meaningful(value.error) || meaningful(value.error_reason))
    flags.push("sourceError");
  const dispatched = record(
    runtime.dispatched_action ?? runtime.executed_action,
  );
  if (
    step.take_over === true ||
    ["take_over", "takeover"].includes(String(dispatched.action))
  )
    flags.push("takeover");
  else if (
    actions.some((action) => ["take_over", "takeover"].includes(action.kind))
  )
    flags.push("takeoverProposal");
  if (multipleEndings && actions.some((action) => action.kind === "terminate"))
    flags.push("multiEnd");
  if (
    meaningful(step.user_interrupt) ||
    Object.keys(record(step.user_interrupt)).length
  )
    flags.push("followup");
  if (step.step_type === "human") flags.push("human");
  if (
    step.step_type === "retry" ||
    meaningful(runtime.retry) ||
    Object.keys(record(runtime.retry)).length
  )
    flags.push("retry");
  if (
    Array.isArray(value.rejected_model_outputs) &&
    value.rejected_model_outputs.length
  )
    flags.push("modelRetry");
  if (runtime.security_flag === true) flags.push("security");
  if (
    step.teacher_assist === true ||
    value.teacher_assist === true ||
    teacher.source === "teacher" ||
    (typeof teacher.proposal_id === "string" && teacher.proposal_id.length)
  )
    flags.push("teacher");
  if (
    Array.isArray(runtime.risk_control) &&
    runtime.risk_control.some((item) => Object.keys(record(item)).length)
  )
    flags.push("risk");
  if (!step.image || detail.missing_media.includes(step.image))
    flags.push("missing");
  return flags;
}
export function trajectorySignals(detail: Detail) {
  const multiple =
    detail.trajectory.traj.filter((step) =>
      projectStep(step).actions.some((action) => action.kind === "terminate"),
    ).length > 1;
  const steps = detail.trajectory.traj.map((step) =>
    stepSignals(step, detail, multiple),
  );
  const present = new Set<LegendKind>(steps.flat());
  return {
    steps,
    legend: (Object.keys(LEGEND) as LegendKind[]).filter(
      (kind) => kind === "current" || present.has(kind),
    ),
  };
}
