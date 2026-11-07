import { useId, type MouseEvent, type ReactNode } from "react";
import { ExpandableText } from "./ExpandableText";
import "./styles.css";
import {
  hasValue,
  text,
  type EvaluationView,
  type Field,
  type Grader,
  type ResultSource,
  type ResultFilter,
  type ViewState,
} from "./contracts";

type Props = {
  queueStatus?: ReactNode;
  view: EvaluationView;
  state: ViewState;
  onState: (state: ViewState) => void;
  onStep?: (event: MouseEvent<HTMLAnchorElement>, index: number) => void;
};
const statusText = (status: boolean | null | undefined) =>
  status === true
    ? "正确"
    : status === false
      ? "错误"
      : status === null
        ? "不确定"
        : "未判定";
const statusClass = (status: boolean | null | undefined) =>
  status === true
    ? "pass"
    : status === false
      ? "fail"
      : status === null
        ? "unknown"
        : "unassessed";

function Fields({ fields }: { fields: Field[] }) {
  return (
    <>
      {fields
        .filter((field) => field.key === "source_raw" || hasValue(field.value))
        .map((field, i) => (
          <details className="ev-raw" key={`${field.key}-${i}`}>
            <summary>{field.title || field.key || "原始结果"}</summary>
            <pre>{text(field.value)}</pre>
          </details>
        ))}
    </>
  );
}

function Reference({ source }: { source: ResultSource }) {
  if (source.relation === "same_snapshot") return null;
  return (
    <span
      className="ev-reference"
      title={source.bindingLabel || "输入关联未核对"}
    >
      参考结果
    </span>
  );
}
function SourceDetails({ source }: { source: ResultSource }) {
  return (
    <>
      <p className="ev-source-label">{source.bindingLabel}</p>
      <details className="ev-raw">
        <summary>评估来源</summary>
        <pre>{JSON.stringify(source.raw, null, 2)}</pre>
      </details>
    </>
  );
}

