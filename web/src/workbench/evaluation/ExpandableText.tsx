import { useId, useLayoutEffect, useRef, useState } from "react";

type Props = { text: string; label: string; emptyText: string; lines?: number };

/** One measured preview and one inline toggle for machine and specialist evidence. */
export function ExpandableText({ text, label, emptyText, lines = 4 }: Props) {
  const id = useId();
  const paragraph = useRef<HTMLParagraphElement>(null);
  const [overflow, setOverflow] = useState(false);
  const [expanded, setExpanded] = useState(false);
  useLayoutEffect(() => {
    setExpanded(false);
    const element = paragraph.current;
    if (!element) return;
    const measure = () => {
      const lineHeight =
        parseFloat(getComputedStyle(element).lineHeight) || 19.8;
      setOverflow(element.scrollHeight > lineHeight * lines + 1);
    };
    measure();
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(measure);
    observer?.observe(element);
    return () => observer?.disconnect();
  }, [text, lines]);

  const toggle = () => setExpanded((value) => !value);
  const clickText = () => {
    const selection = window.getSelection();
    // Selecting evidence for copying must not collapse the text on mouse-up.
    if (
      selection &&
      !selection.isCollapsed &&
      paragraph.current?.contains(selection.anchorNode)
    )
      return;
    if (overflow) toggle();
  };

  return (
    <div className={`ev-text${overflow ? " ev-text--expandable" : ""}`}>
      <p
        id={`${id}-text`}
        ref={paragraph}
        className={expanded ? "ev-text-expanded" : "ev-clamped"}
        style={expanded ? undefined : { WebkitLineClamp: lines }}
        onClick={clickText}
      >
        <span
          className="ev-text-content"
          role={overflow ? "button" : undefined}
          tabIndex={overflow ? 0 : undefined}
          aria-label={
            overflow
              ? `${label}文字，点击${expanded ? "收起" : "展开"}`
              : undefined
          }
          aria-expanded={overflow ? expanded : undefined}
          aria-controls={overflow ? `${id}-text` : undefined}
          onKeyDown={(event) => {
            if (overflow && (event.key === "Enter" || event.key === " ")) {
              event.preventDefault();
              event.stopPropagation();
              if (!event.repeat) toggle();
            }
          }}
        >
          {text || emptyText}
        </span>
        {overflow && (
          <button
            type="button"
            className="ev-text-toggle"
            aria-label={`${expanded ? "收起" : "展开"}${label}`}
            aria-expanded={expanded}
            aria-controls={`${id}-text`}
            onClick={(event) => {
              event.stopPropagation();
              toggle();
            }}
          >
            {expanded ? "收起" : "展开全文"}
          </button>
        )}
      </p>
    </div>
  );
}
