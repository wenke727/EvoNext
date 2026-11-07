import { LEGEND } from "./legend";
import { TimelineLegend, entries } from "../workbench/timeline/Legend";
import type { LegendFlags } from "../workbench/timeline/Legend";
import type { LegendKind } from "./legend";
const nativeKeys = {
  current: "current",
  sourceCorrect: "success",
  sourceError: "error",
  takeover: "takeover",
  takeoverProposal: "takeoverProposal",
  multiEnd: "multiTerminator",
  followup: "userFollowup",
  human: "userIntervention",
  retry: "retry",
  modelRetry: "modelRetry",
  security: "securityFlag",
  teacher: "teacherAssist",
  risk: "riskIt",
  missing: "missing",
} as const;
export function StepLegend({ kinds }: { kinds: LegendKind[] }) {
  const flags: LegendFlags = {};
  const labels: Partial<
    Record<
      (typeof entries)[number][0],
      { label: string; hint: string; color: string }
    >
  > = {};
  for (const kind of kinds) {
    const key = nativeKeys[kind];
    flags[key] = true;
    labels[key] = LEGEND[kind];
  }
  return (
    <div className="step-legend">
      <TimelineLegend
        flags={flags}
        hasSteps={kinds.length > 0}
        labels={labels}
      />
    </div>
  );
}
export function SignalBadges({ kinds }: { kinds: LegendKind[] }) {
  if (!kinds.length) return null;
  return (
    <span className="step-signal-badges" aria-label="来源步骤标记">
      {kinds.map((kind) => (
        <span
          key={kind}
          data-signal={kind}
          title={`${LEGEND[kind].label}：${LEGEND[kind].hint}`}
          style={{ color: LEGEND[kind].color }}
        >
          {LEGEND[kind].icon}
        </span>
      ))}
    </span>
  );
}