export function Panel({ view, state, onState, onStep, queueStatus }: Props) {
  const panelId = useId();
  const stepLinks = (indices: number[], evidence = false) =>
    indices.map((index, i) => {
      const label = `Step ${index}`;
      const href = `#snapshot=${encodeURIComponent(view.snapshotId)}&step=${index}&view=detail`;
      return view.taskId && view.knownSteps.includes(index) ? (
        <a
          key={`${index}-${i}`}
          href={href}
          title={evidence ? "任务级评估的证据步骤" : undefined}
          onClick={(event) => onStep?.(event, index)}
        >
          {label}
        </a>
      ) : (
        <span
          className="ev-unlocated"
          key={`${index}-${i}`}
          title={evidence ? "任务级评估的证据步骤" : undefined}
        >
          {label}（无法定位）
        </span>
      );
    });
  const renderGrader = (grader: Grader) => {
    const failures = grader.items.filter(
      (item) => item.status === false,
    ).length;
    const unknowns = grader.items.filter((item) => item.status === null).length;
    const correct = grader.items.filter((item) => item.status === true).length;
    const unassessed = grader.items.filter(
      (item) => item.status === undefined,
    ).length;
    const open = state.open === grader.key;
    const filter = open ? state.filter : "issues";
    const visible = grader.items.filter(
      (item) =>
        (filter === "issues" && item.status !== true) ||
        String(item.status) === filter,
    );
    const summary = grader.items.length
      ? `${failures} 项错误 · ${unknowns} 项不确定 · ${correct} 项正确 · ${unassessed} 项未判定`
      : grader.summary ||
        (grader.status !== undefined ? statusText(grader.status) : "原始结果");
    const contentId = `${panelId}-ev-grader-${encodeURIComponent(grader.key)}`;
    const selectFilter = (value: ResultFilter) =>
      onState({
        ...state,
        open: grader.key,
        filter: open && filter === value ? "issues" : value,
      });
    return (
      <section className="ev-grader" key={grader.key}>
        <div className="ev-grader-heading">
          <button
            className="ev-grader-toggle"
            type="button"
            title={
              grader.version
                ? `${grader.title}\nJudge 版本：${grader.version}`
                : grader.title
            }
            aria-label={`${grader.title} · ${summary}`}
            aria-expanded={open}
            aria-controls={contentId}
            onClick={() =>
              onState({
                ...state,
                open: open ? null : grader.key,
                filter: "issues",
              })
            }
          >
            <span className="ev-chevron" aria-hidden="true">
              {open ? "▾" : "▸"}
            </span>
            <strong>{grader.title}</strong>
          </button>
          {grader.version && (
            <span
              className="ev-provider ev-grader-version"
              title={`Judge 版本：${grader.version}`}
            >
              {grader.version}
            </span>
          )}
          {grader.items.length ? (
            <span
              className="ev-grader-counts"
              role="group"
              aria-label={`${grader.title}：${summary}；携带 ${grader.items.length} 项，已判定 ${grader.items.length - unassessed} 项`}
            >
              <button
                type="button"
                className="ev-grader-tally ev-fail"
                data-status="false"
                data-count={failures}
                disabled={!failures}
                aria-pressed={open && filter === "false"}
                aria-controls={contentId}
                aria-label={`${grader.title}：仅看错误，${failures} 项`}
                title={`错误：${failures} 项；${filter === "false" ? "再次点击恢复默认" : "点击仅看错误"}`}
                onClick={() => selectFilter("false")}
              >
                <span aria-hidden="true">{failures}</span>
                <span aria-hidden="true">✕</span>
              </button>
              <span className="ev-tally-divider" aria-hidden="true">
                /
              </span>
              <button
                type="button"
                className="ev-grader-tally ev-unknown"
                data-status="null"
                data-count={unknowns}
                disabled={!unknowns}
                aria-pressed={open && filter === "null"}
                aria-controls={contentId}
                aria-label={`${grader.title}：仅看不确定，${unknowns} 项`}
                title={`不确定：${unknowns} 项；${filter === "null" ? "再次点击恢复默认" : "点击仅看不确定"}`}
                onClick={() => selectFilter("null")}
              >
                <span aria-hidden="true">{unknowns}</span>
                <span aria-hidden="true">?</span>
              </button>
              <span className="ev-tally-divider" aria-hidden="true">
                /
              </span>
              <button
                type="button"
                className="ev-grader-tally ev-pass"
                data-status="true"
                data-count={correct}
                disabled={!correct}
                aria-pressed={open && filter === "true"}
                aria-controls={contentId}
                aria-label={`${grader.title}：仅看正确，${correct} 项`}
                title={`正确：${correct} 项；${filter === "true" ? "再次点击恢复默认" : "点击仅看正确"}`}
                onClick={() => selectFilter("true")}
              >
                <span aria-hidden="true">{correct}</span>
                <span aria-hidden="true">✓</span>
              </button>
              {unassessed > 0 && (
                <>
                  <span className="ev-tally-divider" aria-hidden="true">
                    /
                  </span>
                  <button
                    type="button"
                    className="ev-grader-tally ev-unassessed"
                    aria-pressed={open && filter === "undefined"}
                    aria-controls={contentId}
                    aria-label={`${grader.title}：仅看未判定，${unassessed} 项`}
                    onClick={() => selectFilter("undefined")}
                  >
                    <span>{unassessed}</span>
                    <span>—</span>
                  </button>
                </>
              )}
            </span>
          ) : (
            <span className="ev-grader-summary ev-summary">{summary}</span>
          )}
          <Reference source={grader.source} />
        </div>
        <div id={contentId} hidden={!open}>
          <SourceDetails source={grader.source} />
          {grader.items.length > 0 && (
            <>
              {visible.length ? (
                <ul
                  className="ev-results"
                  aria-label={`${grader.title}评估明细`}
                >
                  {visible.map((item) => (
                    <li className="ev-result" key={grader.items.indexOf(item)}>
                      <div
                        aria-label={
                          grader.scope === "task"
                            ? "证据和结果"
                            : grader.scope === "step"
                              ? "步骤和结果"
                              : "关联和结果"
                        }
                      >
                        <div className="ev-step-links">
                          {item.references ? (
                            item.references.length ? (
                              item.references.map((ref, i) =>
                                ref.position !== null ? (
                                  <a
                                    key={i}
                                    href={`#snapshot=${encodeURIComponent(view.snapshotId)}&step=${ref.position}&view=detail`}
                                    title={ref.label}
                                    onClick={(event) =>
                                      onStep?.(event, ref.position!)
                                    }
                                  >
                                    Step {ref.position}
                                  </a>
                                ) : (
                                  <span
                                    className="ev-unlocated"
                                    key={i}
                                    title={ref.reason}
                                  >
                                    {ref.label}（无法定位）
                                  </span>
                                ),
                              )
                            ) : grader.scope === "task" ? (
                              "任务级"
                            ) : (
                              "未定位"
                            )
                          ) : (
                            <>
                              {stepLinks(item.steps)}
                              {stepLinks(item.evidence, true)}
                              {!item.steps.length &&
                                !item.evidence.length &&
                                (grader.scope === "task" ? "任务级" : "未定位")}
                            </>
                          )}
                        </div>
                        <span
                          className={`ev-status ev-${statusClass(item.status)}`}
                        >
                          {statusText(item.status)}
                        </span>
                      </div>
                      <div aria-label="原因">
                        <ExpandableText
                          text={item.reason}
                          label="评估原因"
                          emptyText="未提供原因"
                          lines={3}
                        />
                        <Fields fields={item.fields} />
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="ev-empty">
                  {filter === "issues" ? "已评结果均正确" : "当前筛选无结果"}
                </p>
              )}
            </>
          )}
          {!grader.items.length && grader.summary && (
            <ExpandableText
              text={grader.summary}
              label="评估原因"
              emptyText="未提供原因"
              lines={3}
            />
          )}
          <Fields fields={grader.fields} />
        </div>
      </section>
    );
  };
  return (
    <div className="ev-panel">
      <section className="ev-machine" aria-label="机器评估">
        <header>
          <div className="ev-machine-identity">
            <h3 className="ev-module-title">ORM</h3>
            {queueStatus}
            {view.machine.provider && (
              <span
                className="ev-provider"
                title={`Provider: ${view.machine.provider}`}
              >
                {view.machine.provider}
              </span>
            )}
          </div>
          <div className="ev-verdicts">
            {view.machine.carried && <Reference source={view.machine.source} />}
            {view.machine.statuses.length ? (
              view.machine.statuses.map((status, i) => (
                <span
                  className="ev-verdict"
                  data-status={view.machine.statusCodes[i]}
                  title={status}
                  key={i}
                >
                  {status}
                </span>
              ))
            ) : (
              <span className="ev-verdict">
                {view.machine.carried ? "状态未声明" : "结果未携带"}
              </span>
            )}
          </div>
        </header>
        {!view.machine.carried ? (
          <p className="ev-empty">
            当前包未携带 ORM 结果，无法据此判断是否已评估。
          </p>
        ) : (
          <>
            <SourceDetails source={view.machine.source} />
            {view.machine.failureReasons.length > 0 && (
              <div className="ev-facts ev-failure-reasons">
                <span>错误归因</span>
                <p>{view.machine.failureReasons.join(" / ")}</p>
              </div>
            )}
            <div className="ev-facts">
              <span>判定依据</span>
              <ExpandableText
                text={view.machine.reasoning}
                label="判定依据"
                emptyText="未提供判定依据"
              />
            </div>
          </>
        )}
      </section>
      {view.graders.length > 0 ? (
        <section className="ev-specialists" aria-label="专项评估">
          <h3 className="ev-module-title">专项</h3>
          {view.graders.map(renderGrader)}
        </section>
      ) : (
        <section className="ev-specialists" aria-label="专项评估">
          <h3 className="ev-module-title">专项</h3>
          <p className="ev-empty">当前包未携带专项结果。</p>
        </section>
      )}
    </div>
  );
}
