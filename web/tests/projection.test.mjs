import { test } from "node:test";
import assert from "node:assert/strict";
import { projectStep, actionGeometry } from "../src/evidence/projection.ts";
import { navigationTarget } from "../src/evidence/navigation.ts";

test("raw-only evidence yields traceable fields without changing source JSON", () => {
  const step = {
    index: 0,
    value: {
      raw_model_output:
        '<think>  a\n b </think><action>tap</action><tool_call>{"name":"mobile_use","arguments":{"action":"click","coordinate":[500,1000]}}</tool_call>',
    },
    unknown: 1,
  };
  const raw = JSON.stringify(step);
  const projection = projectStep(step);
  assert.equal(projection.thought.value, "  a\n b ");
  assert.match(projection.call.source, /读取解析/);
  assert.equal(projection.actions[0].kind, "click");
  assert.equal(JSON.stringify(step), raw);
});
test("recorded execution is not promoted to a proposed or dispatched action", () => {
  const step = {
    value: {
      recorded_execution: {
        code: "tap(1, 2)",
        normalized_tool_call: {
          name: "mobile_use",
          arguments: { action: "click", coordinate: [1, 2] },
        },
      },
    },
  };
  const projection = projectStep(step);
  assert.equal(projection.call, undefined);
  assert.deepEqual(projection.actions, []);
});
test("broken or ambiguous source output stays unparsed", () => {
  const malformed = projectStep({
    value: { raw_model_output: "<tool_call>not JSON</tool_call>" },
  });
  assert.equal(malformed.call, undefined);
  assert.match(malformed.parseError, /有效 JSON/);
  const ambiguous = projectStep({
    value: { raw_model_output: "<think>a</think><think>b</think>" },
  });
  assert.equal(ambiguous.thought, undefined);
});
test("explicit tool_call wins over raw output and supports JSON-encoded arguments", () => {
  const projection = projectStep({
    value: {
      tool_call: { name: "mobile_use", arguments: '{"action":"wait"}' },
      raw_model_output: "<tool_call>invalid</tool_call>",
    },
  });
  assert.equal(projection.call.source, "value.tool_call");
  assert.equal(projection.actions[0].kind, "wait");
});
test("coordinate space is explicit; normalized markers map exactly onto the source image", () => {
  const action = {
    kind: "click",
    args: { coordinate: [500, 1000] },
    source: "test",
  };
  assert.equal(actionGeometry(action, "unknown", 640, 1472), null);
  assert.deepEqual(actionGeometry(action, "normalized", 640, 1472), {
    kind: "point",
    points: [320, 1472],
  });
  assert.equal(
    actionGeometry(
      { ...action, args: { coordinate: [1001, 1] } },
      "normalized",
      640,
      1472,
    ),
    null,
  );
  assert.equal(
    actionGeometry(
      { ...action, args: { coordinate: ["2", 1] } },
      "normalized",
      640,
      1472,
    ),
    null,
  );
});
test("drag endpoints and pixel markers retain their own coordinate meaning", () => {
  const drag = {
    kind: "drag",
    args: { start_coordinate: [100, 200], end_coordinate: [300, 400] },
    source: "test",
  };
  assert.deepEqual(actionGeometry(drag, "pixels", 640, 1472), {
    kind: "motion",
    points: [100, 200, 300, 400],
  });
});
test("non-spatial and unknown tool calls never invent a coordinate marker", () => {
  assert.equal(
    actionGeometry(
      { kind: "type", args: { text: "x", coordinate: [1, 2] }, source: "test" },
      "normalized",
      640,
      1472,
    ),
    null,
  );
  assert.equal(
    projectStep({
      value: {
        tool_call: {
          name: "unknown_tool",
          arguments: { action: "click", coordinate: [1, 2] },
        },
      },
    }).actions.length,
    0,
  );
});
test("grid cursor follows old wrap and row-boundary behavior", () => {
  assert.equal(navigationTarget("ArrowLeft", 0, 10, 3, true), 9);
  assert.equal(navigationTarget("ArrowRight", 9, 10, 3, true), 0);
  assert.equal(navigationTarget("ArrowUp", 1, 10, 3, true), 1);
  assert.equal(navigationTarget("ArrowDown", 8, 10, 3, true), 8);
  assert.equal(navigationTarget("ArrowDown", 2, 10, 3, true), 5);
  assert.equal(navigationTarget("End", 0, 2000, 6, true), 1999);
});
