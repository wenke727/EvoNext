import type { EvidenceClient } from "./client";

export type Recovery = {
  snapshot_id: string;
  attempt: number;
  recovery_state: string;
  can_recover: boolean;
  calls: { repetition_id: string; status: string }[];
};

export async function reconcileEvaluation(client: Pick<EvidenceClient, "request">, operation: string, snapshot: string): Promise<Recovery> {
  const response = await client.request(`/api/v1/evaluations/${encodeURIComponent(operation)}/recovery`);
  const value: Recovery = await response.json();
  if (value.snapshot_id !== snapshot) throw new Error("评估属于另一份轨迹快照");
  return value;
}

export async function recoverEvaluation(client: Pick<EvidenceClient, "request">, operation: string, snapshot: string, recovery: Recovery) {
  if (recovery.snapshot_id !== snapshot || !recovery.can_recover) throw new Error("请先核对回执，当前状态不能恢复");
  return client.request(`/api/v1/evaluations/${encodeURIComponent(operation)}/recovery`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expected_attempt: recovery.attempt, confirmed: true }),
  });
}
