import { useMemo, useState } from "react";
import type { Detail, EvidenceClient } from "./client";
import { comparisonSources } from "./comparison";
import { EvidenceImage } from "./EvidenceImage";
export function EvidenceComparison({
  client,
  detail,
  position,
}: {
  client: EvidenceClient;
  detail: Detail;
  position: number;
}) {
  const sources = useMemo(
    () => comparisonSources(detail, position),
    [detail, position],
  );
  const [choice, setChoice] = useState("next");
  const selected =
    sources.find((source) => source.key === choice) ?? sources[0];
  return (
    <div className="comparison-frame">
      <label className="comparison-select">
        <select
          aria-label="对照图来源"
          value={selected.key}
          onChange={(event) => setChoice(event.target.value)}
        >
          {sources.map((source) => (
            <option key={source.key} value={source.key}>
              {source.label}
              {source.path && !source.bound ? "（未绑定）" : ""}
            </option>
          ))}
        </select>
      </label>
      <span className="comparison-label">{selected.label}</span>
      {selected.path && selected.bound && selected.step ? (
        <EvidenceImage
          key={selected.key}
          client={client}
          detail={detail}
          step={selected.step}
          position={selected.position}
          markers={false}
        />
      ) : (
        <div className="comparison-absent">
          {selected.path
            ? "记录引用尚未绑定媒体"
            : selected.step
              ? "下一步未记录截图"
              : "没有下一步截图"}
          <small>不跳过缺帧，不读取任意外部路径</small>
        </div>
      )}
    </div>
  );
}
