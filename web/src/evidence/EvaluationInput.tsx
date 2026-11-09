import { useEffect, useRef, useState } from "react";
import type { EvidenceClient } from "./client";

type Preview = {
  step_count: number;
  text_bytes: number;
  text_budget_exceeded: boolean;
  images: { position: number; selected: boolean; availability: string }[];
};
type Evaluation = {
  snapshot_id: string;
  status: string;
  error?: { error_type: string };
  result?: {
    outcome: string;
    checks: { check_id: string; judgment: string; reason: string; evidence_refs: string[] }[];
    native_result: { error_localization?: string; findings: { judgment: string; position?: number | null; check_id: string; reason: string; evidence_refs: string[] }[] };
  };
};

export function EvaluationInput({ client, snapshot, focusPosition, onClose, onStep }: {
  client: EvidenceClient;
  snapshot: string;
  focusPosition: number;
  onClose: () => void;
  onStep: (position: number) => void;
}) {
  const caseIds = useRef(new Map<number, string>());
  const [caseNotice, setCaseNotice] = useState("");
  const [savingCase, setSavingCase] = useState(false);
  async function confirmFinding(index: number, reason: string) {
    if (!window.confirm("确认该步骤存在此问题，并创建独立 Case？\n" + reason)) return;
    const id = caseIds.current.get(index) || crypto.randomUUID();
    caseIds.current.set(index, id);
    setSavingCase(true); setError("");
    try {
      await client.request(`/api/v1/evaluations/${operation}/findings/${index}/cases`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_id: id, summary: reason, confirmed: true }),
      });
      setCaseNotice("Case 已保存 · " + id);
      window.dispatchEvent(new CustomEvent("evonext-case-created", { detail: snapshot }));
    } catch (reason) { setError(String(reason)); }
    finally { setSavingCase(false); }
  }
  const dialog = useRef<HTMLDialogElement>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [investigation, setInvestigation] = useState("auto");
  const [markers, setMarkers] = useState("auto");
  const [operation] = useState(() => new URLSearchParams(location.hash.slice(1)).get("evaluation") || crypto.randomUUID());
  const resume = useRef(Boolean(new URLSearchParams(location.hash.slice(1)).get("evaluation")));
  const [running, setRunning] = useState(resume.current);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  useEffect(() => {
    if (!running) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const response = await client.request(`/api/v1/evaluations/${operation}`, { signal: controller.signal });
        const value: Evaluation = await response.json();
        if (controller.signal.aborted) return;
        if (value.snapshot_id !== snapshot) throw new Error("评估属于另一份轨迹快照");
        setEvaluation(value);
        if (value.status === "pending") timer = setTimeout(poll, 1500);
        else setRunning(false);
      } catch (reason) {
        if (!controller.signal.aborted) { setError(String(reason)); setRunning(false); }
      }
    };
    if (resume.current) {
      void poll();
      return () => { controller.abort(); clearTimeout(timer); };
    }
    void client.request(`/api/v1/snapshots/${snapshot}/evaluations`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operation_id: operation, investigation, options: { markers },
        focus_positions: investigation === "always" ? [focusPosition] : [] }), signal: controller.signal,
    }).then(() => poll()).catch(reason => {
      if (!controller.signal.aborted) { setError(String(reason)); setRunning(false); }
    });
    return () => { controller.abort(); clearTimeout(timer); };
  }, [running, client, operation, snapshot, investigation, markers, focusPosition]);
  useEffect(() => {
    const controller = new AbortController();
    const element = dialog.current;
    const opener = document.activeElement;
    element?.showModal();
    client.request(`/api/v1/snapshots/${snapshot}/evaluation-input`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: "{}", signal: controller.signal,
    }).then(response => response.json()).then(value => {
      if (!controller.signal.aborted) setPreview(value);
    }).catch(reason => {
      if (!controller.signal.aborted) setError(String(reason));
    });
    return () => {
      controller.abort();
      element?.close();
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    };
  }, [client, snapshot]);
  return <dialog ref={dialog} className="shortcut-dialog" aria-label="评估输入预览" onClose={onClose}>
    <div className="dialog-heading">
      <h2>评估输入预览</h2>
      <button autoFocus onClick={onClose}>关闭</button>
    </div>
    {error && <p role="alert">{error}</p>}
    {!preview && !error && <p role="status">正在准备完整轨迹…</p>}
    {preview && <>
      <p>完整轨迹共 {preview.step_count} 步，全部步骤保留在评估文本中（{preview.text_bytes} 字节）。</p>
      <p>首轮选择 {preview.images.filter(image => image.selected).length} 张图片。
        缺少绑定或图片的步骤有 {preview.images.filter(image => image.availability !== "bound_unverified").length} 个。</p>
      <p>图片字节尚待读取核验。当前为输入预览，尚未调用模型。</p>
      {preview.text_budget_exceeded && <p role="alert">完整文本超过首轮预算，需要调整预算或取证方案。</p>}
      <div className="dialog-heading">
        {preview.images.filter(image => image.selected).map(image =>
          <button key={image.position} onClick={() => { onStep(image.position); onClose(); }}>
            查看 Step {image.position} 图片
          </button>)}
      </div>
      <p>默认隐藏已有评分、人审、原始模型输出及未映射字段，原文仍可从轨迹 JSON 查看。</p>
      <label>模型图片 <select value={markers} disabled={running || evaluation !== null}
        onChange={event => setMarkers(event.target.value)}>
        <option value="auto">有明确坐标时标记动作</option>
        <option value="off">只用原图</option>
      </select></label>
      <label>调查范围 <select value={investigation} disabled={running || evaluation !== null}
        onChange={event => setInvestigation(event.target.value)}>
        <option value="auto">结果未知或失败尚未定位时追加取证</option>
        <option value="always" disabled={focusPosition < 0}>调查当前 Step {focusPosition}</option>
        <option value="off">仅 Fast Judge</option>
      </select></label>
      <button disabled={running || preview.text_budget_exceeded || evaluation?.status === "completed"}
        onClick={() => {
          const params = new URLSearchParams(location.hash.slice(1));
          params.set("evaluation", operation);
          history.replaceState(null, "", `${location.pathname}#${params}`);
          resume.current = false;
          setError(""); setRunning(true);
        }}>运行 Fast Judge（模型调用）</button>
      {running && <p role="status">评估处理中 · {operation}</p>}
      {evaluation?.status === "needs_attention" && <p role="alert">评估需要核对 · {evaluation.error?.error_type}</p>}
      {caseNotice && <p role="status">{caseNotice}</p>}
      {evaluation?.result && <>
        <h3>任务结论 · {evaluation.result.outcome}</h3>
        {evaluation.result.checks.map(check => <div key={check.check_id}>
          <p>{check.check_id} · {check.judgment} · {check.reason}</p>
          {check.evidence_refs.map(ref => {
            const match = ref.match(/\/steps\/(\d+)(?:\/image)?$/);
            return match && <button key={ref} onClick={() => { onStep(Number(match[1])); onClose(); }}>
              查看 Step {match[1]} 证据
            </button>;
          })}
        </div>)}
        {evaluation.result.outcome === "failure" && evaluation.result.native_result.error_localization === "undetermined" && <p>已确认任务失败，错误步骤尚未定位。</p>}
        {evaluation.result.native_result.findings.map((finding, index) => <p key={finding.check_id}>
          过程发现 · {finding.reason}
          {finding.position != null && finding.judgment === "fail" &&
            <button disabled={savingCase} onClick={() => void confirmFinding(index, finding.reason)}>确认问题并创建 Case</button>}
          {finding.position != null && <button onClick={() => { onStep(finding.position!); onClose(); }}>查看 Step {finding.position}</button>}
        </p>)}
      </>}
    </>}
  </dialog>;
}
