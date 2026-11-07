import "./tokens.css";
import "./legend.css";

export const entries = [
  ["current", "当前步骤", ""],
  ["missing", "缺图", ""],
  ["modelRetry", "模型重试", ""],
  ["takeoverProposal", "接管提案", ""],
  ["success", "成功", ""],
  ["error", "错误", ""],
  ["takeover", "接管", ""],
  [
    "multiTerminator",
    "多终止点",
    "同一轨迹存在多个 terminate，可能是多任务设计",
  ],
  ["userFollowup", "用户跟进", "这一步有用户跟进信息"],
  ["userIntervention", "主动操控", "用户主动操控，期间操作未采集"],
  ["firstDeviation", "末次偏航", ""],
  ["retry", "重试", ""],
  ["securityFlag", "黑屏", ""],
  ["teacherAssist", "Teacher Assist", ""],
  ["riskItImg", "IT 图片风控", ""],
  ["riskItText", "IT 文本风控", ""],
  ["riskIt", "IT 风控", ""],
  ["riskIntent", "意图风控", ""],
  ["riskInputPrompt", "提示词风控", ""],
] as const;
export type LegendFlags = Partial<Record<(typeof entries)[number][0], boolean>>;

function Icon({ kind }: { kind: (typeof entries)[number][0] }) {
  if (kind === "retry") return null; // Shared SVG mask also used by timeline badges.
  const paths =
    kind === "userFollowup"
      ? "M3 3h10v8H7l-4 3V3z M5 6h6 M5 8h4"
      : kind === "userIntervention"
        ? "M6 8V3a1 1 0 0 1 2 0v4 M8 6l4 1v4l-2 3H6l-3-4 1-1 2 2V8"
        : kind === "firstDeviation"
          ? "M4 4l8 8 M12 4l-8 8"
          : kind.startsWith("risk")
            ? "M8 2l6 11H2L8 2z M8 6v3 M8 11h0"
            : "M3 3h10v10H3z";
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths} />
    </svg>
  );
}

export function TimelineLegend({
  flags,
  hasSteps,
  labels,
}: {
  flags: LegendFlags;
  hasSteps: boolean;
  labels?: Partial<
    Record<
      (typeof entries)[number][0],
      { label: string; hint: string; color: string }
    >
  >;
}) {
  if (!hasSteps) return null;
  return (
    <div
      className="timeline-legend-react"
      role="list"
      aria-label="步骤状态图例"
    >
      {entries
        .filter(([key]) => key === "current" || flags[key])
        .map(([key, label, hint]) => (
          <span
            className="timeline-legend-react__item"
            role="listitem"
            key={key}
            title={labels?.[key]?.hint || hint || label}
          >
            <span
              className="timeline-legend-react__icon"
              data-kind={key}
              style={labels?.[key] ? { color: labels[key]!.color } : undefined}
            >
              <Icon kind={key} />
            </span>
            <span>{labels?.[key]?.label || label}</span>
          </span>
        ))}
    </div>
  );
}
