"""Case review contract tests. No old platform, provider, or real device calls."""
from concurrent.futures import ThreadPoolExecutor
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from evonext.app.api import create_app
from evonext.config import Settings
from evonext.contracts.trajectory import Snapshot, encode_json
from evonext.evidence.store import MemoryAssets, MemorySnapshots
from evonext.review.contracts import CaseProposal, StaleCase, verify_proposal
from evonext.review.store import MemoryCases, case_heads, case_reviews


def example():
    return Snapshot.create(encode_json({
        "task_id": "900719925474099312345", "instruction": "Synthetic GUI task",
        "_version_info": {"version_number": 0},
        "traj": [
            {"index": 42, "step_id": "source-step-A", "image": None,
             "value": {"raw_model_output": "  actual string  "}},
            {"index": 99, "step_id": "source-step-Z", "image": None,
             "value": {"execution_result": {"status": "unknown"}}},
        ],
    }))


def proposal(snapshot, *, case_id=None, **kwargs):
    data = {
        "case_id": str(case_id or uuid4()),
        "snapshot_id": snapshot.id,
        "position": 1,
        "source_step_id": "source-step-Z",
        "issue_kind": "step_action",
        "summary": "Second action has no verified after-state.",
        "evidence_refs": ["step:1"],
        "analysis_refs": [],
    }
    data.update(kwargs)
    return data


@pytest.fixture()
def case_app():
    repo, assets = MemorySnapshots(), MemoryAssets()
    snapshot = example()
    repo.put(snapshot)
    app = create_app(Settings(demo=True, _env_file=None), repo, assets)
    with TestClient(app) as client:
        yield client, repo, snapshot


def test_api_case_lifecycle_is_independent_of_raw_and_old_evaluation(case_app):
    client, repo, source = case_app
    before = source.trajectory_json
    body = proposal(source)
    first = client.post("/api/v1/cases", json=body)
    assert first.status_code == 201, first.text
    created = first.json()
    assert created["review_revision"] == 0
    assert created["review_status"] == "pending"
    assert created["source_version"] == 0
    assert created["source_step_id"] == "source-step-Z"
    assert created["history"] == []
    assert client.post("/api/v1/cases", json=body).json()["case_id"] == body["case_id"]
    url = "/api/v1/snapshots/" + source.id + "/cases"
    assert len(client.get(url).json()["items"]) == 1

    approval = {"decision": "confirmed", "reason": "Device response does not prove action effect."}
    path = f"/api/v1/cases/{body['case_id']}/review"
    decided = client.post(path, json=approval, headers={"If-Match": '"0"'})
    assert decided.status_code == 200, decided.text
    assert decided.json()["review_status"] == "operator_confirmed"
    assert decided.json()["authority"] == "configured_operator"
    assert decided.json()["history"][0]["actor"] == "demo-operator"
    assert len(decided.json()["history"]) == 1

    # Retry after a lost HTTP response is idempotent; a differing stale decision is not.
    replay = client.post(path, json=approval, headers={"If-Match": '"0"'})
    assert replay.status_code == 200
    assert len(replay.json()["history"]) == 1
    different = client.post(path, json={"decision": "rejected", "reason": "Disagree with evidence."},
                            headers={"If-Match": '"0"'})
    assert different.status_code == 412
    assert client.post(path, json=approval).status_code == 428
    assert client.post(path, json=approval, headers={"If-Match": "0"}).status_code == 400
    assert repo.get(source.id).trajectory_json == before
    assert "review" not in repo.get(source.id).document
    assert "evaluation" not in repo.get(source.id).document


@pytest.mark.parametrize("changed", [
    {"position": 2},
    {"source_step_id": "another"},
    {"evidence_refs": ["step:0"]},
    {"evidence_refs": ["media:unbound.png", "step:1"]},
    {"evidence_refs": ["step:1", "step:1"]},
    {"analysis_refs": [{"producer": "legacy-kernel", "kind": "diagnosis",
                        "record_id": "record", "snapshot_id": "f" * 64}]},
])
def test_case_cannot_bind_other_evidence(case_app, changed):
    client, _, snapshot = case_app
    result = client.post("/api/v1/cases", json=proposal(snapshot, **changed))
    assert result.status_code in {400, 422}
    assert client.get("/api/v1/snapshots/" + snapshot.id + "/cases").json()["items"] == []


def test_external_diagnosis_is_unverified_pointer_not_a_decision(case_app):
    client, _, snapshot = case_app
    body = proposal(snapshot, analysis_refs=[{
        "producer": "legacy-evaluation.kernel",
        "kind": "diagnosis",
        "record_id": "diagnosis-1",
        "snapshot_id": snapshot.id,
    }])
    result = client.post("/api/v1/cases", json=body)
    assert result.status_code == 201
    assert result.json()["review_status"] == "pending"
    assert result.json()["analysis_refs"][0]["record_id"] == "diagnosis-1"
    assert result.json()["authority"] == "none"


