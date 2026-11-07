import { useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import type { Detail } from "./client";
import { inspectorFields, filterInspectorFields, traceReferences, type RawField } from "./inspector";
import "./inspector.css";

function RawNode({ field, searching }: { field: RawField; searching: boolean }) {
  const [open,setOpen]=useState(false);
  const kind=field.value === null ? "null" : Array.isArray(field.value) ? `Array(${field.value.length})` : typeof field.value;
  return <details className="inspector-node" open={searching || open} onToggle={event=>setOpen(event.currentTarget.open)}>
    <summary><code>{field.key}</code><span>{kind}</span></summary>
    {(searching || open) && <pre>{field.json}</pre>}
  </details>;
}

export function EvidenceInspector({ detail, position, width, onStep, onClose, onReload, onResize, onWidth }: {
  detail: Detail;
  position: number;
  width: number;
  onStep: (position: number) => void;
  onClose: () => void;
  onReload: () => void;
  onResize: (event: PointerEvent<HTMLDivElement>) => void;
  onWidth: (width: number) => void;
}) {
  const [view,setView]=useState<"raw"|"trace">("raw");
  const [scope,setScope]=useState<"step"|"task">("step");
  const [query,setQuery]=useState("");
  const [notice,setNotice]=useState("");
  const search=useRef<HTMLInputElement>(null);
  const close=useRef<HTMLButtonElement>(null);
  const tabs=useRef<HTMLDivElement>(null);
  const step=detail.trajectory.traj[position];
  const fields=useMemo(()=>step ? inspectorFields(step) : [],[step]);
  const filtered=useMemo(()=>filterInspectorFields(fields,query),[fields,query]);
  const references=useMemo(()=>view === "trace" ? traceReferences(detail,scope === "task" ? null : position) : [],[detail,position,scope,view]);
  useEffect(()=>{close.current?.focus();},[]);
  useEffect(()=>{setNotice("");},[position,view]);
  async function copy(value: string) {
    try { await navigator.clipboard.writeText(value);setNotice("已复制"); }
    catch { setNotice("无法访问剪贴板，可选择原文复制"); }
  }
  return <aside className="evidence-inspector" aria-label="打点详情" onKeyDown={event=>{
    if(event.nativeEvent.isComposing) return;
    if(event.key === "Escape") {event.preventDefault();event.stopPropagation();onClose();}
    if((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "f" && view === "raw") {
      event.preventDefault();event.stopPropagation();search.current?.focus();
    }
  }}>
    <div className="inspector-resizer" role="separator" tabIndex={0} aria-label="调整打点面板宽度" aria-orientation="vertical"
      aria-valuemin={320} aria-valuemax={720} aria-valuenow={width} onPointerDown={onResize} onKeyDown={event=>{
        if(["ArrowLeft","ArrowRight"].includes(event.key)) {
          event.preventDefault();event.stopPropagation();onWidth(width+(event.key === "ArrowLeft" ? 20 : -20));
        }
      }} />
    <header className="inspector-header">
      <strong>打点</strong><span>Step {position}</span>
      <button aria-label="打点上一步" disabled={position<=0} onClick={()=>onStep(position-1)}>‹</button>
      <button aria-label="打点下一步" disabled={position>=detail.step_count-1} onClick={()=>onStep(position+1)}>›</button>
      <button onClick={onReload}>刷新</button>
      <button ref={close} aria-label="关闭打点" aria-keyshortcuts="Escape" onClick={onClose}>×</button>
    </header>
    <div className="inspector-tabs" ref={tabs} role="tablist" aria-label="步骤详情视图" onKeyDown={event=>{
      if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key)) return;
      event.preventDefault();event.stopPropagation();
      const next=event.key === "Home" ? "raw" : event.key === "End" ? "trace" : view === "raw" ? "trace" : "raw";
      setView(next);tabs.current?.querySelector<HTMLButtonElement>(`[data-view="${next}"]`)?.focus();
    }}>
      {([['raw','打点数据'],['trace','模块 log']] as const).map(([key,label])=><button key={key} data-view={key}
        id={`inspector-${key}-tab`} role="tab" aria-selected={view===key} aria-controls={`inspector-${key}-panel`}
        tabIndex={view===key ? 0 : -1} onClick={()=>setView(key)}>{label}</button>)}
    </div>
    <p className="inspector-source">固定来源版本 {detail.source_version ?? "未知"} · {detail.snapshot_id.slice(0,8)}</p>
    {view === "raw" ? <section id="inspector-raw-panel" role="tabpanel" aria-labelledby="inspector-raw-tab" className="inspector-content">
      <div className="inspector-search"><input ref={search} type="search" aria-label="搜索打点数据" placeholder="搜索字段或原文" value={query} onChange={event=>setQuery(event.target.value)} />
        {query && <button onClick={()=>setQuery("")}>清除</button>}
      </div>
      <div className="inspector-actions"><span>{filtered.length} 个{query ? "匹配" : "源"}字段</span><button disabled={!step} onClick={()=>copy(JSON.stringify(step,null,2))}>复制步骤 JSON</button></div>
      <p className="inspector-hint">按源字段展示；提案、执行记录与回执各自保留。</p>
      {filtered.map(field=><RawNode key={JSON.stringify([position,field.path])} field={field} searching={query.trim().length>0} />)}
      {!filtered.length && <p className="inspector-empty">没有匹配的来源字段。</p>}
    </section> : <section id="inspector-trace-panel" role="tabpanel" aria-labelledby="inspector-trace-tab" className="inspector-content">
      <div className="inspector-scope" role="group" aria-label="追踪范围">
        <button aria-pressed={scope === "step"} onClick={()=>setScope("step")}>当前步</button>
        <button aria-pressed={scope === "task"} onClick={()=>setScope("task")}>全任务</button>
      </div>
      <p className="inspector-hint">模块调用细节在来源追踪服务中查看；此处只列出包内引用，尚未核验远端内容。</p>
      {!references.length && <p className="inspector-empty">当前来源未携带{scope === "step" ? "本步" : "任务步骤"}追踪引用。打点数据仍可查看。</p>}
      {references.map(reference=><section className="inspector-trace-ref" key={reference.source}>
        <div><button onClick={()=>onStep(reference.position)}>Step {reference.position}</button><code>{reference.source}</code></div>
        <dl><dt>Trace ID</dt><dd>{reference.traceId ?? "未记录"}</dd><dt>Observation ID</dt><dd>{reference.observationId ?? "未记录"}</dd></dl>
        {reference.url ? <a href={reference.url} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">打开来源追踪 ↗</a> : <p className="inspector-hint">未携带可用的追踪链接。</p>}
        {reference.traceId !== null && <button onClick={()=>copy(reference.traceId!)}>复制 Trace ID</button>}
        <details><summary>引用原文</summary><pre>{JSON.stringify(reference.raw,null,2)}</pre></details>
      </section>)}
    </section>}
    <p className="inspector-notice" role="status">{notice}</p>
  </aside>;
}
