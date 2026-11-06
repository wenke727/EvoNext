import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

type Summary = { snapshot_id: string; task_id: string; instruction: string; step_count: number; source_version: number | null; media_count: number };
type Step = { index?: number; source_index?: number; step_id?: string; image?: string | null; value?: Record<string, unknown>; runtime?: unknown };
type Detail = Summary & { trajectory: { traj: Step[]; [key: string]: unknown }; metadata: Record<string, unknown>; missing_media: string[] };
type Page = { items: Summary[]; next_cursor: string | null };

function App() {
  const [token, setToken] = useState('');
  const [items, setItems] = useState<Summary[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState('');
  const [detail, setDetail] = useState<Detail | null>(null);
  const [position, setPosition] = useState(0);
  const [imageUrl, setImageUrl] = useState('');
  const [status, setStatus] = useState('未连接');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [legacyTask, setLegacyTask] = useState('');
  const [legacyVersion, setLegacyVersion] = useState('');
  const step = detail?.trajectory.traj[position];

  async function request(path: string, init: RequestInit = {}) {
    const headers = new Headers(init.headers);
    headers.set('X-API-Key', token);
    const response = await fetch(path, { ...init, headers });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.error ?? body.detail ?? `HTTP ${response.status}`);
    }
    return response;
  }

  async function load(append = false) {
    setError('');
    try {
      const health = await (await request('/health/ready')).json();
      setStatus(health.demo ? '演示模式 · 重启后数据清空' : '服务就绪 · 尚未生产验收');
      const page: Page = await (await request(`/api/v1/snapshots?limit=50${append && cursor ? `&after=${cursor}` : ''}`)).json();
      setItems(previous => append ? [...previous, ...page.items] : page.items);
      setCursor(page.next_cursor);
    } catch (e) { setError(String(e)); }
  }

  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    setDetail(null); setPosition(0); setError('');
    request(`/api/v1/snapshots/${selected}`, { signal: controller.signal })
      .then(response => response.json()).then((value: Detail) => { if (!controller.signal.aborted) setDetail(value); })
      .catch(e => { if (!controller.signal.aborted) setError(String(e)); });
    return () => controller.abort();
  }, [selected, token]);

  useEffect(() => {
    setImageUrl('');
    if (!detail || !step?.image || detail.missing_media.includes(step.image)) return;
    const controller = new AbortController();
    let url = '';
    request(`/api/v1/snapshots/${detail.snapshot_id}/media?path=${encodeURIComponent(step.image)}`, { signal: controller.signal })
      .then(response => response.blob()).then(blob => {
        if (!controller.signal.aborted) { url = URL.createObjectURL(blob); setImageUrl(url); }
      }).catch(e => { if (!controller.signal.aborted) setError(String(e)); });
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [detail, position, token]);

  async function importFile(file: File) {
    setBusy(true); setError('');
    try {
      const limit = file.name.toLowerCase().endsWith('.zip') ? 64 * 1024 * 1024 : 8 * 1024 * 1024;
      if (file.size > limit) throw new Error('文件超过默认上传上限');
      let response: Response;
      if (file.name.toLowerCase().endsWith('.zip')) {
        response = await request('/api/v1/bundles', { method: 'POST', body: file, headers: { 'Content-Type': 'application/zip' } });
      } else {
        const document = JSON.parse(await file.text());
        response = await request('/api/v1/snapshots', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ trajectory: document }) });
      }
      const result: Summary = await response.json();
      await load(); setSelected(result.snapshot_id);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }

  async function download(kind: 'trajectory' | 'bundle') {
    if (!detail) return;
    try {
      const blob = await (await request(`/api/v1/snapshots/${detail.snapshot_id}/${kind}`)).blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a'); link.href = url; link.download = kind === 'bundle' ? 'opencua-bundle.zip' : 'trajectory.json';
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(String(e)); }
  }

  async function pullLegacy() {
    if (!legacyTask) return;
    setBusy(true); setError('');
    try {
      const suffix = legacyVersion !== '' ? `?version=${encodeURIComponent(legacyVersion)}` : '';
      const result: Summary = await (await request(`/api/v1/bridge/import/${encodeURIComponent(legacyTask)}${suffix}`, { method: 'POST' })).json();
      await load(); setSelected(result.snapshot_id);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }

  return <div className="shell">
    <header><div><span className="eyebrow">TRAJECTORY / EVIDENCE / EVOLUTION</span><h1>EvoNext</h1></div>
      <div className="connect"><label>API Key<input type="password" value={token} onChange={e => { setToken(e.target.value); setSelected(''); setDetail(null); setItems([]); }} placeholder="仅保存在当前页面内存" autoComplete="off"/></label><button onClick={() => void load()}>连接</button></div>
    </header>
    <div className="status">{status}<span>OpenCUA · MongoDB · MinIO · PostgreSQL · Langfuse</span></div>
    {error && <div role="alert" className="error">{error}</div>}
    <div className="layout">
      <aside><h2>轨迹资产</h2><p>导入固定快照，保留原始证据。查看不会触发模型或设备。</p>
        <label className="import">{busy ? '处理中…' : '导入 JSON / 完整 ZIP 包'}<input aria-label="导入轨迹" type="file" accept=".json,.zip" disabled={busy} onChange={e => { const f = e.target.files?.[0]; if (f) void importFile(f); e.target.value = ''; }}/></label>
        <div className="list">{items.map(item => <button key={item.snapshot_id} className={selected === item.snapshot_id ? 'item active' : 'item'} onClick={() => setSelected(item.snapshot_id)}><strong>{item.task_id}</strong><span>{item.instruction}</span><small>{item.step_count} 步 · 来源版本 {item.source_version ?? '未知'} · {item.snapshot_id.slice(0, 8)}</small></button>)}</div>
        {cursor && <button onClick={() => void load(true)}>加载更多</button>}
        <details><summary>从旧平台读取</summary><label>Task ID<input value={legacyTask} onChange={e => setLegacyTask(e.target.value)}/></label><label>固定版本（0 有效）<input type="number" min="0" value={legacyVersion} onChange={e => setLegacyVersion(e.target.value)}/></label><button disabled={busy} onClick={() => void pullLegacy()}>读取并保存快照</button><p>服务端配置旧平台；此操作不回写旧库，不自动抓取外部图片。</p></details>
      </aside>
      <main>{detail ? <>
        <section className="title"><div><span className="eyebrow">IMMUTABLE SNAPSHOT</span><h2>{detail.task_id}</h2><p>{detail.instruction}</p></div><div className="actions"><button onClick={() => void download('trajectory')}>导出 JSON</button><button onClick={() => void download('bundle')}>导出完整包</button></div></section>
        <div className="identity">快照 {detail.snapshot_id}<br/>原始数据只读；导入和存储校验不代表任务成功。</div>
        {detail.missing_media.length > 0 && <p className="warning">{detail.missing_media.length} 个媒体引用尚未绑定；不会访问任意外部 URL。</p>}
        <nav className="steps"><button disabled={position === 0} onClick={() => setPosition(0)}>首步</button><button disabled={position === 0} onClick={() => setPosition(p => p - 1)}>上一步</button><label>位置 <input type="number" min="1" max={Math.max(1, detail.step_count)} value={detail.step_count ? position + 1 : 0} onChange={e => setPosition(Math.max(0, Math.min(detail.step_count - 1, Number(e.target.value) - 1)))}/> / {detail.step_count}</label><button disabled={position >= detail.step_count - 1} onClick={() => setPosition(p => p + 1)}>下一步</button><button disabled={!detail.step_count} onClick={() => setPosition(Math.max(0, detail.step_count - 1))}>末步</button></nav>
        <div className="evidence"><div className="screen">{imageUrl ? <img src={imageUrl} alt={`步骤 ${position + 1} 的来源截图`}/> : <p>没有绑定截图<br/><small>缺图不会替换为其他步骤的图片。</small></p>}</div><div><p>包内 index：{step?.index ?? '未记录'} · 原 step_id：{step?.step_id ?? '未记录'}</p><h3>模型原始输出</h3><pre>{String(step?.value?.raw_model_output ?? '未记录；不从解析结果拼造')}</pre><h3>工具调用（提案或当前版本动作）</h3><pre>{JSON.stringify(step?.value?.tool_call ?? null, null, 2)}</pre><h3>实际执行记录 / 回执</h3><pre>{JSON.stringify({ recorded_execution: step?.value?.recorded_execution ?? null, execution_result: step?.value?.execution_result ?? null, runtime: step?.runtime ?? null }, null, 2)}</pre></div></div>
        <details><summary>来源元信息</summary><pre>{JSON.stringify(detail.metadata, null, 2)}</pre></details>
      </> : <section className="empty"><span className="eyebrow">FOUNDATION · M0/M1</span><h2>先让证据可靠，再扩展自进化闭环。</h2><p>连接服务，导入或选择一条轨迹。当前已接通导入、浏览、固定快照和导出。</p><p>Review / Case、Evaluation / Diagnosis、Recovery、Skill 和 Dataset 将按独立验收切片接入，不以空按钮冒充功能。</p></section>}</main>
    </div>
  </div>;
}

createRoot(document.getElementById('root')!).render(<App/>);
