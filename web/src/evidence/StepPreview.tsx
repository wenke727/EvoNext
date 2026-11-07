import { createPortal } from "react-dom";
import type { Detail, EvidenceClient } from "./client";
import { EvidenceImage } from "./EvidenceImage";
import { actionLabel, projectStep, type CoordinateSpace } from "./projection";
import { evidenceText } from "./display";

export function StepPreview({
  client,
  detail,
  target,
  markers,
  bbox,
  space,
}: {
  client: EvidenceClient;
  detail: Detail;
  target: { index: number; x: number; y: number };
  markers: boolean;
  bbox: boolean;
  space: CoordinateSpace;
}) {
  const step = detail.trajectory.traj[target.index];
  const projection = projectStep(step);
  return createPortal(
    <div
      role="tooltip"
      className="action-peek"
      style={{ left: target.x, top: target.y }}
    >
      <div>
        <strong>Step {target.index}</strong>
        <span>{projection.actions.map(actionLabel).join(" / ")}</span>
      </div>
      <EvidenceImage
        key={target.index}
        client={client}
        detail={detail}
        step={step}
        position={target.index}
        markers={markers} bbox={bbox}
        space={space}
        closeup
      />
      <p>{evidenceText(projection.semantic?.value)}</p>
    </div>,
    document.body,
  );
}
