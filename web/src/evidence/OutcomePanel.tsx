import { useEffect, useRef, useState } from "react";
import type { Detail, EvidenceClient } from "./client";

type OutcomeRun = {
  run_id: string; snapshot_id: string; status: string; input_hash: string; policy_version: string;
  request: {obligations: {check_id: string; requirement: string}[]; evidence_positions: number[]};
  context: {images: {evidence_id: string; position: number; relation: string}[]; missing: {position: number; reason: string}[]};
  model: string;
  record: null | {
    execution_status: string; outcome: string;
    checks: {check_id: string; judgment: string; reason: string; evidence_refs: string[]}[];
    native_result: {error?: string; error_reason?: string; usage?: unknown; observed_model?: string};
  };
};
const labels: Record<string, string> = {
  queued: "已冻结，待派发", running: "评分进行中", completed: "评分已完成", failed: "评分技术错误",
  pass: "满足", fail: "不满足", unknown: "证据不足", not_assessed: "未评估",
  success: "冻结义务满足", failure: "冻结义务不满足", error: "技术错误",
};
export function OutcomePanel({detail, position, client, onStep}: {
  detail: Detail; position: number; client: EvidenceClient; onStep: (position: number) => void;
}) {
  const [runs, setRuns] = useState<OutcomeRun[]>([]);
  const [selected, setSelected] = useState("");
  const [obligations, setObligations] = useState("");
  const [positions, setPositions] = useState<number[]>([]);
  const [scopeConfirmed, setScopeConfirmed] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef<object | null>(null);
  const row = runs.find(value => value.run_id === selected);
  async function refresh(signal?: AbortSignal) {
    try {
      const response = await client.request("/api/v1/snapshots/" + detail.snapshot_id + "/outcome-runs", {signal});
      const value = await response.json();
      if (!signal?.aborted) setRuns(value.items);
    } catch (e) { if (!signal?.aborted) setError(String(e)); }
  }
  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    client.request("/api/v1/outcome-capabilities", {signal: controller.signal})
      .then(response => response.json()).then(value => {if (!controller.signal.aborted) setEnabled(value.dispatch_enabled);})
      .catch(e => {if (!controller.signal.aborted) setError(String(e));});
    return () => controller.abort();
  }, [client, detail.snapshot_id]);
  useEffect(() => {
    if (!row || !["queued", "running"].includes(row.status)) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => void refresh(controller.signal), 3000);
    return () => {clearInterval(timer); controller.abort();};
  }, [row?.run_id, row?.status, client, detail.snapshot_id]);
  async function create() {
    const requirements = obligations.split("\n").map(value => value.trim()).filter(Boolean);
    if (!scopeConfirmed) {setError("请先确认本次使用初始指令范围"); return;}
    if (!requirements.length || requirements.length > 12 || requirements.some(value => value.length < 4)) {
      setError("请逐行填写 1–12 项必需义务，每项至少 4 个字符"); return;
    }
    if (!pending.current) pending.current = {
      scope: "initial_instruction_only", run_id: crypto.randomUUID(), snapshot_id: detail.snapshot_id, repetition_id: "0",
      obligations: requirements.map((requirement, index) => ({check_id: "goal." + (index + 1), requirement})),
      evidence_positions: positions,
    };
    setBusy(true); setError("");
    try {
      const response = await client.request("/api/v1/outcome-runs", {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(pending.current),
      });
      const result: OutcomeRun = await response.json();
      setSelected(result.run_id); pending.current = null; await refresh();
    } catch (e) { setError(String(e) + "。重试会核对同一冻结请求。"); }
    finally { setBusy(false); }
  }
  async function dispatch() {
    if (!row || !window.confirm("派发此冻结评估将使用已配置的模型并可能产生费用，继续？")) return;
    setBusy(true); setError("");
    try {
      await client.request("/api/v1/outcome-runs/" + row.run_id + "/dispatch", {method: "POST"});
      await refresh();
    } catch (e) {setError(String(e));} finally {setBusy(false);}
  }
  return <section className="task-section outcome-panel" aria-label="独立 Outcome">
    <h2>独立 Outcome</h2>
    <p>按固定任务义务评估所选截图。截图保持动作前的时间关系。</p>
    {error && <p role="alert" className="case-error">{error}</p>}
    <label>任务完成义务（每行一项）
      <textarea rows={3} value={obligations} disabled={busy || !!pending.current}
        onChange={event => setObligations(event.target.value)}
        placeholder="例如：截图可确认已进入显示设置页面"/></label>
    <p>首版支持固定初始指令与最多四张、合计 512 KiB 的动作前截图。过程约束和未交付观察可能无法判断。</p>
    <button disabled={busy || !!pending.current || positions.includes(position) || positions.length >= 4}
      onClick={() => setPositions([...positions, position])}>选取当前 Step {position} 截图</button>
    {positions.map(value => <button key={value} disabled={busy || !!pending.current}
      onClick={() => setPositions(positions.filter(item => item !== value))}>移除 Step {value}</button>)}
    <label><input type="checkbox" checked={scopeConfirmed} disabled={busy || !!pending.current}
      onChange={event => setScopeConfirmed(event.target.checked)}/>
      确认本次目标仅使用初始指令，没有待纳入的中途改令</label>
    <button disabled={busy} onClick={() => void create()}>{pending.current ? "重试冻结请求" : "冻结评估输入"}</button>
    {!enabled && <p>真实模型派发未启用。可冻结输入和读取已有记录。</p>}
    <label>评估版本<select value={selected} onChange={event => setSelected(event.target.value)}>
      <option value="">选择评估</option>
      {runs.map(value => <option key={value.run_id} value={value.run_id}>
        {value.run_id.slice(0, 8)} · {labels[value.status] || value.status}
      </option>)}</select></label>
    <button disabled={busy} onClick={() => void refresh()}>刷新评估记录</button>
    {row && <article>
      <p>{labels[row.status]} · {row.model || "模型未配置"}</p>
      <small>输入 {row.input_hash.slice(0, 12)} · 策略 {row.policy_version.slice(0, 12)}</small>
      <ul>{row.request.obligations.map(value => <li key={value.check_id}>{value.requirement}</li>)}</ul>
      <div>{row.context.images.map(value =>
        <button key={value.evidence_id} onClick={() => onStep(value.position)}>
          Step {value.position} · 动作前图
        </button>)}</div>
      {row.context.missing.map(value => <p key={value.position}>Step {value.position} · 缺少绑定图片</p>)}
      {row.status === "queued" && <button disabled={busy || !enabled} onClick={() => void dispatch()}>派发此冻结评估</button>}
      {row.status === "running" && <p>若 Worker 中断，此请求需要人工核对；持续运行状态不会触发重发。</p>}
      {row.record && <div>
        <p>评分 {labels[row.record.execution_status] || row.record.execution_status} · {labels[row.record.outcome]}</p>
        <p>{row.record.checks.length} 项义务 · {row.record.checks.filter(value => value.judgment === "unknown").length} 项缺证
          · {row.record.checks.filter(value => value.judgment === "not_assessed").length} 项未评</p>
        {row.record.checks.map(check => <article key={check.check_id}>
          <strong>{check.check_id} · {labels[check.judgment] || check.judgment}</strong><p>{check.reason}</p>
          {check.evidence_refs.map(ref => {
            const source = row.context.images.find(image => image.evidence_id === ref);
            return source ? <button key={ref} onClick={() => onStep(source.position)}>证据 Step {source.position}</button> : null;
          })}
        </article>)}
        {row.record.native_result.error && <p role="alert">未评原因 / 错误 · {row.record.native_result.error_reason || row.record.native_result.error}</p>}
        <details><summary>固定结果与调用引用</summary><pre>{JSON.stringify(row.record, null, 2)}</pre></details>
      </div>}
    </article>}
  </section>;
}
