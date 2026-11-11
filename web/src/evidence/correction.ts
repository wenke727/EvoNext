export type Region = {
  role: "original_target" | "suggested_target";
  space: "normalized_1000";
  xyxy: number[];
  media_locator: string;
  media_sha256: string;
  image_width: number;
  image_height: number;
  orientation_profile: "upright_v1";
};
export type CorrectionItem = {
  item_id: string;
  position: number;
  source_step_id: string | null;
  source_action_stage: "unknown" | "model_proposal" | "resolved_action" | "runtime_dispatch";
  source_action_ref: string | null;
  kind: "region_only" | "action_correction" | "no_action";
  regions: Region[];
  suggested_action: {action: "click"; space: "normalized_1000"; point: number[]} | null;
  verdict: "accepted" | "rejected" | "unknown" | "not_reviewed";
  reason: string;
};
export type CorrectionDraft = {note: string; items: CorrectionItem[]};
export type SavedDraft = {draft_revision: number; draft_hash: string; draft: CorrectionDraft};
export type FrozenReview = {
  revision: number; actor: string; reason: string; decision: string;
  frozen_draft: CorrectionDraft | null;
};
export type UsePreview = {
  status: string; missing: string[]; blocked: string[]; candidate: unknown;
  publication_authorized: boolean; new_trial_executed: boolean;
};

// Coordinates are relative to the rendered image, excluding surrounding layout.
export function imagePoint(clientX: number, clientY: number, bounds: {
  left: number; top: number; width: number; height: number;
}): number[] {
  return [
    Math.max(0, Math.min(1000, (clientX - bounds.left) / bounds.width * 1000)),
    Math.max(0, Math.min(1000, (clientY - bounds.top) / bounds.height * 1000)),
  ];
}
export function rectangle(start: number[], end: number[]): number[] | null {
  const box = [Math.min(start[0], end[0]), Math.min(start[1], end[1]),
    Math.max(start[0], end[0]), Math.max(start[1], end[1])];
  return box[0] < box[2] && box[1] < box[3] ? box : null;
}
