import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { PointerEvent } from "react";
import type { CaseDecision, CaseView, Detail, EvidenceClient } from "./client";
import { imagePoint, rectangle } from "./correction";
import type { CorrectionDraft, CorrectionItem, FrozenReview, Region, SavedDraft, UsePreview } from "./correction";

export function CorrectionEditor({ item, detail, client, onClose, onReviewed }: {
  item: CaseView; detail: Detail; client: EvidenceClient;
  onClose: () => void; onReviewed: (result: CaseView) => void;
}) {
  const [saved, setSaved] = useState<SavedDraft | null>(null);
  const [draft, setDraft] = useState<CorrectionDraft>({note: "", items: []});
  const [head, setHead] = useState(item);
  const [selected, setSelected] = useState(0);
  const [tool, setTool] = useState<Region["role"] | "point">("original_target");
  const [url, setUrl] = useState("");
  const [size, setSize] = useState({width: 0, height: 0});
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [history, setHistory] = useState<FrozenReview | null>(null);
  const [preview, setPreview] = useState<UsePreview | null>(null);
  const [remote, setRemote] = useState<SavedDraft | null>(null);
  const [drag, setDrag] = useState<number[] | null>(null);
  const origin = useRef<number[] | null>(null);
  const saveCommand = useRef<Parameters<EvidenceClient["saveCorrections"]>[1] | null>(null);
  const reviewCommand = useRef<Parameters<EvidenceClient["reviewCorrections"]>[1] | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const reviewControls = useRef<HTMLDivElement>(null);
  const step = detail.trajectory.traj[item.position];
  const path = step?.image;
  const hash = path ? detail.manifest?.media[path] : undefined;
  const current = draft.items[selected];
  const dirty = saved !== null && JSON.stringify(draft) !== JSON.stringify(saved.draft);
  const drawable = !!(url && hash && size.width && current);
  const editing = dirty || busy || !!saveCommand.current || !!reviewCommand.current;

  useEffect(() => {
    dialog.current?.showModal();
    const controller = new AbortController();
    Promise.all([
      client.correctionDraft(item.case_id, controller.signal),
      client.request("/api/v1/cases/" + item.case_id, {signal: controller.signal})
        .then(response => response.json() as Promise<CaseView>),
    ]).then(([result, fullCase]) => {
      if (!controller.signal.aborted) {
        setSaved(result); setDraft(result.draft); setHead(fullCase);
      }
    }).catch(e => { if (!controller.signal.aborted) setError(String(e)); });
    return () => controller.abort();
  }, [client, item.case_id]);

  useEffect(() => {
    if (!path || detail.missing_media.includes(path)) return;
    let live = true;
    let objectUrl = "";
    const lease = client.media.acquire(detail.snapshot_id, path);
    lease.promise.then(blob => {
      if (live) { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl); }
    }).catch(e => { if (live) setError(String(e)); });
    return () => { live = false; lease.release(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [client, detail.snapshot_id, path]);

  useEffect(() => {
    const protect = (event: BeforeUnloadEvent) => {
      if (editing) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", protect);
    return () => window.removeEventListener("beforeunload", protect);
  }, [editing]);

  function close() {
    if (busy) return;
    if (editing && !window.confirm("有未保存编辑或待核对请求，确定离开？")) return;
    onClose();
  }
  function update(change: Partial<CorrectionItem>) {
    setDraft(value => ({...value, items: value.items.map((entry, index) =>
      index === selected ? {...entry, ...change} : entry)}));
    setPreview(null);
  }
  function add() {
    const next: CorrectionItem = {
      item_id: crypto.randomUUID(), position: item.position,
      source_step_id: item.source_step_id, source_action_stage: "unknown", source_action_ref: null,
      kind: "no_action", regions: [], suggested_action: null, verdict: "not_reviewed", reason: "",
    };
    setSelected(draft.items.length);
    setDraft(value => ({...value, items: [...value.items, next]}));
  }
  function point(event: PointerEvent<SVGSVGElement>) {
    return imagePoint(event.clientX, event.clientY, event.currentTarget.getBoundingClientRect());
  }
  function finish(event: PointerEvent<SVGSVGElement>) {
    if (!origin.current || !current) return;
    const start = origin.current;
    origin.current = null;
    setDrag(null);
    const end = point(event);
    if (tool === "point") {
      update({kind: "action_correction",
        suggested_action: {action: "click", space: "normalized_1000", point: end}});
      return;
    }
    const box = rectangle(start, end);
    if (!box || !path || !hash) return;
    if (current.regions.length >= 8) { setError("每个候选最多 8 个框"); return; }
    update({kind: current.suggested_action ? "action_correction" : "region_only",
      regions: [...current.regions, {role: tool, space: "normalized_1000", xyxy: box,
        media_locator: path, media_sha256: hash, image_width: size.width,
        image_height: size.height, orientation_profile: "upright_v1"}]});
  }
  async function save() {
    if (!saved) return;
    setBusy(true); setError(""); setNotice("");
    if (!saveCommand.current) saveCommand.current = {
      command_id: crypto.randomUUID(), expected_draft_revision: saved.draft_revision,
      draft: structuredClone(draft),
    };
    try {
      const result = await client.saveCorrections(item.case_id, saveCommand.current);
      setSaved(result); setDraft(result.draft); setRemote(null); saveCommand.current = null;
      setNotice("草稿已保存，可刷新读回");
    } catch (e) {
      setError(String(e) + "。保留当前编辑；重试会核对同一请求。");
    } finally { setBusy(false); }
  }
  async function compare() {
    setBusy(true); setError("");
    try {
      const result = await client.correctionDraft(item.case_id);
      const response = await client.request("/api/v1/cases/" + item.case_id);
      const next: CaseView = await response.json();
      setRemote(result); setHead(next);
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function review(decision: CaseDecision) {
    if (!saved || dirty || reason.trim().length < 8) {
      setError("先保存当前草稿，并填写至少 8 个字符的审核理由"); return;
    }
    setBusy(true); setError("");
    if (!reviewCommand.current) reviewCommand.current = {
      command_id: crypto.randomUUID(), expected_review_revision: head.review_revision,
      draft_revision: saved.draft_revision, draft_hash: saved.draft_hash,
      decision, reason: reason.trim(),
    };
    try {
      const result = await client.reviewCorrections(item.case_id, reviewCommand.current);
      setHead(result); onReviewed(result);
      setHistory(await client.frozenReview(item.case_id, result.review_revision));
      setPreview(null); reviewCommand.current = null;
      setNotice("已冻结所见草稿，追加操作员审核记录");
    } catch (e) { setError(String(e) + "。请重试同一审核，或读取服务端版本比较。"); }
    finally { setBusy(false); }
  }
  async function readReview(revision: number) {
    setBusy(true); setError("");
    try { setHistory(await client.frozenReview(item.case_id, revision)); setPreview(null); }
    catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function readPreview(purpose: string) {
    if (!history) return;
    setBusy(true); setError("");
    try { setPreview(await client.correctionPreview(item.case_id, history.revision, purpose)); }
    catch (e) { setError(String(e)); } finally { setBusy(false); }
  }

  return createPortal(<dialog ref={dialog} className="correction-dialog" aria-label="步骤纠正与审核"
    onCancel={event => {event.preventDefault(); close();}}>
    <header><div><h2>Step {item.position} · 纠正与审核</h2>
      <p>{item.summary}</p><small>快照 {detail.snapshot_id.slice(0, 12)} · Case {item.case_id.slice(0, 8)}</small></div>
      <button disabled={busy} onClick={close}>关闭</button></header>
    {error && <p role="alert" className="case-error">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <div className="correction-layout">
      <section>
        <div className="case-actions">
          {(["original_target", "suggested_target", "point"] as const).map((value, index) =>
            <button key={value} aria-pressed={tool === value} disabled={busy}
              onClick={() => setTool(value)}>{["框原目标", "框建议目标", "指定点击"][index]}</button>)}
          <button onClick={() => reviewControls.current?.scrollIntoView({block: "start"})}>前往审核</button>
        </div>
        <p>选择候选后在动作前原图绘制。点击位置需单独指定。坐标范围 0–1000。</p>
        {url ? <div className="correction-image">
          <img src={url} alt={"步骤 " + item.position + " 动作前原图"}
            onError={() => {setSize({width: 0, height: 0}); setError("原图无法解码，几何标注待核对");}}
            onLoad={event => setSize({width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight})}/>
          <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-label="原图标注画布"
            style={{pointerEvents: drawable && !busy && !saveCommand.current && !reviewCommand.current ? "auto" : "none"}}
            onPointerDown={event => {
              if (event.button !== 0) return;
              event.currentTarget.setPointerCapture(event.pointerId);
              origin.current = point(event); setDrag([...origin.current, ...origin.current]);
            }}
            onPointerMove={event => { if (origin.current) setDrag(rectangle(origin.current, point(event))); }}
            onPointerUp={finish}
            onPointerCancel={() => {origin.current = null; setDrag(null);}}>
            {current?.regions.map((region, index) => <rect key={index}
              x={region.xyxy[0]} y={region.xyxy[1]} width={region.xyxy[2] - region.xyxy[0]}
              height={region.xyxy[3] - region.xyxy[1]}
              className={region.role}/>)}
            {current?.suggested_action && <circle cx={current.suggested_action.point[0]}
              cy={current.suggested_action.point[1]} r="10" className="click-point"/>}
            {drag && <rect x={drag[0]} y={drag[1]} width={drag[2] - drag[0]} height={drag[3] - drag[1]} className="drawing"/>}
          </svg>
        </div> : <p>动作前原图不可用，可以保存文字判断。</p>}
        {!hash && <p>缺少媒体摘要，几何标注待核对。</p>}
        <details><summary>该步骤原始证据</summary><pre>{JSON.stringify(step, null, 2)}</pre></details>
      </section>
      <section aria-label="纠正候选">
        <fieldset disabled={busy || !saved || !!saveCommand.current || !!reviewCommand.current}>
          <label>审核备注<textarea value={draft.note} maxLength={4000}
            onChange={event => setDraft({...draft, note: event.target.value})}/></label>
          <div className="case-actions">{draft.items.map((entry, index) =>
            <button key={entry.item_id} aria-pressed={selected === index}
              onClick={() => setSelected(index)}>候选 {index + 1}</button>)}
            <button disabled={draft.items.length >= 16} onClick={add}>添加同一步候选</button></div>
          {current && <>
            <label>动作依据<select value={current.source_action_stage} onChange={event => {
              const stage = event.target.value as CorrectionItem["source_action_stage"];
              update({source_action_stage: stage, source_action_ref:
                stage === "unknown" ? null : stage === "runtime_dispatch" ? "runtime.dispatched_action" :
                  stage === "resolved_action" ? "value.tool_call" :
                    step.value?.tool_call != null ? "value.tool_call" : "value.raw_model_output"});
            }}>
              <option value="unknown">未知 / 待核对</option><option value="model_proposal">模型提案</option>
              <option value="resolved_action">解析后动作</option><option value="runtime_dispatch">实际派发</option>
            </select></label>
            {current.regions.map((region, index) => <div className="correction-region" key={index}>
              <strong>{region.role === "original_target" ? "原目标" : "建议目标"} {index + 1}</strong>
              <div>{region.xyxy.map((coordinate, axis) => <label key={axis}>{["x1", "y1", "x2", "y2"][axis]}
                <input type="number" min="0" max="1000" step="any" value={Number(coordinate.toFixed(3))}
                  onChange={event => update({regions: current.regions.map((box, i) => i === index ?
                    {...box, xyxy: box.xyxy.map((v, j) => j === axis ? Number(event.target.value) : v)} : box)})}/></label>)}</div>
              <button onClick={() => {
                const regions = current.regions.filter((_, i) => i !== index);
                update({regions, kind: current.suggested_action ? "action_correction" : regions.length ? "region_only" : "no_action"});
              }}>删除框 {index + 1}</button>
            </div>)}
            {current.suggested_action && <div className="correction-region"><strong>建议点击</strong>
              {current.suggested_action.point.map((value, axis) => <label key={axis}>{axis ? "y" : "x"}
                <input type="number" min="0" max="1000" step="any" value={Number(value.toFixed(3))}
                  onChange={event => update({suggested_action: {...current.suggested_action!,
                    point: current.suggested_action!.point.map((v, i) => i === axis ? Number(event.target.value) : v)}})}/></label>)}
              <button onClick={() => update({suggested_action: null, kind: current.regions.length ? "region_only" : "no_action"})}>清除点击</button>
            </div>}
            <label>候选判断<select value={current.verdict} onChange={event => update({verdict: event.target.value as CorrectionItem["verdict"]})}>
              <option value="not_reviewed">未审核</option><option value="accepted">认可</option>
              <option value="rejected">驳回</option><option value="unknown">无法判断</option></select></label>
            <label>候选理由<textarea maxLength={2000} value={current.reason}
              onChange={event => update({reason: event.target.value})}/></label>
            <button onClick={() => {setDraft({...draft, items: draft.items.filter((_, i) => i !== selected)}); setSelected(0);}}>删除当前候选</button>
          </>}
        </fieldset>
        <button disabled={busy || !saved || !!reviewCommand.current} onClick={() => void save()}>
          {saveCommand.current ? "重试同一保存" : "保存纠正草稿"}</button>
        <span> 草稿 r{saved?.draft_revision ?? "…"} {dirty ? "· 未保存" : ""}</span>
        <button disabled={busy} onClick={() => void compare()}>读取服务端版本比较</button>
        {remote && <div className="correction-conflict">
          <p>当前编辑保留在上方。服务端草稿 r{remote.draft_revision}，审核 r{head.review_revision}。</p>
          <details open><summary>服务端草稿</summary><pre>{JSON.stringify(remote.draft, null, 2)}</pre></details>
          <button disabled={busy} onClick={() => {
            setSaved(remote); setRemote(null); saveCommand.current = null; reviewCommand.current = null;
            setNotice("已采用服务端基准；请比较上方编辑，再保存并重新审核");
          }}>保留我的编辑，使用此版本重新提交</button>
          <button disabled={busy} onClick={() => {
            if (!window.confirm("替换为服务端草稿？未保存编辑将被替换。")) return;
            setSaved(remote); setDraft(remote.draft); setRemote(null); setSelected(0);
            saveCommand.current = null; reviewCommand.current = null;
          }}>采用服务端草稿</button>
        </div>}
        <div ref={reviewControls} tabIndex={-1}/>
        <label>整体审核理由<textarea value={reason} maxLength={2000} disabled={busy || !!reviewCommand.current}
          onChange={event => setReason(event.target.value)}/></label>
        <div className="case-actions">{(["confirmed", "needs_evidence", "rejected"] as CaseDecision[]).map((decision, index) =>
          <button key={decision} disabled={busy || !saved?.draft_revision || dirty || !!saveCommand.current ||
            (!!reviewCommand.current && reviewCommand.current.decision !== decision)}
            onClick={() => void review(decision)}>{["确认问题并冻结纠正", "待补证", "驳回问题"][index]}</button>)}</div>
        <p>本次为操作员审核。用途资格与实际执行效果分别显示。</p>
        <div className="case-actions">{head.history.map(event =>
          <button key={event.revision} disabled={busy} onClick={() => void readReview(event.revision)}>查看审核 r{event.revision}</button>)}</div>
        {history && <section aria-label="已冻结审核">
          <h3>审核 r{history.revision} · {history.actor}</h3><p>{history.reason}</p>
          <pre>{JSON.stringify(history.frozen_draft, null, 2)}</pre>
          <div className="case-actions">{["diagnosis", "localization", "sft", "dpo"].map((purpose, index) =>
            <button key={purpose} disabled={busy} onClick={() => void readPreview(purpose)}>
              {["诊断预览", "定位预览", "SFT 预览", "DPO 预览"][index]}</button>)}</div>
          {preview && <div role="status"><p>{preview.status} · 未授权发布 · 未执行新 Trial</p>
            <p>{[...preview.blocked, ...preview.missing].join(" · ")}</p>
            <pre>{JSON.stringify(preview.candidate, null, 2)}</pre></div>}
        </section>}
      </section>
    </div>
  </dialog>, document.body);
}
