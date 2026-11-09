export function TaskSearch({ task, version, busy, onTask, onVersion, onSearch }: {
  task: string;
  version: string;
  busy: boolean;
  onTask: (value: string) => void;
  onVersion: (value: string) => void;
  onSearch: () => void;
}) {
  return <form className="task-id-search" role="search" aria-label="轨迹定位" onSubmit={event=>{event.preventDefault();onSearch();}}>
    <svg viewBox="0 0 20 20" width="15" height="15" aria-hidden="true"><circle cx="8" cy="8" r="5"/><path d="m12 12 5 5"/></svg>
    <input aria-label="搜索 Task ID" placeholder="输入 Task ID，回车打开" value={task} onChange={event=>onTask(event.target.value)} disabled={busy} autoComplete="off" spellCheck={false} />
    <input className="task-search-version" aria-label="搜索来源版本" placeholder="最新版本" inputMode="numeric" value={version} onChange={event=>onVersion(event.target.value)} disabled={busy} title="留空读取当前版本；填写 0 可定位版本零" />
    <button type="submit" disabled={busy || !task.trim()}>{busy ? "读取中…" : "打开"}</button>
  </form>;
}
