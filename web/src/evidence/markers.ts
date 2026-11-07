import type { Step } from "./client";
import { actionGeometry, type ActionView, type CoordinateSpace, type Geometry } from "./projection.ts";

export type BboxGeometry = { x: number; y: number; width: number; height: number };
export type ActionMarker = { geometry: Geometry; sequences: number[]; source: string };

export function bboxGeometry(value: unknown, space: CoordinateSpace, width: number, height: number): BboxGeometry | null {
  if (space === "unknown" || !Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null;
  let corners: unknown[];
  if (Array.isArray(value) && value.length === 4) corners = value;
  else if (value && typeof value === "object") {
    const box = value as Record<string, unknown>;
    if (![box.x, box.y, box.width, box.height].every(n => typeof n === "number" && Number.isFinite(n))) return null;
    if ((box.width as number) <= 0 || (box.height as number) <= 0) return null;
    corners = [box.x, box.y, (box.x as number) + (box.width as number), (box.y as number) + (box.height as number)];
  } else return null;
  const limitX = space === "normalized" ? 1000 : width;
  const limitY = space === "normalized" ? 1000 : height;
  if (!corners.every((n, i) => typeof n === "number" && Number.isFinite(n) && n >= 0 && n <= (i % 2 ? limitY : limitX))) return null;
  const [x1,y1,x2,y2] = corners as number[];
  if (x1 === x2 || y1 === y2) return null;
  return { x: Math.min(x1,x2) / limitX * width, y: Math.min(y1,y2) / limitY * height,
    width: Math.abs(x2-x1) / limitX * width, height: Math.abs(y2-y1) / limitY * height };
}

// Merge identical geometry only; shared starts with distinct motion endpoints stay separate.
export function actionMarkers(actions: ActionView[], space: CoordinateSpace, width: number, height: number): ActionMarker[] {
  const grouped = new Map<string, ActionMarker>();
  for (const action of actions) {
    const geometry = actionGeometry(action, space, width, height);
    if (!geometry) continue;
    const key = JSON.stringify(geometry);
    const marker = grouped.get(key) ?? { geometry, sequences: [], source: action.source };
    if (action.sequence != null) marker.sequences.push(action.sequence);
    grouped.set(key, marker);
  }
  return [...grouped.values()];
}

export function sourceBbox(step: Step, space: CoordinateSpace, width: number, height: number) {
  return bboxGeometry(step.value?.bbox, space, width, height);
}
