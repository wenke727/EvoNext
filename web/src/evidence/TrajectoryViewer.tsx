import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, PointerEvent } from "react";
import type { Detail, EvidenceClient } from "./client";
import { EvidenceInspector } from "./EvidenceInspector";
import { EvidenceImage } from "./EvidenceImage";
import { actionLabel, projectStep } from "./projection";
import { usePreferences } from "./preferences";
import { RetryStack } from "../workbench/timeline/RetryStack";
import { retryEntries, windowEntries, visiblePositions, visibleCursor, TIMELINE_PAGE_SIZE } from "./timeline";
import type { TimelineEntry } from "./timeline";
import { navigationTarget } from "./navigation";
import { TaskSidebar } from "./TaskSidebar";
import { EvidenceComparison } from "./EvidenceComparison";
import { TimelineControls } from "../workbench/timeline/Controls";
import { trajectorySignals } from "./legend";
import { StepEvidenceFields } from "./StepEvidenceFields";
import { DisplaySettings } from "./DisplaySettings";
import { StepPreview } from "./StepPreview";
import { evidenceText as text } from "./display";
import { StepLegend, SignalBadges } from "./StepLegend";

const PAGE_SIZE = TIMELINE_PAGE_SIZE;

export function TrajectoryViewer({
  client,
  detail,
  status,
  taskIndex,
  taskCount,
  onTaskNavigate,
  onReload,
  onDownload,
  onJson,
}: {
  client: EvidenceClient;
  detail: Detail;
  status: string;
  taskIndex: number;
  taskCount: number;
  onTaskNavigate: (direction: number) => void;
  onReload: () => void;
  onDownload: (kind: "trajectory" | "bundle") => void;
  onJson: () => void;
}) {
  const steps = detail.trajectory.traj;
  const count = steps.length;
  const entries = useMemo(() => retryEntries(steps, detail.missing_media), [steps, detail.missing_media]);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const visible = useMemo(() => visiblePositions(entries, expanded), [entries, expanded]);
  const signals = useMemo(() => trajectorySignals(detail), [detail]);
  const initial = new URLSearchParams(location.hash.slice(1));
  const initialIndex = Math.max(
    0,
    Math.min(count - 1, Number(initial.get("step")) || 0),
  );
  const [position, setPosition] = useState(initialIndex);
  const [cursor, setCursor] = useState(initialIndex);
  const [mode, setMode] = useState<"detail" | "grid">(
    initial.get("view") === "grid" ? "grid" : "detail",
  );
  const [gridPage, setGridPage] = useState(
    Math.floor(initialIndex / PAGE_SIZE),
  );
  const [prefs, setPrefs] = usePreferences();
  const [inspector, setInspector] = useState(false);
  const inspectorOpener = useRef<HTMLElement | null>(null);
  const inspectorButton = useRef<HTMLButtonElement>(null);
  const [settings, setSettings] = useState(false);
  const [help, setHelp] = useState(false);
  const [zoom, setZoom] = useState(false);
  const [notice, setNotice] = useState("");
  const [compare, setCompare] = useState(false);
  const [hover, setHover] = useState<{
    index: number;
    x: number;
    y: number;
  } | null>(null);
  const [peek, setPeek] = useState<typeof hover>(null);
  const strip = useRef<HTMLDivElement>(null);
  const overview = useRef<HTMLDivElement>(null);
  const detailScroll = useRef<HTMLDivElement>(null);
  const helpDialog = useRef<HTMLDialogElement>(null);
  const zoomDialog = useRef<HTMLDialogElement>(null);
  const step = steps[position];
  const projection = step ? projectStep(step) : null;
  const stripStart = Math.max(0, Math.min(position - 10, count - 21));
  const pageCount = Math.max(1, Math.ceil(count / PAGE_SIZE));

  function open(index: number) {
    if (!count) return;
    const next = Math.max(0, Math.min(count - 1, Math.trunc(index)));
    setPosition(next);
    setCursor(next);
    setMode("detail");
    setGridPage(Math.floor(next / PAGE_SIZE));
    detailScroll.current?.scrollTo(0, 0);
  }
  function toggleMode() {
    if (mode === "detail") {
      setCursor(position);
      setGridPage(Math.floor(position / PAGE_SIZE));
      setMode("grid");
    } else open(cursor);
  }
  function toggleInspector() {
    if (inspector) closeInspector();
    else {
      inspectorOpener.current = document.activeElement as HTMLElement;
      open(mode === "grid" ? cursor : position);
      setInspector(true);
    }
  }
  function closeInspector() {
    setInspector(false);
    requestAnimationFrame(() => {
      const target = inspectorOpener.current?.isConnected ? inspectorOpener.current : inspectorButton.current;
      target?.focus();
    });
  }
  function moveCursor(next: number) {
    setCursor(next);
    setGridPage(Math.floor(next / PAGE_SIZE));
    requestAnimationFrame(() =>
      overview.current
        ?.querySelector<HTMLButtonElement>(`[data-position="${next}"]`)
        ?.focus(),
    );
  }
  function resize(
    event: PointerEvent<HTMLDivElement>,
    kind: "sidebar" | "timeline" | "inspector",
  ) {
    const target = event.currentTarget;
    const start = kind === "timeline" ? event.clientY : event.clientX;
    const value = prefs[kind];
    target.setPointerCapture(event.pointerId);
    const onMove = (e: globalThis.PointerEvent) => {
      const delta =
        kind === "timeline" ? (e.clientY - start) * (prefs.dock === "bottom" ? -1 : 1)
          : (e.clientX - start) * (kind === "inspector" ? -1 : 1);
      setPrefs((p) => ({
        ...p,
        [kind]: Math.max(
          kind === "sidebar" ? 280 : kind === "inspector" ? 320 : 110,
          Math.min(kind === "sidebar" ? 600 : kind === "inspector" ? 720 : 400, value + delta),
        ),
      }));
    };
    const finish = () => {
      target.removeEventListener("pointermove", onMove);
      target.removeEventListener("pointerup", finish);
      target.removeEventListener("pointercancel", finish);
    };
    target.addEventListener("pointermove", onMove);
    target.addEventListener("pointerup", finish);
    target.addEventListener("pointercancel", finish);
  }
  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setNotice("已复制");
    } catch {
      setNotice("无法访问剪贴板，可从原文手动复制");
    }
  }

  useEffect(() => {
    setPeek(null);
    if (!hover) return;
    const timer = setTimeout(() => setPeek(hover), 150);
    return () => clearTimeout(timer);
  }, [hover]);
  useEffect(() => {
    const clear = () => setHover(null);
    window.addEventListener("resize", clear);
    window.addEventListener("blur", clear);
    document.addEventListener("scroll", clear, true);
    return () => {
      window.removeEventListener("resize", clear);
      window.removeEventListener("blur", clear);
      document.removeEventListener("scroll", clear, true);
    };
  }, []);
  useEffect(() => {
    setHover(null);
    const index = mode === "grid" ? cursor : position;
    const params = new URLSearchParams({
      snapshot: detail.snapshot_id,
      step: String(index),
      view: mode,
    });
    history.replaceState(null, "", `#${params}`);
    (mode === "grid" ? overview : strip).current
      ?.querySelector('[aria-current="step"]')
      ?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [position, cursor, mode, detail.snapshot_id]);
  useEffect(() => {
    const restore = () => {
      const params = new URLSearchParams(location.hash.slice(1));
      if (params.get("snapshot") !== detail.snapshot_id) return;
      const parsed = Number(params.get("step"));
      const next = Number.isFinite(parsed)
        ? Math.max(0, Math.min(count - 1, Math.trunc(parsed)))
        : 0;
      setPosition(next);
      setCursor(next);
      setGridPage(Math.floor(next / PAGE_SIZE));
      setMode(params.get("view") === "grid" ? "grid" : "detail");
    };
    window.addEventListener("hashchange", restore);
    return () => window.removeEventListener("hashchange", restore);
  }, [detail.snapshot_id, count]);

  useEffect(() => {
    if (help) helpDialog.current?.showModal();
    else helpDialog.current?.close();
  }, [help]);
  useEffect(() => {
    if (zoom) zoomDialog.current?.showModal();
    else zoomDialog.current?.close();
  }, [zoom]);
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement;
      if (
        event.defaultPrevented ||
        event.isComposing ||
        target.closest(
          'input,textarea,select,[contenteditable="true"],summary,[role="separator"]',
        )
      )
        return;
      if (help || zoom || settings) return;
      const modifier = event.ctrlKey || event.metaKey;
      if (
        modifier &&
        (event.key === "ArrowLeft" || event.key === "ArrowRight")
      ) {
        event.preventDefault();
        onTaskNavigate(event.key === "ArrowLeft" ? -1 : 1);
        return;
      }
      if (event.key === "PageDown" || event.key === "PageUp") {
        event.preventDefault();
        onTaskNavigate(event.key === "PageUp" ? -1 : 1);
        return;
      }
      const toggle =
        (event.key.toLowerCase() === "g" || event.code === "KeyG") &&
        ((event.altKey && !modifier && !event.shiftKey) ||
          (event.ctrlKey &&
            event.shiftKey &&
            !event.metaKey &&
            !event.altKey) ||
          (event.metaKey &&
            !event.ctrlKey &&
            !event.altKey &&
            !event.shiftKey));
      if (toggle) {
        event.preventDefault();
        toggleMode();
        return;
      }
      if (modifier || event.altKey) return;
      if (["?", "h"].includes(event.key)) {
        event.preventDefault();
        setHelp(true);
        return;
      }
      if (event.key === "i") {
        event.preventDefault();
        toggleInspector();
        return;
      }
      if (event.key === "Escape" && inspector) {
        event.preventDefault();
        closeInspector();
        return;
      }
      if (event.key === "l") {
        event.preventDefault();
        onReload();
        return;
      }
      if (event.key === "Escape" && mode === "detail") {
        event.preventDefault();
        toggleMode();
        return;
      }
      if (event.key === "Enter" && mode === "grid") {
        event.preventDefault();
        open(cursor);
        return;
      }
      if (
        count &&
        [
          "ArrowLeft",
          "ArrowRight",
          "Home",
          "End",
          ...(mode === "grid" ? ["ArrowUp", "ArrowDown"] : []),
        ].includes(event.key)
      ) {
        event.preventDefault();
        const cols = overview.current
          ? getComputedStyle(overview.current).gridTemplateColumns.split(" ")
              .length
          : prefs.columns;
        const current = mode === "grid" ? cursor : position;
        const visibleIndex = visibleCursor(entries, visible, current);
        const next = mode === "grid"
          ? visible[navigationTarget(event.key, visibleIndex, visible.length, cols, true)]
          : navigationTarget(event.key, current, count, cols, false);
        if (mode === "grid") moveCursor(next);
        else open(next);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  function card(index: number, compact: boolean) {
    const item = steps[index];
    const view = projectStep(item);
    const selected = (compact ? position : cursor) === index;
    return (
      <button
        key={index}
        type="button"
        data-position={index}
        className={`step-card ${selected ? "selected" : ""}`}
        data-source-verdict={
          signals.steps[index].includes("sourceError")
            ? "error"
            : signals.steps[index].includes("sourceCorrect")
              ? "correct"
              : undefined
        }
        aria-label={`打开 Step ${index}`}
        aria-current={selected ? "step" : undefined}
        tabIndex={
          selected ||
          (!compact &&
            Math.floor(cursor / PAGE_SIZE) !== gridPage &&
            index === gridPage * PAGE_SIZE)
            ? 0
            : -1
        }
        onFocus={() => {
          if (!compact) setCursor(index);
        }}
        onClick={() => {
          setHover(null);
          open(index);
        }}
        onMouseEnter={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          setHover({
            index,
            x: Math.max(
              8,
              Math.min(
                innerWidth - 370,
                rect.right + 8 < innerWidth - 360
                  ? rect.right + 8
                  : rect.left - 368,
              ),
            ),
            y: Math.max(8, Math.min(innerHeight - 250, rect.top)),
          });
        }}
        onMouseLeave={() => setHover(null)}
        title={`Step ${index} · ${view.actions.map(actionLabel).join(" / ") || "未解析动作"}\n${text(view.semantic?.value)}`}
      >
        {!compact && <span className="step-card-index">{index}<SignalBadges kinds={signals.steps[index]} /></span>}
        {compact && <span className="step-card-signals"><SignalBadges kinds={signals.steps[index]} /></span>}
        <EvidenceImage
          client={client}
          detail={detail}
          step={item}
          position={index}
          thumbnail
          markers={prefs.markers} bbox={prefs.display.bbox}
          space={prefs.space}
        />
        {compact && <span className="step-card-index">{index}</span>}
        {!compact && (
          <span className="step-card-semantic">
            {view.semantic
              ? text(view.semantic.value)
              : view.actions.map(actionLabel).join(" / ") || "未记录动作语义"}
          </span>
        )}
      </button>
    );
  }

  function renderEntry(entry: TimelineEntry, compact: boolean) {
    if (entry.start === entry.end) return card(entry.start, compact);
    const current = compact ? position : cursor;
    const selected = current >= entry.start && current <= entry.end;
    const indices = Array.from({ length: entry.end - entry.start + 1 }, (_, i) => entry.start + i);
    const kinds = [...new Set(indices.flatMap(index => signals.steps[index]))];
    const previewIndices = indices.slice(-3);
    return (
      <RetryStack key={entry.key} label={`${entry.start}–${entry.end}`} count={indices.length}
        current={selected} position={selected ? current : entry.end}
        tabIndex={selected || (!compact && Math.floor(cursor / PAGE_SIZE) !== gridPage && entry.start === gridPage * PAGE_SIZE) ? 0 : -1}
        onFocus={() => { if (!compact) setCursor(selected ? cursor : entry.end); }}
        expanded={expanded.has(entry.key)} compact={compact}
        onToggle={() => {
          setHover(null);
          setExpanded(previous => {
            const next = new Set(previous);
            if (next.has(entry.key)) next.delete(entry.key);
            else next.add(entry.key);
            return next;
          });
        }}
        verdict={signals.steps[entry.end].includes("sourceError") ? "error" : signals.steps[entry.end].includes("sourceCorrect") ? "correct" : undefined}
        badges={<SignalBadges kinds={kinds} />}
        previews={previewIndices.map(index => (
          <EvidenceImage key={index} client={client} detail={detail} step={steps[index]} position={index}
            thumbnail markers={prefs.markers} bbox={prefs.display.bbox} space={prefs.space} />
        ))}>
        {indices.map(index => card(index, compact))}
      </RetryStack>
    );
  }

  const style = {
    "--sidebar-width": prefs.collapsed ? "0px" : `${prefs.sidebar}px`,
    "--timeline-height": `${prefs.timeline}px`,
    "--inspector-width": `${prefs.inspector}px`,
  } as CSSProperties;
  return (
    <div
      className={`workbench ${prefs.collapsed ? "sidebar-collapsed" : ""}`}
      style={style}
    >
      <aside
        className="task-sidebar workbench-sidebar"
        aria-label="任务信息"
        inert={prefs.collapsed || undefined}
      >
        <TaskSidebar detail={detail} position={position} onStep={open} display={prefs.display} />
      </aside>
      <div
        className="sidebar-separator"
        role="separator"
        aria-label="调整任务栏宽度"
        aria-orientation="vertical"
        aria-valuenow={Math.round(prefs.sidebar)}
        aria-valuemin={280}
        aria-valuemax={600}
        tabIndex={0}
        onPointerDown={(event) => resize(event, "sidebar")}
        onKeyDown={(event) => {
          if (["ArrowLeft", "ArrowRight"].includes(event.key)) {
            event.preventDefault();
            setPrefs((p) => ({
              ...p,
              sidebar: Math.max(
                280,
                Math.min(
                  600,
                  p.sidebar + (event.key === "ArrowRight" ? 20 : -20),
                ),
              ),
            }));
          }
        }}
      />
      <main
        className={`workbench-main ${inspector ? "inspector-open" : ""} ${mode === "grid" ? "grid-mode" : ""} dock-${prefs.dock}`}
      >
        <div className="workbench-tools">
          <button
            className="icon-button"
            aria-label={prefs.collapsed ? "展开任务信息" : "收起任务信息"}
            onClick={() => setPrefs((p) => ({ ...p, collapsed: !p.collapsed }))}
          >
            ☰
          </button>
          <span className="overview-context">
            {mode === "grid"
              ? `轨迹总览 · 当前 Step ${cursor}`
              : `Step ${position}`}{" "}
            <small>/ {count}</small>
          </span>
          <div className="tool-spacer" />
          <button ref={inspectorButton} aria-expanded={inspector} aria-keyshortcuts="i" onClick={toggleInspector}>打点详情</button>
          {entries.some(entry => entry.end > entry.start) && (
            <button onClick={() => {
              setHover(null);
              const groups = entries.filter(entry => entry.end > entry.start);
              setExpanded(groups.some(entry => !expanded.has(entry.key))
                ? new Set(groups.map(entry => entry.key)) : new Set());
            }}>
              {entries.some(entry => entry.end > entry.start && !expanded.has(entry.key)) ? "展开全部重试" : "收起全部重试"}
            </button>
          )}
          <button aria-haspopup="dialog" onClick={() => setSettings(true)}>显示选项</button>

        </div>
        {!count ? (
          <div className="empty-steps">
            该轨迹没有步骤，仍可查看来源与导出原文。
          </div>
        ) : mode === "grid" ? (
          <section className="grid-panel">
            <div className="grid-legend">
              <StepLegend kinds={signals.legend} />
            </div>
            <div className="grid-controls">
              <span>方向键定位 · Enter 或点击打开</span>
            </div>
            <div
              ref={overview}
              className="step-grid"
              style={{
                gridTemplateColumns: `repeat(${prefs.columns}, minmax(0, 1fr))`,
              }}
              aria-label="步骤网格"
            >
              {windowEntries(entries, gridPage * PAGE_SIZE, (gridPage + 1) * PAGE_SIZE).map(entry => renderEntry(entry, false))}
            </div>
            {pageCount > 1 && (
              <div className="grid-pager">
                <button
                  disabled={!gridPage}
                  onClick={() => setGridPage((p) => p - 1)}
                >
                  上一页
                </button>
                <span>
                  {gridPage + 1} / {pageCount}
                </span>
                <button
                  disabled={gridPage === pageCount - 1}
                  onClick={() => setGridPage((p) => p + 1)}
                >
                  下一页
                </button>
              </div>
            )}
          </section>
        ) : (
          <>
            <section className="timeline-panel" aria-label="缩略图导航">
              <div ref={strip} className="filmstrip">
                {windowEntries(entries, stripStart, stripStart + 21).map(entry => renderEntry(entry, true))}
              </div>
              <StepLegend kinds={signals.legend} />
            </section>
            <div
              className="timeline-separator"
              role="separator"
              aria-label="调整小图条高度"
              aria-orientation="horizontal"
              aria-valuenow={Math.round(prefs.timeline)}
              aria-valuemin={110}
              aria-valuemax={400}
              tabIndex={0}
              onPointerDown={(event) => resize(event, "timeline")}
              onKeyDown={(event) => {
                if (["ArrowUp", "ArrowDown"].includes(event.key)) {
                  event.preventDefault();
                  const sign =
                    (event.key === "ArrowDown" ? 1 : -1) *
                    (prefs.dock === "bottom" ? -1 : 1);
                  setPrefs((p) => ({
                    ...p,
                    timeline: Math.max(
                      110,
                      Math.min(400, p.timeline + sign * 20),
                    ),
                  }));
                }
              }}
            />
            <div ref={detailScroll} className="step-scroll">
              <div className="step-heading">
                <h2>Step {position}</h2>
                <div className="step-navigation">
                  <button
                    aria-label="上一步"
                    onClick={() => open((position - 1 + count) % count)}
                  >
                    ←
                  </button>
                  <input
                    aria-label="Step 序号"
                    type="number"
                    min={0}
                    max={count - 1}
                    value={position}
                    onChange={(e) => {
                      if (Number.isFinite(e.target.valueAsNumber))
                        open(e.target.valueAsNumber);
                    }}
                  />
                  <button
                    aria-label="下一步"
                    onClick={() => open((position + 1) % count)}
                  >
                    →
                  </button>
                  <button
                    disabled={typeof step.value?.raw_model_output !== "string"}
                    onClick={() => {
                      const raw = step.value?.raw_model_output;
                      if (typeof raw === "string") void copy(raw);
                    }}
                  >
                    复制原文
                  </button>
                </div>
              </div>
              <div className="step-content">
                <div
                  className={`screenshot-column ${compare ? "comparing" : ""}`}
                >
                  <div className="screenshot-mode">
                    <button
                      aria-pressed={!compare}
                      onClick={() => setCompare(false)}
                    >
                      单图
                    </button>
                    <button
                      aria-pressed={compare}
                      onClick={() => setCompare(true)}
                    >
                      截图对照
                    </button>
                  </div>
                  <div className="screenshot-pair">
                    <div className="comparison-frame">
                      {compare && (
                        <span className="comparison-label">当前步骤截图</span>
                      )}
                      <EvidenceImage
                        key={position}
                        client={client}
                        detail={detail}
                        step={step}
                        position={position}
                        markers={prefs.markers} bbox={prefs.display.bbox}
                        space={prefs.space}
                      />
                    </div>
                    {compare && (
                      <EvidenceComparison
                        key={position}
                        client={client}
                        detail={detail}
                        position={position}
                      />
                    )}
                  </div>
                  <div className="screenshot-actions">
                    <button
                      onClick={() => setZoom(true)}
                      disabled={
                        !step.image || detail.missing_media.includes(step.image)
                      }
                    >
                      放大截图
                    </button>
                    <span>
                      {projection?.actions.map(actionLabel).join(" / ") ||
                        "未解析动作"}
                    </span>
                  </div>
                  {prefs.markers &&
                  prefs.space === "unknown" &&
                  projection?.actions.length ? (
                    <p className="coordinate-note">
                      坐标空间未声明；选择显示坐标后绘制标记。
                    </p>
                  ) : null}
                </div>
                <StepEvidenceFields
                  step={step}
                  projection={projection}
                  signals={signals.steps[position]}
                  display={prefs.display}
                />
              </div>
            </div>
          </>
        )}
      </main>
      <footer
        className="workbench-footer"
        title="任务导航范围为已加载的快照列表"
      >
        <div>
          <button
            aria-label="上一任务"
            disabled={taskIndex <= 0}
            onClick={() => onTaskNavigate(-1)}
          >
            ←
          </button>
          <span>
            {taskIndex >= 0 ? taskIndex + 1 : "—"} / {taskCount} 任务
          </span>
          <button
            aria-label="下一任务"
            disabled={taskIndex < 0 || taskIndex >= taskCount - 1}
            onClick={() => onTaskNavigate(1)}
          >
            →
          </button>
          <span>来源版本 {detail.source_version ?? "未知"}</span>
          <button onClick={onReload}>↻ 刷新</button>
        </div>
        <span className="footer-status" role="status">
          {notice || status}
        </span>
        <div>
          <div className="workbench-navigator-statusbar">
            <TimelineControls
              visible={true}
              mode={mode === "grid" ? "grid" : "timeline"}
              columns={prefs.columns}
              size={13 - prefs.columns}
              actions={{
                min: 3,
                max: 10,
                setMode: (next) => {
                  if (next === "grid") {
                    setCursor(position);
                    setGridPage(Math.floor(position / PAGE_SIZE));
                    setMode("grid");
                  } else open(mode === "grid" ? cursor : position);
                },
                setSize: (size) =>
                  setPrefs((p) => ({
                    ...p,
                    columns: 13 - Math.max(3, Math.min(10, size)),
                  })),
                openJson: onJson,
              }}
            />
          </div>
          <span className="read-only">只读浏览</span>
          <button onClick={() => onDownload("trajectory")}>导出 JSON</button>
          <button onClick={() => onDownload("bundle")}>导出包</button>
          <button onClick={() => setHelp(true)}>⌨ 快捷键</button>
        </div>
      </footer>
      {inspector && <EvidenceInspector detail={detail} position={position} width={prefs.inspector}
        onStep={open} onClose={closeInspector} onReload={onReload}
        onResize={event => resize(event, "inspector")}
        onWidth={width => setPrefs(p => ({ ...p, inspector: Math.max(320, Math.min(720, width)) }))} />}
      <DisplaySettings
        open={settings}
        value={prefs.display}
        layout={prefs}
        onLayoutChange={layout => setPrefs(p => ({ ...p, ...layout }))}
        onChange={display => setPrefs(p => ({ ...p, display }))}
        onClose={() => setSettings(false)}
      />
      {peek && !help && !zoom && !settings && (
        <StepPreview
          client={client}
          detail={detail}
          target={peek}
          markers={prefs.markers} bbox={prefs.display.bbox}
          space={prefs.space}
        />
      )}
      <dialog
        ref={helpDialog}
        className="shortcut-dialog"
        onClose={() => setHelp(false)}
        aria-label="快捷键"
      >
        <div className="dialog-heading">
          <h2>浏览快捷键</h2>
          <button autoFocus onClick={() => setHelp(false)}>
            关闭
          </button>
        </div>
        <dl>
          <dt>← / →</dt>
          <dd>上一 / 下一步（首尾循环）</dd>
          <dt>↑ / ↓</dt>
          <dd>Grid 按行定位</dd>
          <dt>Home / End</dt>
          <dd>首步 / 末步</dd>
          <dt>Enter</dt>
          <dd>打开 Grid 当前步骤</dd>
          <dt>Escape</dt>
          <dd>返回 Grid / 关闭弹窗</dd>
          <dt>Alt+G / Ctrl+Shift+G / ⌘G</dt>
          <dd>切换 Grid 与单步</dd>
          <dt>Ctrl/⌘ + ← / →，PgUp / PgDn</dt>
          <dd>上一 / 下一任务（已加载列表）</dd>
          <dt>I</dt>
          <dd>打开 / 关闭打点详情</dd>
          <dt>L</dt>
          <dd>刷新当前快照</dd>
          <dt>H / ?</dt>
          <dd>显示快捷键</dd>
        </dl>
        <p>输入框中不接管浏览快捷键。编辑、保存与审核另行接入。</p>
      </dialog>
      <dialog
        ref={zoomDialog}
        className="image-dialog"
        onClose={() => setZoom(false)}
        aria-label="原图查看"
      >
        <div className="dialog-heading">
          <h2>Step {position} · 来源截图</h2>
          <button autoFocus onClick={() => setZoom(false)}>
            关闭
          </button>
        </div>
        {step && (
          <EvidenceImage
            client={client}
            detail={detail}
            step={step}
            position={position}
            markers={prefs.markers} bbox={prefs.display.bbox}
            space={prefs.space}
          />
        )}
      </dialog>
    </div>
  );
}
