"""Durable single-trajectory Fast Judge using existing operation and model receipts."""
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from evonext.contracts.trajectory import ContractError, encode_json, sha256
from evonext.evaluation.inputs import InputOptions


class EvalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation_id: str = Field(min_length=1, max_length=100)
    options: InputOptions = Field(default_factory=InputOptions)
    investigation: Literal["off", "auto", "always"] = "auto"
    max_investigation_calls: int = Field(default=3, ge=0, le=10)
    max_total_images: int = Field(default=10, ge=0, le=100)
    focus_positions: list[int] = Field(default_factory=list, max_length=30)
    obligations: dict[str, str] = Field(default_factory=dict, max_length=30)


def keys(operation_id):
    identity = sha256(operation_id.encode())
    return "eval-request-" + identity, "eval-result-" + identity


def submit(snapshot, request, ledger):
    obligations = request.obligations or {"task_goal": snapshot.document["instruction"]}
    if any(not key.strip() or not value.strip() for key, value in obligations.items()):
        raise ContractError("Obligation IDs and descriptions must be nonempty")
    prompt = Path(__file__).with_name("outcome.md").read_text(encoding="utf-8")
    payload = {"request": request.model_dump(), "prompt": prompt,
               "policy_hash": sha256(prompt.encode()), "obligations": obligations}
    request_key, _ = keys(request.operation_id)
    ledger.record(request_key, snapshot.id, "evaluation_request.v1", payload)
    return status(request.operation_id, ledger)


def status(operation_id, ledger):
    request_key, result_key = keys(operation_id)
    row = ledger.get(request_key)
    if row is None or row["kind"] != "evaluation_request.v1":
        return None
    result = ledger.get(result_key)
    error = ledger.get(request_key + "-error")
    return {"operation_id": operation_id, "snapshot_id": row["snapshot_id"],
            "status": "completed" if result else "needs_attention" if error else "pending",
            "error": error["payload"] if error and not result else None,
            "result": result["payload"] if result else None}


def run(operation_id, evidence, ledger, gateway):
    request_key, result_key = keys(operation_id)
    saved = ledger.get(result_key)
    if saved:
        return saved["payload"]
    row = ledger.get(request_key)
    if row is None or row["kind"] != "evaluation_request.v1":
        raise ContractError("Evaluation request not found")
    payload = row["payload"]
    request = EvalRequest.model_validate(payload["request"])
    snapshot = evidence.get(row["snapshot_id"])
    if snapshot is None:
        raise ContractError("Frozen source is unavailable")
    from evonext.evaluation.core import evaluate

    def pin_input(messages, repetition):
        ledger.record(request_key + "-input-" + repetition, snapshot.id, "evaluation_model_input.v1", {
            "messages_sha256": sha256(encode_json(messages)),
            "model": gateway.settings.model_name, "endpoint": gateway.settings.model_base_url,
            "budget_scope": gateway.settings.model_budget_scope,
            "policy_hash": payload["policy_hash"], "max_tokens": 4096})

    record = evaluate(snapshot, request, evidence, gateway, payload["prompt"], result_key, pin_input)
    ledger.record(result_key, snapshot.id, "evaluation_record.v1", record)
    return record


class FindingConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    case_id: str
    summary: str = Field(min_length=8, max_length=2000)
    confirmed: Literal[True]


def finding_proposal(result, index, confirmation):
    from evonext.review.contracts import CaseProposal
    findings = result["native_result"]["findings"]
    if index < 0 or index >= len(findings):
        raise ContractError("Finding not found")
    finding = findings[index]
    position = finding.get("position")
    if position is None or finding["judgment"] != "fail":
        raise ContractError("Only a located error can become a step Case")
    return CaseProposal(case_id=confirmation.case_id, snapshot_id=result["snapshot_id"],
        position=position, issue_kind="step_action", summary=confirmation.summary,
        evidence_refs=[f"step:{position}"], analysis_refs=[{
            "kind": "diagnosis", "producer": "evonext.evaluation",
            "record_id": result["record_id"], "snapshot_id": result["snapshot_id"]}])
