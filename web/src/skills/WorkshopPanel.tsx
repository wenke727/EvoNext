import { useEffect, useRef, useState } from "react";
import type { EvidenceClient } from "../evidence/client";
import "./workshop.css";

type Files = Record<string, string>;
type Draft = {
  draft_id: string; state: string;
  proposal: { skill_id: string; base_revision: string | null; files: Files;
    sources: string[]; reason: string; mode: string };
  diff: string; warnings: string[];
  review: { verdict: string; notes: string; kind: string } | null;
  commit: { revision: string } | null;
};
type Inventory = { skills: { skill_id: string; revision: string; archived: boolean }[];
  drafts: Draft[]; owner: string; model_enabled: boolean };
type Operation = { operation_id: string; status: string;
  result?: { outcome: string; notes: string; draft_ids: string[] } | null; error?: unknown };

export function WorkshopPanel({ client, snapshotId, visible, onClose }: {
  client: EvidenceClient; snapshotId: string; visible: boolean; onClose: () => void;
}) {
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [skillId, setSkillId] = useState("");
  const [base, setBase] = useState<string | null>(null);
  const [files, setFiles] = useState<Files>({ "SKILL.md": "" });
  const [activeFile, setActiveFile] = useState("SKILL.md");
  const [newPath, setNewPath] = useState("references/details.md");
  const [source, setSource] = useState(snapshotId);
  const [positions, setPositions] = useState("0");
  const [instruction, setInstruction] = useState("");
  const [caseRef, setCaseRef] = useState("");
  const [images, setImages] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [notes, setNotes] = useState("");
  const [operationId, setOperationId] = useState("");
  const [operation, setOperation] = useState<Operation | null>(null);
  const [preview, setPreview] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  async function api<T>(path = "", body?: unknown): Promise<T> {
    const response = await client.request("/api/v1/workshop" + path, body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    return response.json() as Promise<T>;
  }
  async function refresh() { const result = await api<Inventory>(); if (mounted.current) setInventory(result); }
  async function perform(work: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError("");
    try { await work(); } catch (e) { if (mounted.current) setError(String(e)); }
    finally { if (mounted.current) setBusy(false); }
  }
  useEffect(() => { if (visible) void perform(refresh); }, [visible]);
  useEffect(() => {
    if (!dirty) return;
    const protect = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener("beforeunload", protect);
    return () => window.removeEventListener("beforeunload", protect);
  }, [dirty]);

  function editFiles(next: Files) { setFiles(next); setDirty(true); setDraft(null); }
  function adoptDraft(value: Draft) {
    setDraft(value); setSkillId(value.proposal.skill_id); setBase(value.proposal.base_revision);
    setFiles(value.proposal.files); setActiveFile("SKILL.md");
    setSource(value.proposal.sources[0]); setInstruction(value.proposal.reason); setDirty(false);
  }
  function request(mode: "learn" | "diet") {
    const selected = positions.split(",").map(p => Number(p.trim()));
    if (!positions.trim() || selected.some(p => !Number.isInteger(p) || p < 0))
      throw new Error("请输入逗号分隔的 0-based 步骤序号");
    const [caseId, reviewRevision] = caseRef.trim().split("@");
    return { operation_id: operationId || crypto.randomUUID(), skill_id: skillId,
      base_revision: base, mode, instruction,
      sources: [{ snapshot_id: source, positions: selected }], include_images: images,
      cases: caseId ? [{ case_id: caseId, revision: Number(reviewRevision) }] : [] };
  }
  async function author(mode: "learn" | "diet") {
    const body = request(mode);
    // Retain the exact request identity even when delivery becomes uncertain.
    setOperationId(body.operation_id);
    const result = await api<Operation>("/operations", body);
    setOperation(result);
    await refresh();
  }
  async function loadSkill(id: string) {
    const result = await api<{ files: Files; head: { revision: string } }>("/skills/" + encodeURIComponent(id));
    setSkillId(id); setBase(result.head.revision); setFiles(result.files);
    setActiveFile("SKILL.md"); setDraft(null); setDirty(false); setOperationId(""); setOperation(null);
  }

  return <section className="workshop-panel" hidden={!visible} aria-label="Skill Workshop">
    <header><div><h1>Skill Workshop</h1><p>候选方法 · 固定证据 · 复核后显式提交</p></div>
      <button onClick={onClose}>返回轨迹</button></header>
    {error && <p role="alert" className="error">{error}</p>}
    <div className="workshop-columns">
      <aside>
        <h2>候选库</h2>
        <button disabled={busy} onClick={() => void perform(refresh)}>刷新库与草稿</button>
        <p>{inventory?.owner || "尚未连接 Workshop"}</p>
        {inventory?.skills.map(s => <button key={s.skill_id} disabled={busy || dirty}
          onClick={() => void perform(() => loadSkill(s.skill_id))}>
          {s.skill_id}{s.archived ? " · 已归档" : ""}<small>{s.revision.slice(0, 12)}</small>
        </button>)}
        <button disabled={busy || dirty} onClick={() => {
          setSkillId(""); setBase(null); setFiles({ "SKILL.md": "" }); setActiveFile("SKILL.md");
          setDraft(null); setOperationId(""); setOperation(null);
        }}>新建候选</button>
        <h2>草稿箱</h2>
        {inventory?.drafts.slice().reverse().map(d => <button key={d.draft_id} disabled={busy || dirty}
          onClick={() => adoptDraft(d)}>
          {d.proposal.skill_id} · {d.state}<small>{d.proposal.mode} · {d.draft_id.slice(0, 12)}</small>
        </button>)}
        {dirty && <p>先保存草稿再切换。返回轨迹会保留当前编辑。</p>}
      </aside>
      <main>
        <div className="workshop-fields">
          <label>Skill ID<input aria-label="Skill ID" value={skillId} disabled={busy || !!base}
            onChange={e => { setSkillId(e.target.value); setDraft(null); }} placeholder="check-target" /></label>
          <label>来源快照<input aria-label="来源快照" value={source} disabled={busy}
            onChange={e => { setSource(e.target.value); setPreview(""); setDraft(null); }} /></label>
          <button disabled={busy || !snapshotId} onClick={() => { setSource(snapshotId); setPreview(""); setDraft(null); }}>
            使用当前轨迹快照</button>
          <label>学习目标 / 修改理由<textarea aria-label="修改理由" value={instruction} disabled={busy}
            onChange={e => { setInstruction(e.target.value); setDraft(null); }} /></label>
        </div>
        <p>基于版本：{base || "新建"}。附件只保存为内容，不执行脚本。</p>
        <div className="workshop-tabs">{Object.keys(files).map(path =>
          <button key={path} aria-pressed={activeFile === path} onClick={() => setActiveFile(path)}>{path}</button>)}</div>
        <textarea className="workshop-editor" aria-label="Skill 文件内容" value={files[activeFile] ?? ""}
          disabled={busy} spellCheck={false} onChange={e => editFiles({ ...files, [activeFile]: e.target.value })} />
        <div className="workshop-actions">
          <input aria-label="附件路径" value={newPath} onChange={e => setNewPath(e.target.value)} />
          <button disabled={busy || !newPath || newPath in files} onClick={() => {
            editFiles({ ...files, [newPath]: "" }); setActiveFile(newPath);
          }}>添加附件</button>
          <button disabled={busy || activeFile === "SKILL.md"} onClick={() => {
            const next = { ...files }; delete next[activeFile]; editFiles(next); setActiveFile("SKILL.md");
          }}>移除当前附件</button>
          <button disabled={busy || !skillId || !source || !instruction || !files["SKILL.md"]}
            onClick={() => void perform(async () => {
              const result = await api<Draft>("/drafts", { skill_id: skillId, base_revision: base,
                files, source_snapshots: [source], reason: instruction });
              adoptDraft(result); await refresh();
            })}>保存完整草稿</button>
        </div>
        <details>
          <summary>从证据学习 / 精简现有 Skill</summary>
          <p>最多一次修复。精简保持段落原文，仍须复核规则是否在正确时机可读。缺证可停止。</p>
          <label>证据步骤（0-based，逗号分隔）<input value={positions} onChange={e => setPositions(e.target.value)} /></label>
          <label>可选 Case（ID@审核版本）<input value={caseRef} onChange={e => setCaseRef(e.target.value)} /></label>
          <label><input type="checkbox" checked={images} onChange={e => setImages(e.target.checked)} />包含已绑定截图（最多 4 张）</label>
          <div className="workshop-actions">
            <button disabled={busy || !source || !skillId || !instruction}
              onClick={() => void perform(async () => setPreview(JSON.stringify(await api("/preview", request("learn")), null, 2)))}>
              预览选中证据</button>
            <button disabled={busy || !inventory?.model_enabled || !skillId || !source || !instruction || dirty}
              onClick={() => void perform(() => author("learn"))}>显式学习</button>
            <button disabled={busy || !inventory?.model_enabled || !base || !source || !instruction || dirty}
              onClick={() => void perform(() => author("diet"))}>显式精简</button>
          </div>
          {preview && <pre>{preview}</pre>}
          {!inventory?.model_enabled && <p>模型调用未启用；仍可手工编辑和复核。</p>}
          <label>操作 ID（恢复时复用）<input value={operationId} onChange={e => setOperationId(e.target.value)} /></label>
          <button disabled={busy || !operationId} onClick={() => void perform(async () => {
            setOperation(await api<Operation>("/operations/" + encodeURIComponent(operationId))); await refresh();
          })}>读回运行结果</button>
          {operation && <pre role="status">{JSON.stringify(operation, null, 2)}</pre>}
          <button disabled={busy} onClick={() => { setOperationId(""); setOperation(null); }}>为下一次操作清除 ID</button>
        </details>
        {draft && <section className="workshop-review">
          <h2>草稿复核 · {draft.state}</h2>
          <p>{draft.draft_id}</p>
          {draft.warnings.map(w => <p key={w}>{w}</p>)}
          <pre aria-label="草稿 diff">{draft.diff || "内容无变化"}</pre>
          {draft.review && <p>{draft.review.kind === "model" ? "模型复核" : "操作员复核"}：{draft.review.notes}</p>}
          {draft.state === "pending" && <>
            <label>复核依据<textarea aria-label="复核依据" value={notes} onChange={e => setNotes(e.target.value)} /></label>
            <div className="workshop-actions">{(["approved", "needs_evidence", "rejected"] as const).map((verdict, i) =>
              <button key={verdict} disabled={busy || !notes.trim()} onClick={() => void perform(async () => {
                setDraft(await api<Draft>(`/drafts/${draft.draft_id}/review`, { verdict, notes })); await refresh();
              })}>{["通过候选复核", "需要补证", "驳回"][i]}</button>)}</div>
          </>}
          <div className="workshop-actions">
            <button disabled={busy || draft.state !== "approved"} onClick={() => void perform(async () => {
              const result = await api<Draft>(`/drafts/${draft.draft_id}/commit`, {});
              setDraft(result); if (result.commit) setBase(result.commit.revision); await refresh();
            })}>提交为候选版本</button>
            <button disabled={busy || !!draft.commit || draft.state === "discarded"} onClick={() => void perform(async () => {
              setDraft(await api<Draft>(`/drafts/${draft.draft_id}/discard`, {})); await refresh();
            })}>丢弃草稿</button>
          </div>
          {draft.commit && <p role="status">已提交候选版本 {draft.commit.revision}；尚未执行或评估效果。</p>}
        </section>}
      </main>
    </div>
  </section>;
}
