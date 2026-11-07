import type { ButtonHTMLAttributes } from "react";
import "./edit-button.css";

/** A quiet monochrome control; its name describes the field being edited. */
export function EditButton({
  editing,
  label,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  editing: boolean;
  label: string;
}) {
  const name = `${editing ? "完成编辑" : "编辑"}${label}`;
  return (
    <button
      {...props}
      type="button"
      className="fw-edit-button"
      aria-label={name}
      title={name}
      aria-expanded={editing}
    >
      <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
        {editing ? (
          <path
            d="m3.5 8 3 3 6-6"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ) : (
          <path
            d="m10.8 2.2 3 3-7.9 7.9-3.8.8.8-3.8 7.9-7.9ZM9.6 3.4l3 3"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}
      </svg>
    </button>
  );
}
