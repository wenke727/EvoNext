"""Explicit queue recovery guarded by the existing durable paid-call receipts."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from evonext.contracts.trajectory import ContractError
from evonext.evaluation.service import (MAX_RECOVERY_ATTEMPTS, keys,
                                       record_error, status)


class RecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_attempt: int = Field(ge=0, lt=MAX_RECOVERY_ATTEMPTS)
    confirmed: Literal[True]


def reconcile(operation_id, ledger, receipts):
    saved = status(operation_id, ledger)
    if saved is None:
        return None
    if saved["result"] is not None:
        return {**saved, "recovery_state": "completed", "can_recover": False, "calls": []}
    request_key, _ = keys(operation_id)
    request = ledger.get(request_key)["payload"]["request"]
    repetitions = ["0"] + [f"investigation-{i}" for i in range(1, request["max_investigation_calls"] + 1)]
    calls = []
    for repetition in repetitions:
        pin = ledger.get(request_key + "-input-" + repetition)
        if pin is None:
            continue
        key = pin["payload"].get("call_key")
        state = receipts.inspect(key) if key else "unverified"
        calls.append({"repetition_id": repetition, "call_key": key, "status": state or "not_sent"})
    held = any(call["status"] not in {"received", "not_sent"} for call in calls)
    state = ("receipt_reconciliation_required" if held else
             "response_received" if any(call["status"] == "received" for call in calls) else "failed_before_call")
    if saved["attempt"] >= MAX_RECOVERY_ATTEMPTS:
        state = "recovery_limit_reached"
    return {**saved, "recovery_state": state,
            "can_recover": not held and saved["attempt"] < MAX_RECOVERY_ATTEMPTS, "calls": calls}


def admit_recovery(operation_id, request, ledger, receipts):
    saved = reconcile(operation_id, ledger, receipts)
    if saved is None:
        raise ContractError("Evaluation not found")
    if saved["status"] == "completed":
        return saved, False
    request_key, _ = keys(operation_id)
    attempt = request.expected_attempt + 1
    # A lost HTTP acknowledgement reuses its immutable admission. Never issue
    # a second delivery from the duplicate request; the next explicit attempt
    # is available if dispatch itself was interrupted.
    if ledger.get(f"{request_key}-recovery-{attempt}") is not None:
        return saved, False
    if saved["attempt"] != request.expected_attempt:
        raise ContractError("Recovery state changed; reconcile before confirming again")
    if saved["attempt"] >= MAX_RECOVERY_ATTEMPTS:
        raise ContractError("Manual recovery attempt limit reached")
    if not saved["can_recover"]:
        raise ContractError("Sending, unknown or unverified receipts require external reconciliation")
    ledger.record(f"{request_key}-recovery-{attempt}", saved["snapshot_id"], "evaluation_recovery.v1", {
        "operation_id": operation_id, "attempt": attempt, "confirmed": True,
        "paid_call_identity": "unchanged", "automatic_retry": False})
    return status(operation_id, ledger), True


def enqueue(operation_id, ledger, broker_url, *, attempt=0):
    from celery import Celery
    sender = None
    try:
        sender = Celery("evonext", broker=broker_url)
        sender.send_task("evonext.evaluate", args=[operation_id, attempt],
                         queue="evonext.bulk", retry=False)
    except Exception as exc:
        record_error(operation_id, ledger, exc, attempt=attempt, stage="queue_delivery_unverified")
        raise
    finally:
        if sender is not None:
            sender.close()
