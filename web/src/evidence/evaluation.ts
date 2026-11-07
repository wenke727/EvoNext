import type { Detail } from "./client";

export type Binding = {
  relation:
    | "snapshot"
    | "version"
    | "other_task"
    | "other_version"
    | "other_snapshot"
    | "unknown";
  label: string;
  raw: Record<string, unknown>;
};
export type ResultRef = {
  label: string;
  position: number | null;
  reason?: string;
};
export type Judgment = {
  status: boolean | null | undefined;
  reason: string;
  references: ResultRef[];
  raw: unknown;
};
export type GraderView = {
  key: string;
  title: string;
  version: string;
  scope: string;
  summary: string;
  status: boolean | null | undefined;
  binding: Binding;
  items: Judgment[];
  raw: Record<string, unknown>;
};
export type EvaluationView = {
  carried: boolean;
  machine: {
    carried: boolean;
    statuses: string[];
    reasoning: string;
    failures: string[];
    binding: Binding;
    raw: Record<string, unknown>;
  };
  graders: GraderView[];
  raw: unknown;
};
export const record = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
const string = (value: unknown) => (typeof value === "string" ? value : "");
const strings = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : typeof value === "string"
      ? [value]
      : [];
const version = (value: unknown) =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0
    ? value
    : null;

export function resultBinding(
  source: Record<string, unknown>,
  detail: Detail,
): Binding {
  const raw = {
    source_snapshot_id: source.source_snapshot_id,
    source_task_id: source.source_task_id,
    source_version: source.source_version,
    source_view: source.source_view,
    provider: source.provider,
    model_name: source.model_name,
    judge_policy_version: source.judge_policy_version,
    evaluated_at: source.evaluated_at,
  };
  const task = string(source.source_task_id);
  const snapshot = string(source.source_snapshot_id);
  const sourceVersion = version(source.source_version);
  if (task && task !== detail.task_id)
    return { relation: "other_task", label: "其他任务 · 参考结果", raw };
  if (snapshot && snapshot !== detail.snapshot_id)
    return { relation: "other_snapshot", label: "其他快照 · 参考结果", raw };
  if (
    sourceVersion !== null &&
    detail.source_version !== null &&
    sourceVersion !== detail.source_version
  )
    return { relation: "other_version", label: "其他版本 · 参考结果", raw };
  if (snapshot === detail.snapshot_id)
    return { relation: "snapshot", label: "已绑定当前快照", raw };
  if (
    task === detail.task_id &&
    sourceVersion !== null &&
    sourceVersion === detail.source_version
  )
    return {
      relation: "version",
      label: `来源版本 ${sourceVersion} 一致 · 输入快照未核对`,
      raw,
    };
  return { relation: "unknown", label: "输入关联未核对 · 参考结果", raw };
}

function resolveReferences(
  item: Record<string, unknown>,
  detail: Detail,
  binding: Binding,
): ResultRef[] {
  const refs: ResultRef[] = [];
  for (const key of [
    "step_indices",
    "evidence_step_indices",
    "step_ids",
  ] as const) {
    if (!Array.isArray(item[key])) continue;
    for (const identity of item[key]) {
      const id = key === "step_ids";
      if (
        id
          ? typeof identity !== "string"
          : typeof identity !== "number" ||
            !Number.isSafeInteger(identity) ||
            identity < 0
      )
        continue;
      const label = `${key === "evidence_step_indices" ? "证据 " : ""}${id ? "step_id" : "源 index"} ${identity}`;
      const positions = detail.trajectory.traj.flatMap((step, ordinal) =>
        (id ? step.step_id : step.index) === identity ? [ordinal] : [],
      );
      const position = positions.length === 1 ? positions[0] : null;
      if (binding.relation !== "snapshot" && binding.relation !== "version")
        refs.push({
          label,
          position: null,
          reason: "未绑定当前输入快照，不跳转到当前步骤",
        });
      else if (position === null)
        refs.push({
          label,
          position: null,
          reason: positions.length ? "步骤身份不唯一" : "当前快照无此步骤身份",
        });
      else
        refs.push({
          label: `Step ${position} · ${label}${binding.relation === "version" ? " · 来源参考" : ""}`,
          position,
        });
    }
  }
  return refs;
}

// Supported source view: trajectory.evaluation.prediction / graders. Source evidence stays intact.
export function projectEvaluation(detail: Detail): EvaluationView {
  const source = detail.trajectory.evaluation;
  const raw = record(source);
  const prediction = record(raw.prediction);
  const graders: GraderView[] = [];
  if (Array.isArray(raw.graders))
    raw.graders.forEach((value, index) => {
      const grader = record(value);
      if (!Object.keys(grader).length) return;
      const binding = resultBinding(grader, detail);
      const items: Judgment[] = [];
      if (Array.isArray(grader.items))
        for (const entry of grader.items) {
          const item = record(entry);
          items.push({
            status:
              typeof item.status === "boolean"
                ? item.status
                : item.status === null
                  ? null
                  : undefined,
            reason: string(item.reason),
            references: resolveReferences(item, detail, binding),
            raw: entry,
          });
        }
      graders.push({
        key: `${string(grader.key) || "grader"}:${index}`,
        title:
          string(grader.title) || string(grader.key) || `专项 ${index + 1}`,
        version: string(grader.version),
        scope: string(grader.scope) || "未声明",
        status:
          typeof grader.status === "boolean" || grader.status === null
            ? grader.status
            : undefined,
        summary: string(grader.summary),
        binding,
        items,
        raw: grader,
      });
    });
  return {
    carried: source !== undefined && source !== null,
    machine: {
      carried: raw.prediction !== undefined && raw.prediction !== null,
      statuses: strings(prediction.task_status),
      reasoning: string(prediction.reasoning),
      failures: strings(prediction.failure_reason),
      binding: resultBinding(prediction, detail),
      raw: prediction,
    },
    graders,
    raw: source,
  };
}
