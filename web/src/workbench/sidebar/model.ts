/** Sidebar projections never change the source trajectory or infer human verdicts. */
export type Task = Record<string, unknown>;
export const record = (value: unknown): Task =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Task)
    : {};
export const list = (value: unknown): unknown[] =>
  Array.isArray(value) ? value : [];
export const text = (value: unknown): string =>
  value == null
    ? ""
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);
export function parseRecord(value: unknown): Task {
  if (typeof value !== "string") return record(value);
  try {
    return record(JSON.parse(value));
  } catch {
    return {};
  }
}
export function guidance(task: Task): string {
  return text(record(record(task.metadata).pa_skill).content).trim();
}
export function instruction(task: Task): string {
  const source = typeof task.instruction === "string" ? task.instruction : "";
  const skill = guidance(task).replace(/\r\n?/g, "\n").trimEnd();
  const normalized = source.replace(/\r\n?/g, "\n").trimEnd();
  return skill && normalized.endsWith(skill)
    ? normalized.slice(0, -skill.length).trimEnd()
    : source;
}
export function rawInstruction(task: Task): string {
  const metadata = record(task.metadata);
  if (text(metadata.raw_instruction).trim())
    return text(metadata.raw_instruction).trim();
  for (const property of list(record(metadata.backflow_raw).input_properties)) {
    const item = record(property);
    const value =
      parseRecord(item.extInfo).mainPaTask ?? item["extInfo.mainPaTask"];
    if (text(value).trim()) return text(value).trim();
  }
  return "";
}
export function contextFlags(task: Task) {
  const metadata = record(task.metadata);
  const raw = record(metadata.backflow_raw);
  const outputs = list(raw.output_properties).map(record);
  const inputs = list(raw.input_properties).map(record);
  return {
    smallPa: outputs.some(
      (item) =>
        !!text(item.sessionId).trim() &&
        ["smallPaAgentRequest", "smallPaAgentResponse"].some(
          (key) =>
            Object.keys(parseRecord(parseRecord(item.extInfo)[key])).length > 0,
        ),
    ),
    paTrace:
      !!text(metadata.pa_trace_id).trim() ||
      inputs.some(
        (item) =>
          !!text(item.wsTraceId ?? parseRecord(item.extInfo).wsTraceId).trim(),
      ),
  };
}
export function createdAt(value: unknown): string {
  const source = text(value);
  if (!source) return "";
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(source)) return source;
  const date = new Date(source);
  if (Number.isNaN(date.getTime())) return source;
  return date.toLocaleString("sv-SE", { timeZone: "Asia/Shanghai" });
}
export function childItems(task: Task): Task[] {
  const lineage = record(task.lineage);
  return list(lineage.children ?? lineage.siblings)
    .map(record)
    .map((item, position) => ({ item, position }))
    .sort((a, b) => {
      const x = integer(a.item.ordinal),
        y = integer(b.item.ordinal);
      return x !== null && y !== null
        ? x - y || a.position - b.position
        : x !== null
          ? -1
          : y !== null
            ? 1
            : a.position - b.position;
    })
    .map((entry) => entry.item);
}
export function integer(value: unknown): number | null {
  if (
    !(typeof value === "number" || typeof value === "string") ||
    (typeof value === "string" && !value.trim())
  )
    return null;
  return Number.isInteger(Number(value)) ? Number(value) : null;
}
export function validRange(
  item: Task,
  count: number,
): { start: number | null; end: number | null; valid: boolean } {
  const range = record(item.step_range ?? item.source_step_range);
  const start = integer(range.start_step_index),
    end = integer(range.end_step_index);
  return {
    start,
    end,
    valid:
      start !== null &&
      start >= 0 &&
      start < count &&
      (end === null || (end >= start && end < count)),
  };
}
