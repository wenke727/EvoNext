import test from "node:test";
import assert from "node:assert/strict";
import { imagePoint, rectangle } from "../src/evidence/correction.ts";

test("letterboxed image coordinates stay equivalent after responsive scaling", () => {
  assert.deepEqual(imagePoint(80, 140, {left: 30, top: 40, width: 100, height: 200}), [500, 500]);
  assert.deepEqual(imagePoint(280, 540, {left: 30, top: 40, width: 500, height: 1000}), [500, 500]);
  assert.deepEqual(imagePoint(-100, 999, {left: 30, top: 40, width: 100, height: 200}), [0, 1000]);
});
test("drawing in reverse preserves positive-area xyxy without creating click points", () => {
  assert.deepEqual(rectangle([800, 600], [100, 200]), [100, 200, 800, 600]);
  assert.equal(rectangle([100, 100], [100, 200]), null);
});
