import { test } from "node:test";
import assert from "node:assert/strict";
import { reconcileEvaluation, recoverEvaluation } from "../src/evidence/evaluation-recovery.ts";

test("receipt reconciliation is read-only; confirmed recovery preserves operation and attempt", async () => {
  const calls = [];
  const saved = { snapshot_id: "synthetic", attempt: 2, can_recover: true, calls: [], recovery_state: "response_received" };
  const client = { request: async (url, options) => {
    calls.push({ url, options });
    return { json: async () => saved };
  } };
  const recovery = await reconcileEvaluation(client, "original operation", "synthetic");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options, undefined);
  await recoverEvaluation(client, "original operation", "synthetic", recovery);
  assert.equal(calls[1].url, "/api/v1/evaluations/original%20operation/recovery");
  assert.equal(calls[1].options.method, "POST");
  assert.deepEqual(JSON.parse(calls[1].options.body), { expected_attempt: 2, confirmed: true });
});

test("held receipts and cross-snapshot reconciliation never submit recovery", async () => {
  let writes = 0;
  const client = { request: async (_, options) => {
    if (options?.method === "POST") writes++;
    return { json: async () => ({ snapshot_id: "other" }) };
  } };
  await assert.rejects(reconcileEvaluation(client, "op", "synthetic"), /另一份/);
  await assert.rejects(recoverEvaluation(client, "op", "synthetic", { snapshot_id: "synthetic", can_recover: false }), /不能恢复/);
  await assert.rejects(recoverEvaluation(client, "op", "synthetic", { snapshot_id: "other", can_recover: true }), /不能恢复/);
  assert.equal(writes, 0);
});
