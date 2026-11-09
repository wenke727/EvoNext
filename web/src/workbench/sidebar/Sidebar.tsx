import {
  useLayoutEffect,
  useRef,
  useState,
  type TextareaHTMLAttributes,
} from "react";
import type { SidebarProps, SidebarPorts } from "./contracts";
import {
  childItems,
  contextFlags,
  createdAt,
  guidance,
  instruction,
  integer,
  list,
  rawInstruction,
  record,
  text,
  validRange,
  type Task,
} from "./model";
import { ReadOnlyTags } from "./ReadOnlyTags";
import { uniqueTags } from "./tags";
import { EditButton } from "../components/EditButton";
import "./styles.css";

function GrowingTextarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      el.style.height = "auto";
      el.style.height = `${el.scrollHeight + el.offsetHeight - el.clientHeight}px`;
    };
    measure();
    let width = el.clientWidth;
    const observer = new ResizeObserver(() => {
      if (el.clientWidth !== width) {
        width = el.clientWidth;
        measure();
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [props.value]);
  return (
    <textarea
      {...props}
      ref={ref}
      rows={1}
      className="editable-textarea textarea-auto-grow"
    />
  );
}

function FieldHistory({
  task,
  field,
  disabled,
  onRestore,
}: {
  task: Task;
  field: string;
  disabled: boolean;
  onRestore(value: string): void;
}) {
  const backups =
    task[`${field}_bak`] == null
      ? []
      : Array.isArray(task[`${field}_bak`])
        ? list(task[`${field}_bak`])
        : [task[`${field}_bak`]];
  const [open, setOpen] = useState(false);
  const timestamps = list(task[`${field}_updated_at`]);
  if (!backups.length) return null;
  return (
    <span className="sidebar-history">
      <button
        type="button"
        className="small-btn"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        History ({backups.length})
      </button>
      {open && (
        <div className="sidebar-history-list">
          {backups.map((value, index) => {
            const timestamp = timestamps[index];
            const tuple = Array.isArray(timestamp) ? timestamp : [timestamp];
            return (
              <div key={index}>
                <div className="evaluation-machine-pred">
                  {createdAt(tuple[0])} {text(tuple[1])}
                </div>
                <pre>{text(value)}</pre>
                <button
                  type="button"
                  className="small-btn"
                  disabled={disabled}
                  onClick={() => {
                    onRestore(text(value));
                    setOpen(false);
                  }}
                >
                  恢复到草稿
                </button>
              </div>
            );
          })}
        </div>
      )}
    </span>
  );
}

function Lineage({ task, ports }: { task: Task; ports: SidebarPorts }) {
  const lineage = record(task.lineage),
    parent = text(lineage.parent_task_id || lineage.root_task_id);
  const derived = lineage.role === "derived_child";
  const range = validRange(
    { step_range: lineage.source_step_range },
    list(task.traj).length,
  );
  const items = childItems(task);
  return (
    <>
      {derived && (
        <div
          className="lineage-child-task-panel lineage-child-parent-panel"
          data-lineage-role="derived_child"
        >
          <div className="lineage-child-task-panel-body">
            <span>子任务</span>
            <span className="lineage-child-chip">
              来源步骤 {range.start ?? "?"}-{range.end ?? "?"}
            </span>
            {parent && ports.taskUrl(parent, range.start) && (
              <a
                className="lineage-child-parent-link"
                href={ports.taskUrl(parent, range.start)}
              >
                查看父任务来源步骤
              </a>
            )}
          </div>
        </div>
      )}
      {items.length > 0 && (
        <div
          className="lineage-child-task-panel"
          data-lineage-role={text(lineage.role) || "root"}
        >
          <div className="lineage-child-task-panel-head">
            <span className="lineage-child-task-panel-title">子任务划分</span>
          </div>
          <div className="lineage-child-task-panel-body">
            {items.map((item, index) => {
              const id = text(item.task_id),
                ordinal = integer(item.ordinal) ?? index + 1;
              const current =
                id === text(task.task_id) ||
                (derived &&
                  integer(item.ordinal) !== null &&
                  integer(item.ordinal) === integer(lineage.ordinal));
              const title =
                text(item.instruction).trim() || `子任务 ${ordinal}`;
              const range = validRange(item, list(task.traj).length);
              const label =
                range.start !== null || range.end !== null
                  ? `步骤 ${range.start ?? "?"}-${range.end ?? "?"}`
                  : "-";
              return (
                <div
                  className="lineage-child-task-chip"
                  key={`${id}:${ordinal}:${index}`}
                >
                  <span className="lineage-child-ordinal">{ordinal}.</span>
                  {current || !id || !ports.taskUrl(id) ? (
                    <span
                      className={`lineage-child-task-chip-title${current ? " lineage-child-current" : ""}`}
                      title={title}
                    >
                      {title}
                    </span>
                  ) : (
                    <a
                      className="lineage-child-task-chip-title lineage-child-task-link"
                      href={ports.taskUrl(id)}
                      title={title}
                    >
                      {title}
                    </a>
                  )}
                  {derived &&
                  parent &&
                  range.start !== null &&
                  range.start >= 0 &&
                  ports.taskUrl(parent, range.start) ? (
                    <a
                      className="lineage-child-range"
                      href={ports.taskUrl(parent, range.start)}
                    >
                      {label}
                    </a>
                  ) : range.valid ? (
                    <button
                      className="lineage-child-range"
                      type="button"
                      aria-label={`跳到子轨迹起始步骤 ${range.start}`}
                      onClick={() => ports.jump(range.start!)}
                    >
                      {label}
                    </button>
                  ) : (
                    <span
                      className="lineage-child-range lineage-child-range--disabled"
                      title="无效或越界的步骤范围"
                    >
                      {label}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}

function ClientReport({ task }: { task: Task }) {
  const report = record(task.client_report);
  const rows = [
    ["端侧来源", report.data_source],
    ["设备 SN", report.sn ?? report.SN],
    ["终止步骤", report.terminal_step_id],
    ["错误类型", report.error_type],
    ["错误说明", report.error_response],
  ].filter(([, value]) => text(value).trim());
  if (!rows.length) return null;
  return (
    <section
      className="client-report-section evaluation-orm-section"
      data-client-report="true"
      aria-label="端侧打点"
    >
      <div className="field-header evaluation-orm-header client-report-header">
        <div className="field-title evaluation-orm-title client-report-title">
          <b>端侧打点</b>
        </div>
      </div>
      {rows.map(([label, value]) => (
        <div
          className="evaluation-machine-pred client-report-line"
          key={text(label)}
        >
          <span className="client-report-label">{text(label)}:</span>
          <span className="client-report-value">{text(value)}</span>
        </div>
      ))}
    </section>
  );
}

function Scores({ task }: { task: Task }) {
  const rows = [
    ["Alignment Score", task.alignment_score],
    ["Efficiency Score", task.efficiency_score],
    ["Difficulty Score", task.task_difficulty],
  ].filter(
    ([, value]) => value !== undefined && value !== null && value !== "",
  );
  return rows.length ? (
    <dl className="sidebar-scores">
      {rows.map(([label, value]) => (
        <div key={text(label)}>
          <dt>{text(label)}</dt>
          <dd>{text(value)}</dd>
        </div>
      ))}
    </dl>
  ) : null;
}

function Feedback({ task }: { task: Task }) {
  const teach = record(task.feedback),
    repeats = list(task.repeat_feedbacks).map(record);
  const items = [...(Object.keys(teach).length ? [teach] : []), ...repeats];
  if (!items.length) return null;
  return (
    <details className="sidebar-feedback" open>
      <summary>
        反馈 <span>{items.length}</span>
      </summary>
      {items.map((item, index) => (
        <div className={`feedback-item vote-${text(item.vote)}`} key={index}>
          <div className="feedback-header">
            <span>
              {index === 0 && Object.keys(teach).length
                ? "Teach Feedback"
                : `Repeat Feedback ${index + 1}`}
            </span>
            <span className="vote-icon">
              {item.vote === "up" ? "✅" : item.vote === "down" ? "❌" : "➖"}
            </span>
            <span className="vote-text">
              {text(item.vote).toUpperCase() || "N/A"}
            </span>
            <span className="feedback-time">{createdAt(item.updated_at)}</span>
          </div>
          {item.message != null && (
            <p className="feedback-message">{text(item.message)}</p>
          )}
          {item.repeat_id != null && (
            <span className="repeat-id">Repeat ID: {text(item.repeat_id)}</span>
          )}
        </div>
      ))}
    </details>
  );
}

function Audit({
  task,
  options,
  disabled,
  onChange,
}: {
  task: Task;
  options: SidebarProps["preferences"]["auditOptions"];
  disabled: boolean;
  onChange(value: Task): void;
}) {
  const evaluation = record(task.evaluation),
    machine = record(record(evaluation.prediction).main_traj_orm),
    human = record(evaluation.main_traj_orm);
  function change(field: string, value: string) {
    const next = { ...human };
    if (!value) delete next[field];
    else next[field] = field === "response_correct" ? value === "true" : value;
    onChange(next);
  }
  const fields: [string, string, string[]][] = [
    ["task_status", "任务结果", options.taskStatusOptions],
    ["response_correct", "回复正确", ["true", "false"]],
    ["primary_error_cause", "一级错误原因", options.primaryErrorCauses],
    ["secondary_error_cause", "二级错误原因", options.secondaryErrorCauses],
  ];
  return (
    <section className="autojudge-v2-section autojudge-v2-main">
      <div className="field-header">
        <b>轨迹级主模型判定</b>
      </div>
      <div className="autojudge-v2-column-head">
        <span>判定维度</span>
        <span>机评证据</span>
        <span>人评结论</span>
      </div>
      {fields.map(([field, label, values]) => (
        <div className="autojudge-v2-row" key={field}>
          <label htmlFor={`audit-${field}`} className="autojudge-v2-label">
            {label}
          </label>
          <span className="autojudge-v2-machine">
            {text(machine[field]) || "—"}
          </span>
          <select
            id={`audit-${field}`}
            className="evaluation-select autojudge-v2-select"
            disabled={disabled}
            value={text(human[field])}
            onChange={(event) => change(field, event.target.value)}
          >
            <option value="">未评估</option>
            {[
              ...new Set([
                ...values,
                ...(human[field] != null ? [text(human[field])] : []),
              ]),
            ].map((value) => (
              <option key={value} value={value}>
                {value === "true" ? "正确" : value === "false" ? "错误" : value}
              </option>
            ))}
          </select>
        </div>
      ))}
      <div className="autojudge-v2-row autojudge-v2-row--reason">
        <label htmlFor="audit-reason" className="autojudge-v2-label">
          评估原因
        </label>
        <span className="autojudge-v2-machine">
          {text(machine.reasoning) || "—"}
        </span>
        <textarea
          id="audit-reason"
          rows={2}
          className="editable-textarea autojudge-v2-textarea"
          disabled={disabled}
          value={text(human.reasoning)}
          onChange={(event) => change("reasoning", event.target.value)}
          placeholder="填写人评原因"
        />
      </div>
    </section>
  );
}

export function Sidebar({
  sourceVersion,
  task,
  disabled,
  preferences,
  ports,
  evaluation,
  onField,
  onTags,
  onAudit,
}: SidebarProps) {
  const taskId = text(task.task_id),
    metadata = record(task.metadata),
    flags = contextFlags(task);
  const skill = guidance(task),
    raw = rawInstruction(task),
    app = text(record(metadata.pa_suggestion).app_name).trim();
  const level = text(
    record(metadata.task_ext_info).level ?? metadata.level,
  ).trim();
  const [copyFeedback, setCopyFeedback] = useState("");
  const [editOperations, setEditOperations] = useState(false);
  async function copy(value: string) {
    try {
      await ports.copy(value);
      setCopyFeedback("已复制");
    } catch {
      setCopyFeedback("复制失败");
    }
  }
  const qa = record(task.qa_review);
  return (
    <div className="task-sidebar-content" data-sidebar-react="true">
      <div className="sidebar-header-row">
        <div className="sidebar-header-main">
          <span className="task-id-label">
            <span className="task-id-caption">ID</span>
            <span className="task-id-copy-cluster">
              <span
                className="task-id-value"
                role="button"
                tabIndex={0}
                title={`${taskId || "-"} · 点击复制任务链接`}
                onClick={() => void copy(ports.taskUrl(taskId))}
                onContextMenu={(event) => {
                  event.preventDefault();
                  void copy(ports.taskUrl(taskId));
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    void copy(ports.taskUrl(taskId));
                  }
                }}
              >
                {taskId || "-"}
              </span>
              <button
                type="button"
                className="task-header-copy-btn"
                aria-label="复制任务 ID"
                title={copyFeedback || "复制任务 ID"}
                onClick={() => void copy(taskId)}
              >
                <svg
                  className="task-header-copy-icon"
                  viewBox="0 0 16 16"
                  aria-hidden="true"
                >
                  <rect x="5.25" y="2.25" width="8.5" height="8.5" rx="1.25" />
                  <rect x="2.25" y="5.25" width="8.5" height="8.5" rx="1.25" />
                </svg>
              </button>
            </span>
            {sourceVersion !== undefined && <span className="task-source-version" title="来源版本">v{sourceVersion ?? "?"}</span>}
            {preferences.showTime !== false && task.created_at != null && (
              <span
                className="task-created-at-label"
                title={`创建时间：${createdAt(task.created_at)}`}
              >
                {createdAt(task.created_at)}
              </span>
            )}
          </span>
        </div>
      </div>
      <div className="task-meta-rail">
        <span className="task-meta-key">标签</span>
        <ReadOnlyTags tags={uniqueTags(task.tags)} />
        {level && <span className="task-level-label">等级：{level}</span>}
      </div>
      <section className="instruction-block instruction-task-block sidebar-section task-section">
        <div className="field-header">
          <div className="field-title">
            <b className="task-title">任务</b>
          </div>
          <div className="field-actions">
            {flags.paTrace &&
              preferences.planner &&
              ports.plannerUrl(taskId) && (
                <a
                  className="task-pa-context-link task-pa-context-link--lineage"
                  href={ports.plannerUrl(taskId)}
                  target="_blank"
                  rel="noopener"
                >
                  PA任务执行查询 ↗
                </a>
              )}
            {flags.smallPa && ports.contextUrl(taskId) && (
              <a
                className="task-pa-context-link task-pa-context-link--smallpa"
                href={ports.contextUrl(taskId)}
                target="_blank"
                rel="noopener"
              >
                SmallPA ↗
              </a>
            )}
            {task._checked === true && (
              <span
                className="sidebar-checked"
                title="来源已检查（非本轮审核）"
              >
                ✔
              </span>
            )}
            <FieldHistory
              task={task}
              field="instruction"
              disabled={disabled}
              onRestore={(value) => onField("instruction", value)}
            />
          </div>
        </div>
        <div className="field-content">
          <div
            className={`instruction-input-wrapper${skill ? " instruction-input-wrapper--guided" : ""}`}
          >
            <GrowingTextarea
              id="instruction-global"
              aria-label="任务指令"
              readOnly={disabled}
              aria-readonly={disabled}
              placeholder="输入任务指令"
              value={instruction(task)}
              onChange={(event) => onField("instruction", event.target.value)}
            />
            {skill && (
              <details className="pa-skill-guidance">
                <summary className="pa-skill-guidance-toggle">
                  <span className="pa-skill-guidance-title">SKILL</span>
                </summary>
                <div className="pa-skill-guidance-content">{skill}</div>
              </details>
            )}
          </div>
          {raw && (
            <div
              className="evaluation-machine-pred task-raw-instruction-label--collapsed"
              title={raw}
            >
              用户指令：{raw}
            </div>
          )}
          {app && (
            <div
              className="evaluation-machine-pred"
              title="上游 PA 传入的建议应用"
            >
              建议应用：{app}
            </div>
          )}
          <Lineage task={task} ports={ports} />
          {preferences.operations && (
            <section className="sidebar-operations">
              <div className="field-header">
                <b>参考操作序列</b>
                <div className="field-actions">
                  <FieldHistory
                    task={task}
                    field="operation_suggestion"
                    disabled={disabled}
                    onRestore={(value) => {
                      onField("operation_suggestion", value);
                      setEditOperations(true);
                    }}
                  />
                  <EditButton
                    editing={editOperations}
                    label="参考操作序列"
                    disabled={disabled}
                    onClick={() => setEditOperations((value) => !value)}
                  />
                </div>
              </div>
              {editOperations ? (
                <GrowingTextarea
                  aria-label="参考操作序列"
                  disabled={disabled}
                  value={text(task.operation_suggestion)}
                  onChange={(event) =>
                    onField("operation_suggestion", event.target.value)
                  }
                  placeholder="输入参考操作序列，用分号分隔"
                />
              ) : (
                <div className="sidebar-operation-value">
                  {text(task.operation_suggestion) ||
                    "[No operation_suggestion]"}
                </div>
              )}
            </section>
          )}
          <ClientReport task={task} />
        </div>
      </section>
      {preferences.showEvaluation !== false && (
      <section className="evaluation-orm-section evaluation-orm-review">
        <div className="field-header evaluation-orm-header">
          <div className="field-title evaluation-orm-title">
            <b>评估</b>
          </div>
        </div>
        {evaluation}
      </section>
      )}

      {preferences.audit && (
        <Audit
          task={task}
          options={preferences.auditOptions}
          disabled={disabled}
          onChange={onAudit}
        />
      )}
      <Scores task={task} />
      {preferences.qa && (
        <section className="qa-review-section">
          <div className="field-header">
            <b>质检复核</b>
            <div className="field-actions">
              {["unreviewed", "reviewed"].map((status) => (
                <button
                  type="button"
                  key={status}
                  className={`small-btn${(qa.status === "reviewed" ? "reviewed" : "unreviewed") === status ? " active" : ""}`}
                  disabled={disabled}
                  aria-pressed={
                    (qa.status === "reviewed" ? "reviewed" : "unreviewed") ===
                    status
                  }
                  onClick={() => onField("qa_review", { ...qa, status })}
                >
                  {status === "reviewed" ? "已复核" : "未复核"}
                </button>
              ))}
            </div>
          </div>
          <GrowingTextarea
            aria-label="质检备注"
            disabled={disabled}
            placeholder="填写质检备注"
            value={text(qa.comment)}
            onChange={(event) =>
              onField("qa_review", { ...qa, comment: event.target.value })
            }
          />
          {qa.reviewer != null && (
            <div className="evaluation-machine-pred">
              {text(qa.reviewer)} · {createdAt(qa.reviewed_at)}
            </div>
          )}
        </section>
      )}
      <Feedback task={task} />
    </div>
  );
}
