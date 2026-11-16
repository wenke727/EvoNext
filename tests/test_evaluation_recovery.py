"""Synthetic paid-call and queue failures; no real provider or service access."""
import copy
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from evonext.app.api import create_app
from evonext.config import Settings
from evonext.contracts.trajectory import ContractError, Snapshot, encode_json
from evonext.evaluation.inputs import InputOptions
from evonext.evaluation.recovery import RecoveryRequest, admit_recovery, reconcile
from evonext.evaluation.service import EvalRequest, keys, record_error, run, status, submit
from evonext.evidence.service import EvidenceService
from evonext.evidence.store import MemoryAssets, MemorySnapshots
from evonext.providers.gateway import ModelGateway
from evonext.providers.receipts import MemoryCallReceipts
from test_workshop_authoring import SyntheticLedger


def setup(handler, ledger=None):
    settings = Settings(demo=True, _env_file=None, model_calls_enabled=True, model_name="synthetic",
                        model_api_key="synthetic", model_base_url="https://synthetic.invalid/v1")
    evidence = EvidenceService(MemorySnapshots(), MemoryAssets(), settings)
    snapshot = Snapshot.create(encode_json({"task_id": "synthetic-recovery", "instruction": "inspect",
        "traj": [{"value": {"tool_call": {"action": "wait"}}}]}))
    evidence.accept(snapshot)
    ledger = ledger or SyntheticLedger()
    submit(snapshot, EvalRequest(operation_id="synthetic-op", investigation="off",
                                options=InputOptions(max_images=0)), ledger)
    receipts = MemoryCallReceipts()
    gateway = ModelGateway(settings, transport=httpx.MockTransport(handler), receipts=receipts)
    return snapshot, evidence, ledger, receipts, gateway


def test_received_response_replays_after_result_store_failure_without_rebilling():
    _, result_key = keys("synthetic-op")

    class InterruptedLedger(SyntheticLedger):
        interrupt = True

        def record(self, key, *args):
            if key == result_key and self.interrupt:
                self.interrupt = False
                raise OSError("synthetic store failure after receipt/checkpoint")
            return super().record(key, *args)

    calls = []
    reply = {"checks": [{"check_id": "task_goal", "judgment": "unknown", "reason": "Synthetic missing evidence",
                         "evidence_refs": []}], "findings": []}
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(reply)}}]})
    _, evidence, ledger, receipts, gateway = setup(handler, InterruptedLedger())
    try:
        with pytest.raises(OSError):
            run("synthetic-op", evidence, ledger, gateway)
        record_error("synthetic-op", ledger, OSError())
        initial = copy.deepcopy(status("synthetic-op", ledger)["initial_result"])
        saved = reconcile("synthetic-op", ledger, receipts)
        assert saved["status"] == "needs_attention"
        assert saved["recovery_state"] == "response_received" and saved["can_recover"]
        attempt, dispatch = admit_recovery("synthetic-op", RecoveryRequest(expected_attempt=0, confirmed=True), ledger, receipts)
        assert dispatch and attempt["attempt"] == 1 and attempt["status"] == "pending"
        result = run("synthetic-op", evidence, ledger, gateway)
        assert result["outcome"] == "unknown" and len(calls) == 1
        assert status("synthetic-op", ledger)["initial_result"] == initial
        assert status("synthetic-op", ledger)["status"] == "completed"
        assert ledger.get(keys("synthetic-op")[0] + "-error") is not None
        assert not reconcile("synthetic-op", ledger, receipts)["can_recover"]
    finally:
        gateway.close()


@pytest.mark.parametrize("held_status", ["sending", "unknown", "unverified"])
def test_receipt_reconciliation_blocks_uncertain_calls(held_status):
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("synthetic", request=request)
    _, evidence, ledger, receipts, gateway = setup(handler)
    try:
        with pytest.raises(httpx.ReadTimeout):
            run("synthetic-op", evidence, ledger, gateway)
        record_error("synthetic-op", ledger, TimeoutError())
        if held_status == "unverified":
            ledger.rows[keys("synthetic-op")[0] + "-input-0"]["payload"].pop("call_key")
        else:
            next(iter(receipts.rows.values()))["status"] = held_status
        before = copy.deepcopy(receipts.rows)
        saved = reconcile("synthetic-op", ledger, receipts)
        assert not saved["can_recover"]
        assert saved["calls"][0]["status"] == held_status
        with pytest.raises(ContractError, match="reconciliation"):
            admit_recovery("synthetic-op", RecoveryRequest(expected_attempt=0, confirmed=True), ledger, receipts)
        assert len(calls) == 1 and receipts.rows == before
        assert status("synthetic-op", ledger)["attempt"] == 0
    finally:
        gateway.close()


def test_received_malformed_response_stays_received_and_is_never_rebilled():
    calls = []
    _, evidence, ledger, receipts, gateway = setup(lambda r: calls.append(r) or httpx.Response(200, text="invalid JSON"))
    try:
        for attempt in range(2):
            with pytest.raises(ContractError):
                run("synthetic-op", evidence, ledger, gateway)
            record_error("synthetic-op", ledger, ValueError(), attempt=attempt)
            assert reconcile("synthetic-op", ledger, receipts)["recovery_state"] == "response_received"
            if attempt == 0:
                admit_recovery("synthetic-op", RecoveryRequest(expected_attempt=0, confirmed=True), ledger, receipts)
        assert len(calls) == 1
        assert status("synthetic-op", ledger)["status"] == "needs_attention"
        assert ledger.get(keys("synthetic-op")[0] + "-error")
        assert ledger.get(keys("synthetic-op")[0] + "-error-1")
    finally:
        gateway.close()


