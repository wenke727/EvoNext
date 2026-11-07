import { useEffect, useState } from "react";
import { readDisplayPreferences, type DisplayPreferences } from "./display-preferences";
import type { CoordinateSpace } from "./projection";

export type Preferences = {
  sidebar: number;
  timeline: number;
  inspector: number;
  columns: number;
  collapsed: boolean;
  dock: "top" | "bottom";
  markers: boolean;
  space: CoordinateSpace;
  display: DisplayPreferences;
};
const KEY = "evonext.workbench.ui.v1";
const clamp = (n: unknown, fallback: number, min: number, max: number) =>
  typeof n === "number" && Number.isFinite(n)
    ? Math.min(max, Math.max(min, n))
    : fallback;
export function usePreferences() {
  const [preferences, setPreferences] = useState<Preferences>(() => {
    let value: Partial<Preferences> = {};
    try {
      value = JSON.parse(localStorage.getItem(KEY) ?? "{}") ?? {};
    } catch {
      /* Preferences are optional. */
    }
    return {
      display: readDisplayPreferences(value.display),
      sidebar: clamp(
        value.sidebar,
        Math.min(600, innerWidth * 0.25 + 34),
        280,
        600,
      ),
      inspector: clamp(value.inspector, 440, 320, 720),
      timeline: clamp(value.timeline, 180, 110, 400),
      columns: clamp(value.columns, 6, 3, 10),
      collapsed: innerWidth <= 520 || value.collapsed === true,
      dock: value.dock === "bottom" ? "bottom" : "top",
      markers: value.markers !== false,
      space: ["unknown", "normalized", "pixels"].includes(value.space ?? "")
        ? value.space!
        : "normalized",
    };
  });
  useEffect(() => {
    const query = matchMedia("(max-width: 520px)");
    const collapse = () => {
      if (query.matches) setPreferences((p) => ({ ...p, collapsed: true }));
    };
    query.addEventListener("change", collapse);
    return () => query.removeEventListener("change", collapse);
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(preferences));
    } catch {
      /* No persistence requirement for layout. */
    }
  }, [preferences]);
  return [preferences, setPreferences] as const;
}
