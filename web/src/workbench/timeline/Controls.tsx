import "./controls.css";

type Mode = "timeline" | "grid";
interface Actions {
  min: number;
  max: number;
  setMode(mode: Mode): void;
  setSize(size: number): void;
  openJson(): void;
}
interface ControlsState {
  visible: boolean;
  mode: Mode;
  columns: number;
  size: number;
}

export function TimelineControls({
  mode,
  columns,
  size,
  actions,
}: ControlsState & { actions: Actions }) {
  return (
    <>
      <div
        className="workbench-view-toggle"
        role="group"
        aria-label="Workbench 视图"
      >
        {(["timeline", "grid"] as const).map((view) => {
          const grid = view === "grid";
          const label = grid ? "轨迹总览" : "单步聚焦";
          return (
            <button
              key={view}
              type="button"
              data-timeline-view-mode={view}
              className={
                mode === view
                  ? "workbench-view-button active"
                  : "workbench-view-button"
              }
              aria-label={label}
              aria-pressed={mode === view}
              title={grid ? label + " (Alt+G)" : label}
              onClick={() => actions.setMode(view)}
            >
              <span
                className={"workbench-view-icon workbench-view-icon-" + view}
                aria-hidden="true"
              >
                <i />
                <i />
                <i />
                {grid && <i />}
              </span>
            </button>
          );
        })}
        <button
          type="button"
          className="workbench-view-button workbench-json-view-button"
          aria-label="JSON 视图"
          title="JSON 视图"
          onClick={() => actions.openJson()}
        >
          <span
            className="workbench-view-icon workbench-view-icon-json"
            aria-hidden="true"
          >
            {"{}"}
          </span>
        </button>
      </div>
      {mode === "grid" && (
        <>
          <span
            className="workbench-statusbar-separator workbench-thumbnail-size-separator"
            aria-hidden="true"
          >
            |
          </span>
          <div
            className="workbench-thumbnail-size-control"
            title="缩略图大小：越大每行显示越少"
            role="group"
            aria-label="网格缩略图大小"
          >
            <div className="workbench-thumbnail-size-topline">
              <button
                type="button"
                className="workbench-thumbnail-size-step"
                data-workbench-grid-size-step="-1"
                title="缩小缩略图"
                aria-label="缩小缩略图"
                disabled={size <= actions.min}
                onClick={() => actions.setSize(size - 1)}
              >
                -
              </button>
              <output data-workbench-grid-size-value="">{columns}列</output>
              <button
                type="button"
                className="workbench-thumbnail-size-step"
                data-workbench-grid-size-step="1"
                title="放大缩略图"
                aria-label="放大缩略图"
                disabled={size >= actions.max}
                onClick={() => actions.setSize(size + 1)}
              >
                +
              </button>
            </div>
            <input
              type="range"
              min={actions.min}
              max={actions.max}
              step="1"
              value={size}
              data-workbench-grid-size=""
              aria-label="网格缩略图大小"
              onChange={(event) =>
                actions.setSize(event.currentTarget.valueAsNumber)
              }
            />
          </div>
        </>
      )}
      <span className="workbench-statusbar-separator" aria-hidden="true">
        |
      </span>
    </>
  );
}
