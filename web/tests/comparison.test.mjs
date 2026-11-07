import { test } from "node:test";
import assert from "node:assert/strict";
import { comparisonSources } from "../src/evidence/comparison.ts";
const detail = () => ({
  missing_media: [],
  manifest: { media: { "images/a.png": "a", "images/aux.png": "b" } },
  trajectory: {
    traj: [
      {
        image: "images/a.png",
        after_image: "images/aux.png",
        value: {
          execution_result: { after_screenshot: "/unbound/device/path.jpg" },
        },
      },
      { image: null },
      { image: "images/a.png" },
    ],
  },
});
test("comparison never skips a missing next frame or substitutes it as a receipt", () => {
  const source = detail();
  const views = comparisonSources(source, 0);
  assert.equal(views[0].path, null);
  assert.equal(views[0].bound, false);
  assert.match(views[0].label, /非执行回执/);
  assert.equal(views.find((x) => x.key === "step-after").bound, true);
});
test("unbound source paths remain provenance only, even when absent from step missing-media list", () => {
  const source = detail();
  const views = comparisonSources(source, 0);
  assert.equal(views.find((x) => x.key === "receipt-after").bound, false);
  delete source.manifest;
  assert.equal(
    comparisonSources(source, 0).find((x) => x.key === "step-after").bound,
    false,
  );
});
test("auxiliary bytes do not acquire a timing relation; source objects stay unchanged", () => {
  const source = detail();
  const before = JSON.stringify(source);
  const views = comparisonSources(source, 0);
  assert.match(
    views.find((x) => x.key === "asset:images/aux.png").label,
    /未声明时序/,
  );
  assert.equal(JSON.stringify(source), before);
  assert.equal(comparisonSources(source, 2)[0].step, null);
});
