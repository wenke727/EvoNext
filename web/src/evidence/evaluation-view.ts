import type { Detail } from "./client";
import { projectEvaluation } from "./evaluation.ts";
import type { Binding } from "./evaluation";
import type {
  EvaluationView,
  Field,
  ResultSource,
} from "../workbench/evaluation/contracts";

function source(binding: Binding, detail: Detail): ResultSource {
  const raw = binding.raw;
  return {
    bindingLabel: binding.label,
    raw,
    provider: typeof raw.provider === "string" ? raw.provider : "",
    model: typeof raw.model_name === "string" ? raw.model_name : "",
    policyVersion:
      typeof raw.judge_policy_version === "string"
        ? raw.judge_policy_version
        : "",
    evaluatedAt: typeof raw.evaluated_at === "string" ? raw.evaluated_at : "",
    taskId: typeof raw.source_task_id === "string" ? raw.source_task_id : "",
    inputVersion:
      typeof raw.source_version === "number" ? raw.source_version : null,
    inputView: typeof raw.source_view === "string" ? raw.source_view : "",
    snapshotVersion: detail.source_version,
    relation:
      binding.relation === "snapshot"
        ? "same_snapshot"
        : binding.relation === "version"
          ? "same_version"
          : binding.relation,
  };
}
function rawField(value: unknown): Field[] {
  return [{ key: "source_raw", title: "完整来源结果", value }];
}

export function adaptEvaluationView(detail: Detail): EvaluationView {
  const projected = projectEvaluation(detail);
  return {
    taskId: detail.task_id,
    snapshotId: detail.snapshot_id,
    version:
      detail.source_version === null ? null : String(detail.source_version),
    knownSteps: detail.trajectory.traj.map((_, index) => index),
    machine: {
      carried: projected.machine.carried,
      statuses: projected.machine.statuses,
      statusCodes: projected.machine.statuses,
      provider:
        typeof projected.machine.raw.provider === "string"
          ? projected.machine.raw.provider
          : "",
      reasoning: projected.machine.reasoning,
      failureReasons: projected.machine.failures,
      source: source(projected.machine.binding, detail),
    },
    graders: projected.graders.map((grader) => ({
      key: grader.key,
      title: grader.title,
      version: grader.version,
      scope:
        grader.scope === "task"
          ? "task"
          : grader.scope === "step"
            ? "step"
            : "unknown",
      status: grader.status,
      summary: grader.summary,
      fields: rawField(grader.raw),
      source: source(grader.binding, detail),
      items: grader.items.map((item) => ({
        status: item.status,
        reason: item.reason,
        steps: [],
        evidence: [],
        references: item.references,
        fields: rawField(item.raw),
      })),
    })),
  };
}
