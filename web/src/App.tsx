import { useEffect, useMemo, useRef, useState } from "react";
import { EvidenceClient } from "./evidence/client";
import type { Detail, Summary } from "./evidence/client";
import { TrajectoryViewer } from "./evidence/TrajectoryViewer";

export default function App() {
  const [token, setToken] = useState("");
  const client = useMemo(() => new EvidenceClient(token), [token]);
  const session = useRef(client);
  session.current = client;
  const [items, setItems] = useState<Summary[]>([]);
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
  const [legacyTask, setLegacyTask] = useState("");
  const [legacyVersion, setLegacyVersion] = useState("");
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
      const page = await client.list(append ? cursor : null, controller.signal);
      if (controller.signal.aborted || session.current !== client) return;
      setStatus(health.demo ? "演示模式 · 重启后数据清空" : "服务已连接");
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

  async function importEvidence(operation: () => Promise<Summary>) {
    setBusy(true);
    setError("");
    try {
      const result = await operation();
      if (session.current !== client) return;
      await load();
      selectSnapshot(result.snapshot_id);
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
    setCursor(null);
    setLoading(false);
    setBusy(false);
    setError("");
    setStatus("未连接");
  }

  useEffect(() => {
    if (selected) void load();
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
    history.replaceState(null, "", `#snapshot=${id}`);
    setSelected(id);
  }
  function navigateTask(direction: number) {
    const index = items.findIndex((item) => item.snapshot_id === selected);
    if (index >= 0 && items[index + direction])
      selectSnapshot(items[index + direction].snapshot_id);
  }

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
        <div className="header-spacer" />
        <details className="header-menu library-menu">
          <summary>轨迹 / 导入</summary>
          <div className="menu-panel">
            <div className="menu-title">
              <strong>轨迹资产</strong>
              <span>{items.length} 条已加载</span>
            </div>
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
      {current ? (
        <TrajectoryViewer
          key={`${token}:${selected}`}
          client={client}
          detail={current}
          status={status}
          taskIndex={items.findIndex((item) => item.snapshot_id === selected)}
          taskCount={items.length}
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
                : "连接服务后选择一条轨迹，或导入 JSON / 完整 ZIP 包。"}
            </p>
            <p>原始证据只读 · Grid / 单步浏览</p>
            {!loading && (
              <button onClick={() => void load()}>连接并读取轨迹列表</button>
            )}
          </section>
        </main>
      )}
    </div>
  );
}
