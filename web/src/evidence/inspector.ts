import type { Detail, Step } from "./client";

export type RawField = { key: string; path: string[]; value: unknown; json: string };
function rawField(path: string[], value: unknown): RawField {
  return {key:path.join("."),path,value,json:JSON.stringify(value,null,2)};
}
export function inspectorFields(step: Step): RawField[] {
  return Object.entries(step).map(([key,value]) => rawField([key],value));
}
export function filterInspectorFields(fields: RawField[], query: string) {
  const needle=query.trim().toLocaleLowerCase();
  if (!needle) return fields;
  const matches: RawField[]=[];
  function visit(path: string[], value: unknown) {
    if(path.join(".").toLocaleLowerCase().includes(needle)) {
      matches.push(rawField(path,value));
    } else if(value !== null && typeof value === "object") {
      for(const [key,child] of Object.entries(value)) visit([...path,key],child);
    } else if(JSON.stringify(value)?.toLocaleLowerCase().includes(needle)) {
      matches.push(rawField(path,value));
    }
  }
  for(const field of fields) visit(field.path,field.value);
  return matches;
}

export function safeTraceUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  try {
    const url=new URL(value);
    if (!["https:","http:"].includes(url.protocol) || url.username || url.password) return null;
    return url.href;
  } catch { return null; }
}

export type TraceReference = { source: string; position: number; traceId: string | null; observationId: string | null; url: string | null; raw: unknown };
const identity=(value: unknown) => typeof value === "string" && value.length > 0 ? value
  : typeof value === "number" && Number.isSafeInteger(value) ? String(value) : null;
const record=(value: unknown): Record<string,unknown> => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string,unknown> : {};

// Source references only. Never derive a trace URL from Task ID, step ordinal or IDs.
export function traceReferences(detail: Detail, position: number | null): TraceReference[] {
  const steps=position === null ? detail.trajectory.traj.map((step,index)=>({step,index}))
    : detail.trajectory.traj[position] ? [{step:detail.trajectory.traj[position],index:position}] : [];
  const references: TraceReference[]=[];
  for(const {step,index} of steps) {
    const runtime=record(step.runtime);
    for(const [source,raw] of [["trace_ref",step.trace_ref],["runtime.trace_ref",runtime.trace_ref]] as const) {
      if(raw == null) continue;
      const fields=record(raw);
      references.push({source:`traj[${index}].${source}`,position:index,
        traceId:identity(typeof raw === "string" ? raw : fields.trace_id),
        observationId:identity(fields.observation_id),url:safeTraceUrl(fields.url),raw});
    }
  }
  return references;
}