def test_case_idempotency_conflict_and_bounded_not_found(case_app):
    client, _, snapshot = case_app
    body = proposal(snapshot)
    assert client.post("/api/v1/cases", json=body).status_code == 201
    other = {**body, "summary": "Different problem but same client ID"}
    assert client.post("/api/v1/cases", json=other).status_code == 409
    assert client.get("/api/v1/cases/" + str(uuid4())).status_code == 404
    assert client.get("/api/v1/snapshots/" + "f" * 64 + "/cases").status_code == 404


def test_operator_identity_is_server_owned_without_human_gold():
    snapshot = example()
    repo, assets = MemorySnapshots(), MemoryAssets()
    repo.put(snapshot)
    settings = Settings(_env_file=None, api_key=SecretStr("ci-operator-key"))
    with TestClient(create_app(settings, repo, assets, MemoryCases())) as client:
        body = proposal(snapshot)
        assert client.post("/api/v1/cases", json=body).status_code == 401
        assert client.post("/api/v1/cases", headers={"X-API-Key": "ci-operator-key"},
                           json={**body, "created_by": "fake-human"}).status_code == 422
        saved = client.post("/api/v1/cases", headers={"X-API-Key": "ci-operator-key",
                                "X-Review-Actor": "fake-human"}, json=body)
        assert saved.status_code == 201, saved.text
        assert saved.json()["created_by"] == "api-key-service"
        decision = client.post(f"/api/v1/cases/{body['case_id']}/review",
            headers={"X-API-Key": "ci-operator-key", "If-Match": '"0"'},
            json={"decision": "confirmed", "reason": "Provider output looks reasonable."})
        assert decision.status_code == 403


def test_operator_can_be_configured_server_side_without_body_identity():
    snapshot = example()
    repo = MemorySnapshots()
    repo.put(snapshot)
    settings = Settings(_env_file=None, api_key=SecretStr("ci-operator-key"),
                        review_operator_id="configured-reviewer")
    with TestClient(create_app(settings, repo, MemoryAssets(), MemoryCases())) as client:
        body = proposal(snapshot)
        headers = {"X-API-Key": "ci-operator-key"}
        assert client.post("/api/v1/cases", json=body, headers=headers).json()["created_by"] == "configured-reviewer"
        decision = client.post(f"/api/v1/cases/{body['case_id']}/review",
            headers={**headers, "If-Match": '"0"', "X-Review-Actor": "admin"},
            json={"decision": "needs_evidence", "reason": "Missing observed after-state."})
        assert decision.status_code == 200
        assert decision.json()["history"][0]["actor"] == "configured-reviewer"


def test_concurrent_cas_has_one_decision_and_immutable_history():
    store = MemoryCases()
    snapshot = example()
    payload = verify_proposal(CaseProposal.model_validate_json(json.dumps(proposal(snapshot))), snapshot)
    case_id = payload["case_id"]
    assert store.create(payload, actor="author")["review_revision"] == 0

    def decide(index):
        try:
            store.decide(case_id, 0, "confirmed" if index % 2 else "rejected",
                         f"Bounded operator review decision {index}.", actor="reviewer")
            return True
        except StaleCase:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(decide, range(20))) == 1
    result = store.get(case_id)
    assert result["review_revision"] == 1
    assert len(result["history"]) == 1
    assert result["history"][0]["revision"] == 1


def test_pg_review_tables_use_one_schema_and_fixed_source_links():
    assert case_heads.schema == "evonext"
    assert case_reviews.schema == "evonext"
    assert case_heads.c.snapshot_id.type.length == 64
    assert "task_id" not in case_heads.c
    assert "outcome" not in case_heads.c
    assert "root_cause" not in case_heads.c


def test_proposal_identity_rejects_invalid_uuid_and_injected_status(case_app):
    client, _, snapshot = case_app
    assert client.post("/api/v1/cases", json=proposal(snapshot, case_id="invalid")).status_code == 422
    assert client.post("/api/v1/cases", json={**proposal(snapshot), "review_status": "approved"}).status_code == 422


def test_metadata_and_source_step_id_are_not_inferred(case_app):
    client, _, snapshot = case_app
    data = proposal(snapshot, position=0, source_step_id=None, evidence_refs=["step:0"])
    result = client.post("/api/v1/cases", json=data)
    assert result.status_code == 201
    assert result.json()["source_step_id"] is None
    assert result.json()["position"] == 0
    assert result.json()["source_version"] == 0