def test_recovery_rejects_route_changes_before_new_admission():
    _, evidence, ledger, receipts, gateway = setup(lambda r: httpx.Response(200, text="invalid JSON"))
    try:
        with pytest.raises(ContractError):
            run("synthetic-op", evidence, ledger, gateway)
        record_error("synthetic-op", ledger, ValueError())
        admit_recovery("synthetic-op", RecoveryRequest(expected_attempt=0, confirmed=True), ledger, receipts)
        gateway.settings.model_name = "changed-route"
        with pytest.raises(ContractError, match="different result"):
            run("synthetic-op", evidence, ledger, gateway)
        assert len(receipts.rows) == 1
    finally:
        gateway.close()


def test_api_recovers_queue_failure_and_lost_ack_with_same_operation(monkeypatch):
    ledger, receipts = SyntheticLedger(), MemoryCallReceipts()
    ledger.close = lambda: None
    monkeypatch.setattr("evonext.operations.ledger.Ledger", lambda dsn: ledger)
    monkeypatch.setattr("evonext.providers.receipts.PostgresCallReceipts", lambda dsn: receipts)
    deliveries = []
    class SyntheticQueue:
        def __init__(self, *args, **kwargs): pass
        def send_task(self, name, **kwargs):
            deliveries.append((name, kwargs))
            if len(deliveries) == 1:
                raise OSError("synthetic ambiguous queue submission")
        def close(self): pass
    monkeypatch.setattr("celery.Celery", SyntheticQueue)
    settings = Settings(_env_file=None, api_key="synthetic-api-key", model_calls_enabled=True,
                        postgres_dsn="postgresql://synthetic.invalid/test")
    repo, assets = MemorySnapshots(), MemoryAssets()
    snapshot = Snapshot.create(encode_json({"task_id": "synthetic-queue", "instruction": "inspect", "traj": []}))
    repo.put(snapshot)
    app = create_app(settings, repo, assets)
    with TestClient(app, headers={"X-API-Key": "synthetic-api-key"}) as client:
        op = "synthetic-op"
        assert client.post(f"/api/v1/snapshots/{snapshot.id}/evaluations", json={"operation_id": op}).status_code == 503
        assert client.get(f"/api/v1/evaluations/{op}").json()["error"]["stage"] == "queue_delivery_unverified"
        url = f"/api/v1/evaluations/{op}/recovery"
        saved = client.get(url).json()
        assert saved["recovery_state"] == "failed_before_call" and saved["can_recover"]
        assert len(deliveries) == 1
        assert client.post(url, json={"expected_attempt": 0, "confirmed": False}).status_code == 422
        body = {"expected_attempt": 0, "confirmed": True}
        recovered = client.post(url, json=body)
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["attempt"] == 1
        assert client.get(f"/api/v1/evaluations/{op}").json()["status"] == "pending"
        assert client.post(url, json=body).status_code == 200
        assert len(deliveries) == 2
        assert deliveries[-1][1]["args"] == [op, 1]
        assert deliveries[-1][1]["retry"] is False
        assert client.get("/api/v1/evaluations/absent/recovery").status_code == 404
        assert client.post("/api/v1/evaluations/absent/recovery", json=body).status_code == 404
        # A sending receipt cannot be bypassed by a stale confirmation.
        pin = keys(op)[0] + "-input-0"
        ledger.record(pin, snapshot.id, "evaluation_model_input.v1", {"call_key": "synthetic-held"})
        receipts.begin("synthetic-held", "synthetic", {60: 5})
        assert client.get(url).json()["can_recover"] is False
        assert client.post(url, json={"expected_attempt": 1, "confirmed": True}).status_code == 409
        assert len(deliveries) == 2


def test_worker_records_new_attempt_error_without_overwriting_original(monkeypatch):
    monkeypatch.setenv("EVONEXT_API_KEY", "synthetic-worker-key")
    monkeypatch.setenv("EVONEXT_DEMO", "false")
    from evonext.app import worker
    _, evidence, ledger, receipts, gateway = setup(lambda _: pytest.fail("No paid call expected"))
    ledger.close = lambda: None
    try:
        record_error("synthetic-op", ledger, OSError())
        original_error = ledger.get(keys("synthetic-op")[0] + "-error")
        admit_recovery("synthetic-op", RecoveryRequest(expected_attempt=0, confirmed=True), ledger, receipts)
        monkeypatch.setattr(worker, "stores", lambda settings: (evidence.repository, evidence.assets))
        monkeypatch.setattr(worker, "Ledger", lambda dsn: ledger)
        monkeypatch.setattr(worker, "settings", Settings(_env_file=None, api_key="synthetic-worker-key",
                            postgres_dsn="postgresql://synthetic.invalid/test"))
        def no_model(settings):
            raise ContractError("Synthetic worker configuration failure before call")
        monkeypatch.setattr("evonext.providers.gateway.ModelGateway", no_model)
        with pytest.raises(ContractError, match="configuration"):
            worker.evaluate.run("synthetic-op", 1)
        assert ledger.get(keys("synthetic-op")[0] + "-error") == original_error
        assert status("synthetic-op", ledger)["error"] == {
            "error_type": "ContractError", "stage": "worker", "automatic_retry": False}
        assert status("synthetic-op", ledger)["attempt"] == 1
        assert not receipts.rows
    finally:
        gateway.close()
