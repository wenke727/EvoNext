import type { Step } from "./client";

export const TIMELINE_PAGE_SIZE = 60;
export type TimelineEntry = { start: number; end: number; key: string };

// Fold only explicit retry records with bound screenshots. Missing evidence and
// human intervention stay visible; raw model retries do not imply a step retry.
export function retryEntries(steps: Step[], missing: readonly string[]): TimelineEntry[] {
  const absent = new Set(missing);
  const hasImage = (index: number) => !!steps[index]?.image && !absent.has(steps[index].image!);
  const entries: TimelineEntry[] = [];
  for (let start = 0; start < steps.length;) {
    let end = start;
    const pageEnd = Math.min(steps.length, (Math.floor(start / TIMELINE_PAGE_SIZE) + 1) * TIMELINE_PAGE_SIZE);
    if (steps[start].step_type === "retry" && hasImage(start)) {
      while (end + 1 < pageEnd && steps[end + 1].step_type === "retry" && hasImage(end + 1)) end++;
      if (end + 1 < pageEnd && steps[end + 1].step_type === "agent" && hasImage(end + 1)) end++;
    }
    entries.push({ start, end, key: `${start}:${end}` });
    start = end + 1;
  }
  return entries;
}

export function windowEntries(entries: TimelineEntry[], start: number, end: number) {
  return entries.filter(entry => entry.end >= start && entry.start < end).map(entry => ({
    ...entry,
    start: Math.max(start, entry.start),
    end: Math.min(end - 1, entry.end),
  }));
}

export function visiblePositions(entries: TimelineEntry[], expanded: ReadonlySet<string>) {
  return entries.flatMap(entry => expanded.has(entry.key)
    ? Array.from({ length: entry.end - entry.start + 1 }, (_, index) => entry.start + index)
    : [entry.end]);
}

export function visibleCursor(entries: TimelineEntry[], positions: number[], current: number) {
  const entry = entries.find(entry => current >= entry.start && current <= entry.end);
  return positions.indexOf(positions.includes(current) ? current : entry?.end ?? current);
}
