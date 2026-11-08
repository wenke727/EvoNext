"""Synthetic protocol tests. These do not establish model judgment accuracy."""
import io
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr

from evonext.app.api import create_app
from evonext.config import Settings
from evonext.contracts.trajectory import Snapshot, encode_json
from evonext.evaluation.outcome import OutcomeRequest
from evonext.evaluation.service import OutcomeService
from evonext.evaluation.store import MemoryOutcomes, RunConflict
from evonext.evidence.service import EvidenceService
from evonext.evidence.store import MemoryAssets, MemorySnapshots


@pytest.fixture
def rig():
    settings = Settings(demo=True, model_name="synthetic", model_base_url="http://synthetic.invalid",
                        _env_file=None)
    repo, assets = MemorySnapshots(), MemoryAssets()
    output = io.BytesIO()
    Image.new("RGB", (100, 200), "white").save(output, format="PNG")
    digest = assets.put(output.getvalue())
    document = {"task_id": "900719925474099312345", "instruction": "Synthetic display page goal",
        "_version_info": {"version_number": 0},
        "eval_result": {"sentinel": "GOLD_SHOULD_NOT_ENTER"},
        "traj": [{"step_id": "source-zero", "image": "images/synthetic.png",
                  "value": {"raw_model_output": "PRIOR_VERDICT_SENTINEL"}},
                 {"step_id": "source-one", "image": None}]}
    source = Snapshot.create(encode_json(document),
        encode_json({"review": "HUMAN_GOLD_SENTINEL"}), {"images/synthetic.png": digest})
    repo.put(source)
    evidence = EvidenceService(repo, assets, settings)
    store = MemoryOutcomes()
    service = OutcomeService(evidence, store, settings)
    request = OutcomeRequest(scope="initial_instruction_only", run_id=str(uuid4()), snapshot_id=source.id,
        obligations=[{"check_id": "goal.display", "requirement": "Synthetic display visible"}],
        evidence_positions=[0])
    return settings, source, evidence, service, store, request


