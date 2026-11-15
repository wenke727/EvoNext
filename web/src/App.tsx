import { useEffect, useMemo, useRef, useState } from "react";
import { TaskSearch } from "./workbench/navigation/TaskSearch";
import { EvidenceClient } from "./evidence/client";
import type { Detail, Summary, SourceTask } from "./evidence/client";
import { TrajectoryViewer } from "./evidence/TrajectoryViewer";
import { WorkshopPanel } from "./skills/WorkshopPanel";

export default function App() {
  const [token, setToken] = useState("");
  const [workshopOpen, setWorkshopOpen] = useState(false);
  const client = useMemo(() => new EvidenceClient(token), [token]);
  const session = useRef(client);
  session.current = client;
  const [items, setItems] = useState<Summary[]>([]);
  const [sourceItems, setSourceItems] = useState<SourceTask[]>([]);
  const [sourceMode, setSourceMode] = useState(false);
  const [sourceCursor, setSourceCursor] = useState<string | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState(() => {
    const id =
      new URLSearchParams(location.hash.slice(1)).get("snapshot") ?? "";
    return /^[a-f0-9]{64}$/.test(id) ? id : "";
  });
  const [revision, setRevision] = useState(0);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [status, setStatus] = useState("未连接");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [legacyTask, setLegacyTask] = useState(() => new URLSearchParams(location.search).get("task") ?? "");
  const [legacyVersion, setLegacyVersion] = useState(() => new URLSearchParams(location.search).get("version") ?? "");
  const sourceRouteOpened = useRef(false);
  const listRequest = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      client.media.dispose();
      listRequest.current?.abort();
    },
    [client],
  );

  async function load(append = false) {
    listRequest.current?.abort();
    const controller = new AbortController();
    listRequest.current = controller;
    setError("");
    try {
      const health = await client.ready(controller.signal);
      if (controller.signal.aborted || session.current !== client) return;
      const legacy = health.source_mode === "legacy_mongo";
      setSourceMode(legacy);
      const page = await client.list(append ? cursor : null, controller.signal);
      if (legacy) {
        const sourcePage = await client.listSource(append ? sourceCursor : null, controller.signal);
        if (controller.signal.aborted || session.current !== client) return;
        setSourceItems(previous => append ? [...previous, ...sourcePage.items.filter(item => !previous.some(old => old.task_id === item.task_id))] : sourcePage.items);
        setSourceCursor(sourcePage.next_cursor);
      }
      if (controller.signal.aborted || session.current !== client) return;
      setStatus(legacy ? (health.demo ? "旧库只读 · 预览快照重启清空" : "旧库只读 · 按打开结果固定版本") : health.demo ? "演示模式 · 重启后数据清空" : "服务已连接");
      setItems((previous) =>
        append
          ? [
              ...previous,
              ...page.items.filter(
                (item) =>
                  !previous.some((old) => old.snapshot_id === item.snapshot_id),
              ),
            ]
          : page.items,
      );
      setCursor(page.next_cursor);
    } catch (e) {
      if (!controller.signal.aborted && session.current === client)
        setError(String(e));
    }
  }

  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    setDetail(null);
    setLoading(true);
    setError("");
    client
      .detail(selected, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setDetail(value);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(String(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [selected, client, revision]);

  async function importEvidence(operation: () => Promise<Summary>, sourceCapture = false) {
    setBusy(true);
    setError("");
    try {
      const result = await operation();
      if (session.current !== client) return;
      await load();
      if (session.current !== client) return;
      selectSnapshot(result.snapshot_id);
      if (sourceCapture) {
        setLegacyTask(result.task_id);
        setLegacyVersion(result.source_version == null ? "" : String(result.source_version));
        const route = new URL(location.href);
        route.search = new URLSearchParams({task: result.task_id, ...(result.source_version == null ? {} : {version: String(result.source_version)})}).toString();
        history.replaceState(null, "", route);
      }
    } catch (e) {
      if (session.current === client) setError(String(e));
    } finally {
      if (session.current === client) setBusy(false);
    }
  }

  function changeToken(value: string) {
    listRequest.current?.abort();
    client.media.dispose();
    setToken(value);
    setDetail(null);
    setItems([]);
    setSourceItems([]);
    setSourceCursor(null);
    setSourceMode(false);
    setCursor(null);
    setLoading(false);
    setBusy(false);
    setError("");
    setStatus("未连接");
  }

  useEffect(() => {
    void load();
  }, [client]);

  useEffect(() => {
    const restore = () => {
      const id =
        new URLSearchParams(location.hash.slice(1)).get("snapshot") ?? "";
      if (/^[a-f0-9]{64}$/.test(id)) setSelected(id);
    };
    window.addEventListener("hashchange", restore);
    return () => window.removeEventListener("hashchange", restore);
  }, []);

  function selectSnapshot(id: string) {
    history.replaceState(null, "", `${location.pathname}#snapshot=${id}`);
    setSelected(id);
  }
  async function searchTask(task = legacyTask, version = legacyVersion) {
    const identifier = task.trim();
    if (busy || !identifier) return;
    if (sourceMode) {
      setLegacyTask(identifier);
      await importEvidence(() => client.openSource(identifier, version.trim()), true);
      return;
    }
    const matches = items.filter(item => item.task_id === identifier && (!version || String(item.source_version) === version));
    if (matches.length === 1) selectSnapshot(matches[0].snapshot_id);
    else setError(matches.length ? "该 Task ID 对应多个快照，请在轨迹菜单中选择固定版本。" : "已加载快照中未找到该 ID；旧库数据源尚未配置。");
  }
  function navigateTask(direction: number) {
    if (busy) return;
    if (sourceMode) {
      const index = sourceItems.findIndex(item => item.task_id === detail?.task_id);
      const next = sourceItems[index + direction];
      if (index >= 0 && next) void searchTask(next.task_id, next.source_version == null ? "" : String(next.source_version));
    } else {
      const index = items.findIndex(item => item.snapshot_id === selected);
      if (index >= 0 && items[index + direction]) selectSnapshot(items[index + direction].snapshot_id);
    }
  }

  useEffect(() => {
    const route = new URLSearchParams(location.search);
    const task = route.get("task");
    if (sourceMode && !selected && task && !sourceRouteOpened.current) {
      sourceRouteOpened.current = true;
      void searchTask(task, route.get("version") ?? "");
    }
  }, [sourceMode, selected]);

  const current = detail && detail.snapshot_id === selected ? detail : null;
  return (
    <div className={`shell ${current ? "has-workbench" : ""}`}>
      <header className="app-header">
        <a
          className="brand"
          href="#"
          onClick={(event) => {
            event.preventDefault();
            setSelected("");
            setDetail(null);
            history.replaceState(null, "", location.pathname);
          }}
        >
          EvoNext
        </a>
        <span className="app-divider" />
        <span className="app-title">轨迹工作台</span>
        <TaskSearch task={legacyTask} version={legacyVersion} busy={busy}
          onTask={value => { setLegacyTask(value); setLegacyVersion(""); }} onVersion={setLegacyVersion} onSearch={() => void searchTask()} />
        <span className="source-mode-label">{sourceMode ? "旧库 · 只读" : "本地快照"}</span>
        <div className="header-spacer" />
        <button onClick={() => setWorkshopOpen(value => !value)}>Skill Workshop</button>
        <details className="header-menu library-menu">
          <summary>轨迹 / 导入</summary>
          <div className="menu-panel">
            <div className="menu-title">
              <strong>快照与导入</strong>
              <span>{items.length} 条已加载</span>
            </div>
        <label className="task-picker">
          <select
            aria-label="轨迹选择"
            value={selected}
            onChange={(event) => selectSnapshot(event.target.value)}
          >
            <option value="" disabled>
              选择轨迹
            </option>
            {items.map((item) => (
              <option key={item.snapshot_id} value={item.snapshot_id}>
                {item.task_id} · v{item.source_version ?? "?"} ·{" "}
                {item.snapshot_id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
            <label className="import">
              {busy ? "正在导入…" : "导入 JSON / ZIP"}
              <input
                aria-label="导入轨迹"
                type="file"
                accept=".json,.zip"
                disabled={busy}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void importEvidence(() => client.importFile(file));
                  event.target.value = "";
                }}
              />
            </label>
            <div className="list">
              {items.map((item) => (
                <button
                  key={item.snapshot_id}
                  className={
                    selected === item.snapshot_id ? "item active" : "item"
                  }
                  onClick={(event) => {
                    selectSnapshot(item.snapshot_id);
                    event.currentTarget
                      .closest("details")
                      ?.removeAttribute("open");
                  }}
                >
                  <strong>{item.task_id}</strong>
                  <span>{item.instruction}</span>
                  <small>
                    {item.step_count} 步 · v{item.source_version ?? "?"} ·{" "}
                    {item.snapshot_id.slice(0, 8)}
                  </small>
                </button>
              ))}
            </div>
            {cursor && (
              <button onClick={() => void load(true)}>加载更多轨迹</button>
            )}
            <details className="legacy-import">
              <summary>从旧平台读取</summary>
              <label>
                Task ID
                <input
                  value={legacyTask}
                  onChange={(e) => setLegacyTask(e.target.value)}
                />
              </label>
              <label>
                固定版本（0 有效）
                <input
                  type="number"
                  min="0"
                  value={legacyVersion}
                  onChange={(e) => setLegacyVersion(e.target.value)}
                />
              </label>
              <button
                disabled={busy || !legacyTask || !/^\d+$/.test(legacyVersion)}
                onClick={() =>
                  void importEvidence(() =>
                    client.importLegacy(legacyTask, legacyVersion),
                  )
                }
              >
                读取并保存快照
              </button>
              <p>固定版本读取。截图需显式绑定。</p>
            </details>
          </div>
        </details>
        <details className="header-menu connection-menu">
          <summary>连接设置</summary>
          <div className="menu-panel">
            <label>
              API Key
              <input
                type="password"
                value={token}
                onChange={(e) => changeToken(e.target.value)}
                placeholder="仅保留在当前页面"
                autoComplete="off"
              />
            </label>
            <button onClick={() => void load()}>连接</button>
            <p role="status">{status}</p>
          </div>
        </details>
      </header>
      {error && (
        <div role="alert" className="error app-error">
          {error}
          <button aria-label="关闭错误" onClick={() => setError("")}>
            ×
          </button>
        </div>
      )}
      <WorkshopPanel key={token} client={client} snapshotId={selected} visible={workshopOpen}
        onClose={() => setWorkshopOpen(false)} />
      {!workshopOpen && (current ? (
        <TrajectoryViewer
          key={`${token}:${selected}`}
          client={client}
          detail={current}
          status={status}
          taskIndex={sourceMode ? sourceItems.findIndex(item => item.task_id === current.task_id) : items.findIndex(item => item.snapshot_id === selected)}
          taskCount={sourceMode ? sourceItems.length : items.length}
          onTaskNavigate={navigateTask}
          onReload={() => setRevision((value) => value + 1)}
          onJson={() =>
            void client
              .viewJson(current.snapshot_id)
              .catch((error) => setError(String(error)))
          }
          onDownload={(kind) =>
            void client
              .download(current.snapshot_id, kind)
              .catch((e) => setError(String(e)))
          }
        />
      ) : (
        <main className="library-home">
          <section className="empty">
            <h1>{loading ? "正在读取轨迹…" : "轨迹工作台"}</h1>
            <p>
              {loading
                ? "读取固定快照和媒体绑定。"
                : sourceMode ? "直接输入 Task ID，或从旧库任务列表打开轨迹。" : "输入已加载轨迹的 Task ID，或导入 JSON / ZIP 包。"}
            </p>
            <p>{sourceMode ? "旧 Mongo / MinIO 只读接入" : "原始证据只读 · Grid / 单步浏览"}</p>
            {sourceMode && <div className="source-task-list">
              {sourceItems.map(item => <button key={item.task_id} disabled={busy} onClick={() => void searchTask(item.task_id, item.source_version == null ? "" : String(item.source_version))}>
                <span className="source-task-identity">{item.task_id}<small>v{item.source_version ?? "?"} · {item.step_count} 步</small></span>
                <span>{item.instruction || "未记录任务指令"}</span>
              </button>)}
              {sourceCursor && <button disabled={busy} onClick={() => void load(true)}>加载更多旧库任务</button>}
            </div>}
            {!loading && !sourceMode && (
              <button onClick={() => void load()}>连接并读取轨迹列表</button>
            )}
          </section>
        </main>
      ))}
    </div>
  );
}
