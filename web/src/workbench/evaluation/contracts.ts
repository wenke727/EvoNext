/** Read-only view contract. Canonical evaluation and writes remain server-owned. */
export type Field = { key?: string; title?: string; value?: unknown };
export type Judgment = {
  status: boolean | null | undefined;
  reason: string;
  steps: number[];
  evidence: number[];
  fields: Field[];
  references?: { label: string; position: number | null; reason?: string }[];
};
export type Grader = {
  key: string;
  title: string;
  version?: string;
  scope: "task" | "step" | "unknown";
  status?: boolean | null;
  summary: string;
  fields: Field[];
  items: Judgment[];
  source: ResultSource;
};
export type EvaluationView = {
  taskId: string;
  snapshotId: string;
  version: string | null;
  knownSteps: number[];
  machine: {
    carried: boolean;
    statuses: string[];
    statusCodes: string[];
    provider: string;
    reasoning: string;
    failureReasons: string[];
    source: ResultSource;
  };
  graders: Grader[];
};
export type ResultFilter = "issues" | "false" | "null" | "true" | "undefined";
export type ViewState = {
  open: string | null;
  filter: ResultFilter;
};
export type ResultSource = {
  bindingLabel?: string;
  raw?: unknown;
  provider: string;
  model: string;
  policyVersion: string;
  evaluatedAt: string;
  taskId: string;
  inputVersion: number | null;
  inputView: string;
  snapshotVersion: number | null;
  relation:
    | "same_snapshot"
    | "same_version"
    | "other_version"
    | "other_task"
    | "other_snapshot"
    | "unknown";
};
export const initialState = (): ViewState => ({
  open: null,
  filter: "issues",
});

export function hasValue(value: unknown): boolean {
  if (value == null) return false;
  if (typeof value === "string") return value.trim() !== "";
  if (Array.isArray(value)) return value.some(hasValue);
  if (typeof value === "object") return Object.values(value).some(hasValue);
  return (
    typeof value === "boolean" ||
    (typeof value === "number" && Number.isFinite(value))
  );
}
export function text(value: unknown): string {
  const raw =
    value == null
      ? ""
      : typeof value === "object"
        ? JSON.stringify(value, null, 2)
        : String(value);
  return raw;
}