class SyntheticGateway:
    def __init__(self, checks=None, error=None):
        self.checks = checks if checks is not None else [{
            "check_id": "goal.display", "judgment": "pass", "reason": "Synthetic oracle fixture",
            "evidence_refs": ["step:0:image"]}]
        self.error = error
        self.calls = []

    def complete(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self.error:
            raise self.error
        return {"response": {"choices": [{"message": {"content": json.dumps({"checks": self.checks})}}],
                             "model": "synthetic-observed"},
                "call_key": "synthetic-call", "declared_model": "synthetic",
                "observed_model": "synthetic-observed", "usage": None, "trace_id": None}


def test_frozen_input_is_source_bound_without_prior_judgments(rig):
    settings, source, evidence, service, store, request = rig
    row = service.create(request)
    raw = json.dumps(row["frozen"])
    assert not any(value in raw for value in (
        "GOLD_SHOULD_NOT_ENTER", "PRIOR_VERDICT_SENTINEL", "HUMAN_GOLD_SENTINEL"))
    assert row["frozen"]["context"]["images"][0]["relation"] == "before_action"
    gateway = SyntheticGateway()
    completed = service.execute(request.run_id, gateway)
    assert completed["record"]["outcome"] == "success"
    assert completed["record"]["checks"][0]["evidence_refs"] == ["step:0:image"]
    assert completed["record"]["native_result"]["usage"] is None
    messages, identity = gateway.calls[0]
    assert messages[0]["content"][2]["image_url"]["url"].startswith("data:image/png;base64,")
    assert identity["operation_id"] == "outcome:" + request.run_id
    assert evidence.get(source.id).trajectory_json == source.trajectory_json
    service.execute(request.run_id, gateway)
    assert len(gateway.calls) == 1


@pytest.mark.parametrize("checks", [
    [],
    [{"check_id": "wrong.check", "judgment": "pass", "evidence_refs": ["step:0:image"]}],
    [{"check_id": "goal.display", "judgment": "pass", "evidence_refs": []}],
    [{"check_id": "goal.display", "judgment": "fail", "evidence_refs": ["step:1:image"]}],
    [{"check_id": "goal.display", "judgment": "not_applicable", "evidence_refs": []}],
    [{"check_id": "goal.display", "judgment": "unknown"}] * 2,
])
def test_invalid_coverage_and_undelivered_citations_are_technical_errors(rig, checks):
    _, _, _, service, _, request = rig
    service.create(request)
    result = service.execute(request.run_id, SyntheticGateway(checks))
    assert result["status"] == "failed"
    assert result["record"]["outcome"] == "not_assessed"
    assert result["record"]["checks"][0]["judgment"] == "not_assessed"
    assert result["record"]["native_result"]["response"] is not None


def test_missing_images_require_no_model_call_and_no_false_success(rig):
    _, _, _, service, _, request = rig
    request.evidence_positions = [1]
    service.create(request)
    gateway = SyntheticGateway()
    result = service.execute(request.run_id, gateway)
    assert result["record"]["outcome"] == "unknown"
    assert result["record"]["native_result"]["missing"][0]["position"] == 1
    assert gateway.calls == []


def test_timeout_retains_technical_status_and_stops_redelivery(rig):
    _, _, _, service, _, request = rig
    service.create(request)
    gateway = SyntheticGateway(error=TimeoutError())
    result = service.execute(request.run_id, gateway)
    assert result["record"]["outcome"] == "not_assessed"
    assert result["record"]["native_result"]["error"] == "TimeoutError"
    service.execute(request.run_id, gateway)
    assert len(gateway.calls) == 1


def test_request_replay_preserves_policy_and_conflicting_body_is_rejected(rig):
    _, _, _, service, _, request = rig
    first = service.create(request)
    assert service.create(request) == first
    repeat = request.model_copy(update={"run_id": str(uuid4()), "repetition_id": "1"})
    assert service.create(repeat)["input_hash"] == first["input_hash"]
    request.evidence_positions = [1]
    with pytest.raises(RunConflict):
        service.create(request)


def test_http_admission_get_and_disabled_dispatch_never_call_a_model(rig):
    settings, source, evidence, _, _, request = rig
    with TestClient(create_app(settings, evidence.repository, evidence.assets)) as client:
        result = client.post("/api/v1/outcome-runs", json=request.model_dump())
        assert result.status_code == 202
        assert result.json()["status"] == "queued"
        assert client.post(f"/api/v1/outcome-runs/{request.run_id}/dispatch").status_code == 403
        assert client.get(f"/api/v1/outcome-runs/{request.run_id}").json()["record"] is None
        assert len(client.get(f"/api/v1/snapshots/{source.id}/outcome-runs").json()["items"]) == 1
        changed = request.model_dump() | {"evidence_positions": [1]}
        assert client.post("/api/v1/outcome-runs", json=changed).status_code == 409


def test_queued_request_rejects_changed_model_route(rig):
    _, _, _, service, _, request = rig
    service.create(request)
    service.settings = SimpleNamespace(model_name="changed", model_base_url="http://synthetic.invalid")
    gateway = SyntheticGateway()
    assert service.execute(request.run_id, gateway)["record"]["outcome"] == "not_assessed"
    assert gateway.calls == []


def test_known_user_amendment_profile_is_explicitly_unassessed_without_model(rig):
    settings, source, evidence, _, store, request = rig
    doc = source.document
    doc["traj"].append({"role": "user", "user_instruction": "Change to Sound"})
    changed = Snapshot.create(encode_json(doc), source.metadata_json, source.media)
    evidence.repository.put(changed)
    request.snapshot_id = changed.id
    service = OutcomeService(evidence, store, settings)
    service.create(request)
    gateway = SyntheticGateway()
    result = service.execute(request.run_id, gateway)
    assert result["record"]["outcome"] == "not_assessed"
    assert gateway.calls == []


def test_gateway_records_raw_response_before_outcome_parsing_and_reuses_receipt(rig):
    import httpx
    from evonext.providers.gateway import ModelGateway
    from evonext.providers.receipts import MemoryCallReceipts

    settings, _, _, service, store, request = rig
    settings = settings.model_copy(update={"model_calls_enabled": True,
                                           "model_api_key": SecretStr("synthetic")})
    service.settings = settings
    service.create(request)
    bodies = []
    response = {"model": "synthetic-observed", "choices": [{"message": {"content":
        '{"checks":[{"check_id":"goal.display","judgment":"unknown","reason":"Synthetic fixture lacks terminal evidence","evidence_refs":["step:0:image"]}]}'}}]}
    receipts = MemoryCallReceipts()

    def respond(call):
        bodies.append(json.loads(call.content))
        return httpx.Response(200, json=response)

    gateway = ModelGateway(settings, transport=httpx.MockTransport(respond), receipts=receipts)
    try:
        result = service.execute(request.run_id, gateway)
        assert result["record"]["outcome"] == "unknown"
        key = result["record"]["native_result"]["call_key"]
        assert json.loads(receipts.rows[key]["response"].body) == response
        assert len(bodies) == 1
        assert "GOLD_SHOULD_NOT_ENTER" not in json.dumps(bodies)
    finally:
        gateway.close()


def test_explicit_dispatch_returns_the_same_run_and_result_through_http(rig):
    from fastapi import FastAPI
    from evonext.app.outcome_api import attach_outcome_routes

    settings, _, evidence, service, store, request = rig
    settings = settings.model_copy(update={"demo": False, "model_calls_enabled": True,
                                           "model_api_key": SecretStr("synthetic-only")})
    service.settings = settings
    gateway = SyntheticGateway()
    app = FastAPI()
    attach_outcome_routes(app, evidence=evidence, get_store=lambda: store, settings=settings,
                          auth=[], dispatch=lambda key: service.execute(key, gateway))
    with TestClient(app) as client:
        assert client.post("/api/v1/outcome-runs", json=request.model_dump()).status_code == 202
        route = f"/api/v1/outcome-runs/{request.run_id}/dispatch"
        first = client.post(route)
        assert first.status_code == 202
        assert first.json()["record"]["outcome"] == "success"
        assert client.post(route).json() == first.json()
        assert len(gateway.calls) == 1
        assert client.get(f"/api/v1/outcome-runs/{request.run_id}").json() == first.json()


@pytest.mark.parametrize(("judgment", "expected"), [("fail", "failure"), ("unknown", "unknown"),
                                                   ("not_assessed", "not_assessed")])
def test_business_outcome_keeps_judgment_axis_distinct(rig, judgment, expected):
    _, _, _, service, _, request = rig
    service.create(request)
    gateway = SyntheticGateway([{
        "check_id": "goal.display", "judgment": judgment,
        "reason": "Synthetic per-obligation result.",
        "evidence_refs": ["step:0:image"] if judgment == "fail" else [],
    }])
    result = service.execute(request.run_id, gateway)
    assert result["record"]["execution_status"] == "completed"
    assert result["record"]["outcome"] == expected
