import { useId } from "react";
import type { ActionMarker, BboxGeometry } from "./markers";

export function EvidenceOverlay({ width, height, scale, markers, bbox }: {
  width: number;
  height: number;
  scale: number;
  markers: ActionMarker[];
  bbox: BboxGeometry | null;
}) {
  const arrowId = useId().replaceAll(":", "");
  if (!markers.length && !bbox) return null;
  const radius = Math.max(width * 0.022, 6);
  const unit = scale > 0 ? 1 / scale : 1;
  // Group sequence numbers by anchor without dropping distinct vector geometry.
  const anchors = new Map<string, { x: number; y: number; sequences: number[] }>();
  for (const marker of markers) {
    if (!marker.sequences.length) continue;
    const [x,y] = marker.geometry.points;
    const key = `${x}:${y}`;
    const anchor = anchors.get(key) ?? {x,y,sequences:[]};
    anchor.sequences.push(...marker.sequences);
    anchors.set(key,anchor);
  }
  return (
    <svg className="action-overlay" viewBox={`0 0 ${width} ${height}`} aria-label="动作提案与来源标注" role="img">
      <defs>
        <marker id={arrowId} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#ef4444" />
        </marker>
      </defs>
      {bbox && (
        <g className="bbox-overlay" aria-label="来源 BBox">
          <title>value.bbox · 来源标注框，不代表动作执行结果</title>
          <rect {...bbox} fill="#007aff18" stroke="white" strokeWidth="5" strokeDasharray="5 5" vectorEffect="non-scaling-stroke" />
          <rect {...bbox} fill="none" stroke="#007aff" strokeWidth="2" strokeDasharray="5 5" vectorEffect="non-scaling-stroke" />
        </g>
      )}
      {markers.map(({geometry:shape,source},index) => (
        <g key={index} className="proposal-marker" data-kind={shape.kind}>
          <title>{source} · 模型提案，非执行回执</title>
          {shape.kind === "motion" ? (
            <>
              <path d={`M ${shape.points[0]} ${shape.points[1]} L ${shape.points[2]} ${shape.points[3]}`}
                stroke="#ef4444" strokeWidth={radius * 0.35} markerEnd={`url(#${arrowId})`} fill="none" />
              <circle cx={shape.points[0]} cy={shape.points[1]} r={radius * 0.45} fill="#ef4444" />
            </>
          ) : (
            <g stroke="#ef4444" strokeWidth={radius * 0.23}>
              <circle cx={shape.points[0]} cy={shape.points[1]} r={radius} fill="#ef444426" />
              <path d={`M ${shape.points[0]-radius*1.6} ${shape.points[1]} h ${radius*3.2} M ${shape.points[0]} ${shape.points[1]-radius*1.6} v ${radius*3.2}`} />
            </g>
          )}
        </g>
      ))}
      {[...anchors.values()].map(({x,y,sequences},index) => {
        const label = [...new Set(sequences)].sort((a,b)=>a-b).join(",");
        const badgeWidth = Math.min(width, Math.max(18,label.length*6+10)*unit);
        const badgeHeight = Math.min(height,18*unit);
        const left = Math.max(0,Math.min(width-badgeWidth,x-badgeWidth/2));
        const top = Math.max(0,Math.min(height-badgeHeight,y-radius-badgeHeight-2*unit));
        return <g className="batch-marker-number" key={index} aria-label={`动作 ${label}`}>
          <rect x={left} y={top} width={badgeWidth} height={badgeHeight} rx={Math.min(8*unit,badgeHeight/2)} fill="#dc2626" />
          <text x={left+badgeWidth/2} y={top+badgeHeight/2} dominantBaseline="central" textAnchor="middle" fill="white" fontSize={Math.min(10*unit,badgeHeight*0.7)}>{label}</text>
        </g>;
      })}
    </svg>
  );
}
