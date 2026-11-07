import { test } from "node:test";
import assert from "node:assert/strict";
import { retryEntries, windowEntries, visiblePositions, visibleCursor } from "../src/evidence/timeline.ts";
const step = (step_type, image = "synthetic.png") => ({step_type, image});

test("explicit retries include the following agent frame without rewriting source", () => {
  const steps = [step("agent"),step("retry"),step("retry"),step("agent"),step("agent")];
  const before = structuredClone(steps);
  const entries = retryEntries(steps, []);
  assert.deepEqual(entries.map(({start,end})=>[start,end]), [[0,0],[1,3],[4,4]]);
  assert.deepEqual(steps,before);
  assert.deepEqual(visiblePositions(entries,new Set()),[0,3,4]);
  assert.equal(visibleCursor(entries,[0,3,4],2),1);
  assert.deepEqual(visiblePositions(entries,new Set(["1:3"])),[0,1,2,3,4]);
});

test("missing screenshots, human steps and unbound frames cannot disappear into a stack", () => {
  const steps = [step("retry"),step("retry","missing.png"),step("retry"),step("human"),step("agent"),step("retry",null)];
  assert.ok(retryEntries(steps,["missing.png"]).every(entry=>entry.start===entry.end));
});

test("model replies and runtime retry metadata alone never group source steps", () => {
  const steps = [{...step("agent"),value:{rejected_model_outputs:["synthetic"]}}, {...step("agent"),runtime:{retry:true}},step("agent")];
  assert.equal(retryEntries(steps,[]).length,3);
});

test("groups remain bounded by source pages and window clipping retains identity", () => {
  const steps = Array.from({length:2000},()=>step("retry"));
  const entries = retryEntries(steps,[]);
  assert.ok(entries.every(entry=>entry.end-entry.start<60));
  const window = windowEntries(entries,50,71);
  assert.deepEqual(window,[{start:50,end:59,key:"0:59"},{start:60,end:70,key:"60:119"}]);
  assert.equal(window.reduce((count,entry)=>count+entry.end-entry.start+1,0),21);
});
