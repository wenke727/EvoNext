import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { Detail, EvidenceClient, Step } from "./client";
import { actionLabel, projectStep } from "./projection";
import { actionMarkers, sourceBbox } from "./markers";
import { EvidenceOverlay } from "./EvidenceOverlay";
import type { CoordinateSpace } from "./projection";

export function EvidenceImage({
  client,
  detail,
  step,
  position,
  thumbnail = false,
  markers = true,
  bbox = false,
  space = "unknown",
  closeup = false,
}: {
  client: EvidenceClient;
  detail: Detail;
  step: Step;
  position: number;
  thumbnail?: boolean;
  markers?: boolean;
  bbox?: boolean;
  space?: CoordinateSpace;
  closeup?: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(!thumbnail);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{
    key: string;
    url?: string;
    error?: string;
  }>({ key: "" });
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [bounds, setBounds] = useState({ width: 0, height: 0 });
  const path = step.image;
  const key = JSON.stringify([detail.snapshot_id, path, attempt]);
  const missing = !path || detail.missing_media.includes(path);
  const projection = projectStep(step);
  const geometry = markers ? actionMarkers(projection.actions, space, size.width, size.height) : [];
  const box = bbox ? sourceBbox(step, space, size.width, size.height) : null;
  const sequence = markers && !thumbnail && projection.actions.some(action => action.sequence != null)
    ? projection.actions : [];


  useEffect(() => {
    if (!host.current) return;
    const observer = new ResizeObserver(([entry]) =>
      setBounds({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      }),
    );
    observer.observe(host.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!thumbnail || !host.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => setVisible(entry.isIntersecting),
      { rootMargin: "80px" },
    );
    observer.observe(host.current);
    return () => observer.disconnect();
  }, [thumbnail]);

  useEffect(() => {
    if (!visible || missing || !path) return;
    let live = true;
    let url = "";
    const lease = client.media.acquire(detail.snapshot_id, path);
    setState({ key });
    setSize({ width: 0, height: 0 });
    lease.promise
      .then((blob) => {
        if (live) {
          url = URL.createObjectURL(blob);
          setState({ key, url });
        }
      })
      .catch((error) => {
        if (live && error.name !== "AbortError")
          setState({ key, error: String(error.message ?? error) });
      });
    return () => {
      live = false;
      lease.release();
      if (url) URL.revokeObjectURL(url);
    };
  }, [client, detail.snapshot_id, path, missing, visible, key]);

  const current = state.key === key ? state : null;
  const scale =
    size.width && bounds.width && bounds.height
      ? Math.min(bounds.width / size.width, bounds.height / size.height)
      : 0;
  let frameStyle: CSSProperties = scale
    ? { width: size.width * scale, height: size.height * scale }
    : { width: "100%", height: "100%" };
  const anchor = geometry[0]?.geometry;
  if (closeup && anchor && bounds.width && bounds.height) {
    const cropWidth = size.width;
    const cropHeight = Math.min(size.height, cropWidth / 2);
    const cropY = Math.max(
      0,
      Math.min(size.height - cropHeight, anchor.points[1] - cropHeight / 2),
    );
    const cropScale = Math.min(
      bounds.width / cropWidth,
      bounds.height / cropHeight,
    );
    frameStyle = {
      width: size.width * cropScale,
      height: size.height * cropScale,
      position: "absolute",
      left: (bounds.width - cropWidth * cropScale) / 2,
      top: (bounds.height - cropHeight * cropScale) / 2 - cropY * cropScale,
    };
  }
  return (
    <div
      ref={host}
      className={
        closeup
          ? "media-frame media-closeup"
          : thumbnail
            ? "media-frame media-thumb"
            : "media-frame media-full"
      }
    >
      {missing ? (
        <span className="media-placeholder">
          {path ? "截图未绑定" : "未记录截图"}
          {!thumbnail && <small>不以相邻步骤图片填补缺证</small>}
        </span>
      ) : current?.error ? (
        <span className="media-placeholder" title={current.error}>
          图片读取失败
          {!thumbnail && (
            <>
              <small>{current.error}</small>
              <button onClick={() => setAttempt((a) => a + 1)}>重试截图</button>
            </>
          )}
        </span>
      ) : current?.url ? (
        <div className="source-frame" style={frameStyle}>
          <img
            src={current.url}
            alt={`Step ${position} 的来源截图`}
            onLoad={(event) =>
              setSize({
                width: event.currentTarget.naturalWidth,
                height: event.currentTarget.naturalHeight,
              })
            }
            onError={() => setState({ key, error: "图片无法解码" })}
          />
          <EvidenceOverlay width={size.width} height={size.height}
            scale={Number(frameStyle.width) / size.width} markers={geometry} bbox={box} />
        </div>
      ) : (
        <span className="media-placeholder">
          {visible ? "加载截图…" : "等待加载"}
        </span>
      )}
      {current?.url && !!sequence.length && (
        <details className="marker-sequence">
          <summary>批量提案 · {sequence.length} 项</summary>
          <ol aria-label="批量动作提案顺序">
            {sequence.map((action,index) => <li key={index} title={`${action.source} · ${actionLabel(action)}`}>
              <span>{action.sequence ?? index+1}</span> {actionLabel(action)}
            </li>)}
          </ol>
        </details>
      )}
      {current?.url && bbox && step.value?.bbox != null && size.width > 0 && !box && (
        <span className="bbox-note">BBox 未绘制：检查坐标空间或来源格式</span>
      )}
      {thumbnail && !missing && projection.actions.length > 0 && (
        <span className="action-badge">
          {projection.actions.some(action => action.sequence != null) ? `批量 · ${projection.actions.length} 项` : actionLabel(projection.actions[0])}
        </span>
      )}
    </div>
  );
}
