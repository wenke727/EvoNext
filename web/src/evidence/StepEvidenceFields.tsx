import { useState } from "react";
import type { DisplayPreferences } from "./display-preferences";
import type { Step } from "./client";
import type { StepProjection } from "./projection";
import { LEGEND } from "./legend";
import { evidenceJson as json, evidenceText as text } from "./display";

function JsonDisclosure({ title, value }: { title: string; value: unknown }) {
  const [open, setOpen] = useState(false);
  return (
    <details
      className="json-disclosure"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>{title}</summary>
      {open && <pre>{typeof value === "string" ? value : json(value)}</pre>}
    </details>
  );
}

function SourceField({
  title,
  value,
  source,
}: {
  title: string;
  value: unknown;
  source?: string;
}) {
  return (
    <section className="source-field">
      <div className="field-title">
        <h3>{title}</h3>
        {source && <span title={source}>{source}</span>}
      </div>
      <div className="field-content">
        {value == null ? (
          <span className="unrecorded">未记录</span>
        ) : (
          <pre>{text(value)}</pre>
        )}
      </div>
    </section>
  );
}

export function StepEvidenceFields({
  step,
  projection,
  signals,
  display,
}: {
  display: DisplayPreferences;
  step: Step;
  projection: StepProjection | null;
  signals: (keyof typeof LEGEND)[];
}) {
  let toolCall: unknown;
  if (projection?.call) {
    const value = projection.call.value;
    toolCall = typeof value === "string" ? value : json(value);
  }
  return (
    <div className="step-fields">
      <div className="step-identity">
        源 index {text(step.index)} · source_index{" "}
        {text(step.source_index)} · step_id {text(step.step_id)}
      </div>
      {signals.length > 0 && (
        <div className="source-signal-summary">
          {signals.map((kind) => (
            <span key={kind} title={LEGEND[kind].hint}>
              {LEGEND[kind].icon} {LEGEND[kind].label}
            </span>
          ))}
        </div>
      )}
      {display.followup && step.user_interrupt != null &&
        step.user_interrupt !== false && (
          <section className="followup-evidence">
            <h3>用户跟进 · 来源原文</h3>
            <pre>{text(step.user_interrupt)}</pre>
          </section>
        )}
      {step.step_type === "human" && (
        <p className="human-evidence">
          来源记录为用户主动操控，期间动作与效果以独立证据为准。
        </p>
      )}
      {display.agent && (
        <>
          <h2 className="agent-heading">Agent</h2>
          <SourceField
            title="💭 思考"
            value={projection?.thought?.value}
            source={projection?.thought?.source}
          />
          <SourceField
            title="📝 动作语义"
            value={projection?.semantic?.value}
            source={projection?.semantic?.source}
          />
          <SourceField
            title="工具调用"
            value={toolCall}
            source={projection?.call?.source}
          />
          {projection?.parseError && (
            <p className="warning">{projection.parseError}</p>
          )}
        </>
      )}
      {display.rawOutput && (
        <>
          <JsonDisclosure
            title="模型原始输出"
            value={step.value?.raw_model_output}
          />
          {Array.isArray(step.value?.rejected_model_outputs) &&
            step.value.rejected_model_outputs.length > 0 && (
              <JsonDisclosure
                title={`此前模型回复 · ${step.value.rejected_model_outputs.length} 次`}
                value={step.value.rejected_model_outputs}
              />
            )}
        </>
      )}
      {display.execution && (
        <>
          <JsonDisclosure
            title="实际执行记录"
            value={step.value?.recorded_execution}
          />
          <JsonDisclosure
            title="独立执行回执"
            value={step.value?.execution_result}
          />
        </>
      )}
      {display.runtime && (
        <JsonDisclosure title="Runtime / dispatch / 观测" value={step.runtime} />
      )}
      {display.fullStep && (
        <JsonDisclosure title="完整步骤原文" value={step} />
      )}
    </div>
  );
}
