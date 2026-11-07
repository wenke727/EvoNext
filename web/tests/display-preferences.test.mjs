import { test } from "node:test";
import assert from "node:assert/strict";
import { readDisplayPreferences, DISPLAY_OPTIONS } from "../src/evidence/display-preferences.ts";

test("old or malformed preferences retain supported defaults with time hidden", () => {
  const defaults = readDisplayPreferences(undefined);
  assert.equal(defaults.time, false);
  assert.equal(defaults.agent, true);
  for (const value of [null, false, "invalid", [], { agent: "false", time: 1 }]) {
    assert.deepEqual(readDisplayPreferences(value), defaults);
  }
});

test("only explicit known display booleans survive preference readback", () => {
  const saved = { agent: false, time: true, rawOutput: false, token: "synthetic-secret", trajectory: { task_id: "synthetic-task" } };
  const before = structuredClone(saved);
  const result = readDisplayPreferences(saved);
  assert.equal(result.agent, false);
  assert.equal(result.time, true);
  assert.equal(result.rawOutput, false);
  assert.equal(result.evaluation, true);
  assert.deepEqual(Object.keys(result), DISPLAY_OPTIONS.map(option => option.key));
  assert.deepEqual(saved, before);
});
