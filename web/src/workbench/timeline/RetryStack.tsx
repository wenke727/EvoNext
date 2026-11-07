import { useRef, type ReactNode } from "react";
import "./retry-stack.css";

// Retains the old TimelineStack's layered preview and explicit collapse action;
// state and screenshot loading belong to the new host, without DOM mount bridges.
export function RetryStack({ label, count, current, position, expanded, compact, previews, badges, verdict, tabIndex, onFocus, children, onToggle }: {
  label: string;
  count: number;
  current: boolean;
  position: number;
  expanded: boolean;
  compact: boolean;
  previews: ReactNode[];
  badges: ReactNode;
  verdict?: "error" | "correct";
  tabIndex: number;
  onFocus: () => void;
  children: ReactNode[];
  onToggle: () => void;
}) {
  const group = useRef<HTMLDivElement>(null);
  function toggle() {
    onToggle();
    requestAnimationFrame(() => group.current?.querySelector<HTMLButtonElement>("button")?.focus());
  }
  return (
    <div ref={group} className={`retry-stack ${compact ? "retry-stack--compact" : "retry-stack--grid"} ${expanded ? "is-expanded" : ""}`}
      role="group" aria-label={`重试组 ${label}`} aria-expanded={expanded}
      data-retry-range={label} onKeyDown={event => {
        if (event.key === "Escape" && expanded) {
          event.preventDefault();
          event.stopPropagation();
          toggle();
        }
      }}>
      {expanded ? children.map((child, index) => index === 0 ? (
        <div className="retry-stack-first" key={index}>
          {child}
          <button className="retry-stack-collapse" aria-label={`收起重试组 ${label}`} onClick={toggle} onKeyDown={event => {
            if (event.key === "Enter" || event.key === " ") event.stopPropagation();
          }}>×</button>
        </div>
      ) : child) : (
        <button data-source-verdict={verdict} className="retry-stack-preview" data-position={position} aria-current={current ? "step" : undefined}
          aria-label={`展开重试组 ${label}，${count} 步`} aria-expanded={false}
          tabIndex={tabIndex} onFocus={onFocus}
          onClick={toggle} onKeyDown={event => {
            if (event.key === "Enter" || event.key === " ") event.stopPropagation();
          }}>
          <span className="retry-stack-header">{label} <span>↻ {count}</span></span>
          <span className="retry-stack-images">{previews.map((preview, index) => (
            <span className="retry-stack-layer" key={index} style={{ left: `${index * 12}px`, zIndex: index + 1 }}>{preview}</span>
          ))}</span>
          <span className="retry-stack-badges">{badges}</span>
          <span className="retry-stack-hint">展开重试组</span>
        </button>
      )}
    </div>
  );
}
