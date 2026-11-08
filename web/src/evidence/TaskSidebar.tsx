import { useState } from "react";
import type { DisplayPreferences } from "./display-preferences";
import type { Detail, EvidenceClient } from "./client";
import { OutcomePanel } from "./OutcomePanel";
import { CasePanel } from "./CasePanel";
import { record } from "./evaluation";
import { Sidebar } from "../workbench/sidebar/Sidebar";
import { EvaluationPanel } from "./EvaluationPanel";
import "../workbench/sidebar/base.css";

function Json({ title, value }: { title: string; value: unknown }) {
  const [open, setOpen] = useState(false);
  return (
    <details
      className="json-disclosure"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>{title}</summary>
      {open && <pre>{JSON.stringify(value, null, 2)}</pre>}
    </details>
  );
}
export function TaskSidebar({
  detail,
  position,
  onStep,
  display,
  client,
}: {
  display: DisplayPreferences;
  detail: Detail;
  client: EvidenceClient;
  position: number;
  onStep: (position: number) => void;
}) {
  const [notice, setNotice] = useState("");
  const rejectWrite = () => {
    throw new Error("固定快照只读；修订与审核写入尚未接入");
  };
  function taskUrl(id: string, index?: number | null) {
    if (id !== detail.task_id) return "";
    const hits =
      index == null
        ? [position]
        : detail.trajectory.traj.flatMap((step, ordinal) =>
            step.index === index ? [ordinal] : [],
          );
    if (hits.length !== 1) return "";
    const url = new URL(location.href);
    url.hash = new URLSearchParams({
      snapshot: detail.snapshot_id,
      step: String(hits[0]),
      view: "detail",
    }).toString();
    return url.href;
  }
  return (
    <>
      <Sidebar
        task={detail.trajectory}
        disabled={true}
        evaluation={
          <EvaluationPanel
            detail={detail}
            position={position}
            onStep={onStep}
            embedded
          />
        }
        preferences={{
          showTime: display.time,
          showEvaluation: display.evaluation,
          comments: false,
          qa: false,
          operations:
            typeof detail.trajectory.operation_suggestion === "string" &&
            detail.trajectory.operation_suggestion.length > 0,
          planner: false,
          audit: false,
          auditOptions: {
            taskStatusOptions: [],
            primaryErrorCauses: [],
            secondaryErrorCauses: [],
          },
        }}
        ports={{
          request: async () => rejectWrite(),
          taskUrl,
          contextUrl: () => "",
          plannerUrl: () => "",
          copy: (value) => navigator.clipboard.writeText(value),
          jump: (index) => {
            const hits = detail.trajectory.traj.flatMap((step, ordinal) =>
              step.index === index ? [ordinal] : [],
            );
            if (hits.length === 1) onStep(hits[0]);
            else setNotice("来源步骤范围未唯一绑定到当前快照");
          },
        }}
        onField={rejectWrite}
        onTags={rejectWrite}
        onAudit={rejectWrite}
      />
      <p className="sidebar-note" role="status">
        {notice || "来源证据只读 · 问题另存到 Case"}
      </p>
      <OutcomePanel detail={detail} position={position} onStep={onStep} client={client} />
      <CasePanel detail={detail} position={position} onStep={onStep} client={client} />
      <section className="task-section">
        <h2>来源与版本</h2>
        <dl>
          <dt>来源版本</dt>
          <dd>{detail.source_version ?? "未知"}</dd>
          <dt>步骤 / 媒体</dt>
          <dd>
            {detail.step_count} / {detail.media_count}
          </dd>
          <dt>来源类型</dt>
          <dd>
            {String(
              detail.metadata.source_kind ??
                record(detail.metadata.origin).kind ??
                "未记录",
            )}
          </dd>
          <dt>split</dt>
          <dd>{String(detail.metadata.split ?? "未记录")}</dd>
          <dt>do_not_train</dt>
          <dd>{String(detail.metadata.do_not_train ?? "未记录")}</dd>
        </dl>
      </section>
      {display.time && typeof detail.metadata.created_at === "string" && (
        <p className="sidebar-note">
          来源采集时间 · {detail.metadata.created_at}
        </p>
      )}
      <Json title="来源元信息" value={detail.metadata} />
      <Json
        title="固定快照 / 原始 JSON"
        value={{
          snapshot_id: detail.snapshot_id,
          trajectory: detail.trajectory,
        }}
      />
    </>
  );
}
