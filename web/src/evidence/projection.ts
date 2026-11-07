import type { Step } from "./client";

type Field = { value: unknown; source: string };
export type ActionView = {
  kind: string;
  args: Record<string, unknown>;
  source: string;
  sequence?: number;
};
export type StepProjection = {
  thought?: Field;
  semantic?: Field;
  call?: Field;
  actions: ActionView[];
  parseError?: string;
};
export type CoordinateSpace = "unknown" | "normalized" | "pixels";
export type Geometry = { kind: "point" | "motion"; points: number[] };

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function tag(raw: string, name: string) {
  const matches = [
    ...raw.matchAll(new RegExp(`<${name}>([\\s\\S]*?)</${name}>`, "g")),
  ];
  return matches.length === 1 ? matches[0][1] : undefined;
}

// A disposable reading projection. No defaults or parsed fields are written into source evidence.
export function projectStep(step: Step): StepProjection {
  const value = step.value ?? {};
  const raw =
    typeof value.raw_model_output === "string" ? value.raw_model_output : "";
  const result: StepProjection = { actions: [] };
  for (const [target, names, rawTag] of [
    ["thought", ["thought", "think"], "think"],
    ["semantic", ["action"], "action"],
  ] as const) {
    for (const name of names) {
      if (typeof value[name] === "string") {
        result[target] = { value: value[name], source: `value.${name}` };
        break;
      }
    }
    const extracted = tag(raw, rawTag);
    if (!result[target] && extracted !== undefined)
      result[target] = {
        value: extracted,
        source: `raw_model_output <${rawTag}> · 读取解析`,
      };
    const fields = value.recorded_fields;
    if (!result[target] && object(fields)) {
      for (const name of names)
        if (typeof fields[name] === "string") {
          result[target] = {
            value: fields[name],
            source: `value.recorded_fields.${name}`,
          };
          break;
        }
    }
  }
  if (value.tool_call != null)
    result.call = { value: value.tool_call, source: "value.tool_call" };
  else {
    const blocks = [...raw.matchAll(/<tool_call>([\s\S]*?)<\/tool_call>/g)];
    if (blocks.length) {
      try {
        const calls = blocks.map((block) => JSON.parse(block[1]));
        result.call = {
          value: calls.length === 1 ? calls[0] : calls,
          source: "raw_model_output <tool_call> · 读取解析",
        };
      } catch {
        result.parseError =
          "原始 tool_call 不是有效 JSON；保留原文，不猜测动作。";
      }
    }
  }
  if (!result.call) return result;
  try {
    const payload =
      typeof result.call.value === "string"
        ? JSON.parse(result.call.value)
        : result.call.value;
    const calls = Array.isArray(payload) ? payload : [payload];
    for (const [index, call] of calls.entries()) {
      if (!object(call)) continue;
      if (call.name != null && call.name !== "mobile_use") continue;
      const source = result.call.source + (calls.length > 1 ? `[${index}]` : "");
      let args: unknown = call;
      if (call.name === "mobile_use") {
        args = typeof call.arguments === "string" ? JSON.parse(call.arguments) : call.arguments;
      }
      if (!object(args) || typeof args.action !== "string") continue;
      if (args.action === "batch_actions" && Array.isArray(args.batch_actions)) {
        for (const [ordinal, child] of args.batch_actions.entries()) {
          // Children are structured proposals, never executable legacy code.
          const knownTool = object(child) && child.name === "mobile_use";
          let childArgs: unknown = knownTool ? child.arguments : child;
          if (knownTool && typeof childArgs === "string") {
            try {
              childArgs = JSON.parse(childArgs);
            } catch {
              childArgs = undefined;
            }
          }
          const childRecord = object(childArgs) ? childArgs : null;
          const kind = typeof childRecord?.action === "string" ? childRecord.action : "unknown_action";
          const valid = childRecord && (!object(child) || child.name == null || knownTool);
          result.actions.push({
            kind: valid ? kind : "unknown_action",
            args: valid ? childRecord : { raw: child },
            source: `${source}${call.name === "mobile_use" ? ".arguments" : ""}.batch_actions[${ordinal}]`,
            sequence: result.actions.length + 1,
          });
        }
      } else result.actions.push({ kind: args.action, args, source });
    }
  } catch {
    result.parseError = "结构化调用无法读取；保留原文，不绘制动作标记。";
    result.actions = [];
  }
  return result;
}

function pair(value: unknown): value is [number, number] {
  return (
    Array.isArray(value) &&
    value.length === 2 &&
    value.every((n) => typeof n === "number" && Number.isFinite(n))
  );
}

export function actionGeometry(
  action: ActionView,
  space: CoordinateSpace,
  width: number,
  height: number,
): Geometry | null {
  if (space === "unknown" || width <= 0 || height <= 0) return null;
  const limitX = space === "normalized" ? 1000 : width;
  const limitY = space === "normalized" ? 1000 : height;
  const convert = (point: unknown): number[] | null => {
    if (
      !pair(point) ||
      point[0] < 0 ||
      point[1] < 0 ||
      point[0] > limitX ||
      point[1] > limitY
    )
      return null;
    return [(point[0] / limitX) * width, (point[1] / limitY) * height];
  };
  const args = action.args;
  if (["drag", "swipe", "scroll"].includes(action.kind)) {
    const start = convert(args.start_coordinate ?? args.coordinate);
    const end = convert(args.end_coordinate ?? args.coordinate2);
    if (start && end) return { kind: "motion", points: [...start, ...end] };
  }
  if (
    ["click", "tap", "long_press", "double_click", "scroll"].includes(
      action.kind,
    )
  ) {
    const point = convert(args.coordinate);
    if (point) return { kind: "point", points: point };
  }
  return null;
}

export function actionLabel(action: ActionView) {
  const names: Record<string, string> = {
    click: "点击",
    tap: "点击",
    long_press: "长按",
    double_click: "双击",
    drag: "拖动",
    swipe: "滑动",
    scroll: "滚动",
    type: "输入",
    open: "打开应用",
    wait: "等待",
    system_button: "系统按键",
    terminate: "结束",
    take_over: "接管请求",
    unknown_action: "未知动作",
    batch_actions: "嵌套批量动作（未展开）",
  };
  const label = Object.hasOwn(names, action.kind) ? names[action.kind] : action.kind;
  const detail = action.args.text ?? action.args.button;
  return typeof detail === "string" ? `${label} · ${detail}` : label;
}
