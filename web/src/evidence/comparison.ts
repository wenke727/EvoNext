import type { Detail, Step } from "./client";
export type ComparisonSource = {
  key: string;
  label: string;
  path: string | null;
  position: number;
  bound: boolean;
  step: Step | null;
};
export function comparisonSources(
  detail: Detail,
  position: number,
): ComparisonSource[] {
  const current = detail.trajectory.traj[position];
  const next = detail.trajectory.traj[position + 1];
  const media = detail.manifest?.media;
  const bound = (path: string | null, knownStep = false) =>
    !!path &&
    (media
      ? Object.hasOwn(media, path)
      : knownStep && !detail.missing_media.includes(path));
  const sources: ComparisonSource[] = [
    {
      key: "next",
      label: "下一步截图 · 非执行回执",
      path: next?.image ?? null,
      position: position + 1,
      bound: bound(next?.image ?? null, true),
      step: next ?? null,
    },
  ];
  const receipt = current?.value?.execution_result;
  const after =
    receipt && typeof receipt === "object" && !Array.isArray(receipt)
      ? (receipt as Record<string, unknown>).after_screenshot
      : undefined;
  for (const [key, label, path] of [
    ["step-after", "步骤记录的后续图", current?.after_image],
    ["receipt-after", "回执引用的后续图", after],
  ] as const) {
    if (typeof path === "string" && path)
      sources.push({
        key,
        label,
        path,
        position,
        bound: bound(path),
        step: { image: path, value: {} },
      });
  }
  for (const path of Object.keys(media ?? {}))
    sources.push({
      key: `asset:${path}`,
      label: `包内媒体 · ${path}（未声明时序）`,
      path,
      position,
      bound: true,
      step: { image: path, value: {} },
    });
  return sources;
}
