import { useEffect, useRef, useState } from "react";
import type { CaseView, EvidenceClient, Detail, IssueKind } from "./client";
import "./case-panel.css";
import { CorrectionEditor } from "./CorrectionEditor";

/** A separate review write boundary. The migrated legacy Sidebar stays read-only. */
export function CasePanel({
  detail, position, onStep, client,
}: {
  detail: Detail;
  position: number;
  onStep: (position: number) => void;
  client: EvidenceClient;
}) {
  const [editing, setEditing] = useState<CaseView | null>(null);
  const [cases, setCases] = useState<CaseView[]>([]);
  const [draft, setDraft] = useState(false);
  const [anchor, setAnchor] = useState(position);
  const [kind, setKind] = useState<IssueKind>("unknown");
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const stableDraftId = useRef<string | null>(null);

  async function reload(signal?: AbortSignal) {
    try {
      const next = await client.casesForSnapshot(detail.snapshot_id, signal);
      if (!signal?.aborted) setCases(next.items);
    } catch (e) {
      if (!signal?.aborted) setError(String(e));
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    void reload(controller.signal);
    return () => controller.abort();
  }, [client, detail.snapshot_id]);

  function beginDraft() {
    setAnchor(position);
    stableDraftId.current = crypto.randomUUID();
    setKind("unknown");
    setSummary("");
    setError("");
    setDraft(true);
  }

  async function submit() {
    if (summary.trim().length < 8) {
      setError("问题描述至少需要 8 个字符");
      return;
    }
    const step = detail.trajectory.traj[anchor];
    if (!stableDraftId.current) stableDraftId.current = crypto.randomUUID();
    setBusy(true); setError(""); setNotice("");
    try {
      await client.createCase({
        case_id: stableDraftId.current,
        snapshot_id: detail.snapshot_id,
        position: anchor,
        source_step_id: typeof step?.step_id === "string" ? step.step_id : null,
        issue_kind: kind,
        summary: summary.trim(),
        evidence_refs: ["step:" + anchor],
        analysis_refs: [],
      });
      setDraft(false);
      stableDraftId.current = null;
      setNotice("问题已保存；审核与数据集准入是独立操作");
      await reload();
    } catch (e) {
      setError(String(e));
    } finally { setBusy(false); }
  }

  return (
    <section className="case-panel task-section" aria-label="问题与审核">
      {editing && <CorrectionEditor key={editing.case_id} item={editing} detail={detail} client={client}
        onClose={() => setEditing(null)} onReviewed={result => setCases(current => current.map(value => value.case_id === result.case_id ? result : value))} />}
      <header>
        <h2>问题 / Case</h2>
        <button disabled={busy} onClick={beginDraft}>标记当前步骤</button>
        <button disabled={busy} aria-label="刷新 Case" onClick={() => void reload()}>↻</button>
      </header>
      <p className="case-help">来源轨迹不变；机器诊断仅作建议，人工操作员决定另存。</p>
      {error && <p className="case-error" role="alert">{error}</p>}
      {notice && <p className="case-help" role="status">{notice}</p>}
      {draft && (
        <div className="case-editor">
          <p>固定定位：快照 {detail.snapshot_id.slice(0, 8)} · 步骤 {anchor}</p>
          <label>问题类别
            <select value={kind} onChange={e => setKind(e.target.value as IssueKind)}>
              <option value="unknown">暂不确定</option>
              <option value="task_outcome">任务结果</option>
              <option value="step_action">步骤动作</option>
              <option value="tool_execution">工具执行</option>
              <option value="environment">环境</option>
              <option value="safety">安全/接管</option>
              <option value="data_or_label">数据/标签</option>
            </select>
          </label>
          <label>问题与证据说明
            <textarea rows={3} maxLength={2000} value={summary}
              onChange={e => setSummary(e.target.value)}
              placeholder="具体发生了什么？哪些证据仍然缺失？"/>
          </label>
          <div className="case-actions">
            <button disabled={busy} onClick={() => void submit()}>保存待审 Case</button>
            <button disabled={busy} onClick={() => setDraft(false)}>取消</button>
          </div>
        </div>
      )}
      {!cases.length && <p className="case-help">当前快照暂无 Case。</p>}
      {cases.map(item => (
        <article className="case-item" key={item.case_id}>
          <div className="case-item-head">
            <button onClick={() => onStep(item.position)}>Step {item.position}</button>
            <span>{item.review_status === "operator_confirmed" ? "操作员已确认" :
              item.review_status === "pending" ? "待审核" :
              item.review_status === "rejected" ? "已驳回" : "待补证"}</span>
          </div>
          <p>{item.summary}</p>
          <small>{item.issue_kind} · r{item.review_revision} · {item.case_id.slice(0, 8)}</small>
          {item.analysis_refs.length > 0 &&
            <p className="case-help">外部评估/诊断引用：未验证，不自动作为人审结论</p>}
          <button onClick={() => setEditing(item)}>纠正与审核</button>
          {item.history.length > 0 && <details>
            <summary>决策记录</summary>
            {item.history.map(event => <p key={event.revision} className="case-help">
              r{event.revision} · {event.decision} · {event.actor} · {event.reason}
            </p>)}
          </details>}
        </article>
      ))}
    </section>
  );
}
