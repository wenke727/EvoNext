"""Synthetic regression cases for complete-trajectory evaluation preparation."""
import json
import os
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient

from evonext.app.api import create_app
from evonext.config import Settings
from evonext.contracts.trajectory import Snapshot, encode_json
from evonext.evaluation.inputs import InputOptions, prepare_input
from evonext.evidence.store import MemoryAssets, MemorySnapshots


def synthetic_snapshot(count=12):
    document = {"task_id": "900719925474099312345", "instruction": "synthetic test",
                "_version_info": {"version_number": 0}, "unknown": {"preserve": None},
                "evaluation": {"prediction": "success"}, "traj": []}
    for position in range(count):
        document["traj"].append({"index": 90 + position, "step_id": "duplicate-source-id",
            "image": f"images/{position}.png", "value": {"tool_call": {"action": "tap"},
            "think": "actor opinion", "raw_model_output": "success", "evaluation": True},
            "runtime": {"dispatched_action": {"action": "wait"},
                        "execution_result": {"ok": False, "unknown": None}}})
    return Snapshot.create(encode_json(document), media={f"images/{i}.png": "a" * 64
                                                        for i in range(count)})


def test_complete_trajectory_and_original_bytes_survive_projection():
    snapshot = synthetic_snapshot()
    original = snapshot.trajectory_json
    preview = prepare_input(snapshot, InputOptions())
    assert preview["source_version"] == 0
    assert preview["model_context"]["task_id"] == "900719925474099312345"
    steps = preview["model_context"]["steps"]
    assert len(steps) == 12
    assert len({step["evidence_ref"] for step in steps}) == 12
    assert steps[0]["facts"]["runtime"]["execution_result"] == {"ok": False, "unknown": None}
    assert "think" not in steps[0]["facts"]["value"]
    assert "evaluation" not in preview["model_context"]
    assert "evaluation" in preview["trajectory_fields_outside_context"]
    assert [image["position"] for image in preview["images"] if image["selected"]] == [9, 10, 11]
    assert preview["delivered_evidence_refs"] == []
    assert snapshot.trajectory_json == original
    preview["model_context"]["steps"][0]["facts"]["runtime"].clear()
    assert snapshot.trajectory_json == original


def test_budget_never_silently_truncates_steps_and_options_are_pinned():
    snapshot = synthetic_snapshot(5)
    preview = prepare_input(snapshot, InputOptions(max_images=0, max_text_bytes=1024))
    assert preview["text_budget_exceeded"]
    assert len(preview["model_context"]["steps"]) == 5
    assert not any(image["selected"] for image in preview["images"])
    assert all(image["selection_reason"] == "image_budget" for image in preview["images"])
    with_think = prepare_input(snapshot, InputOptions(include_think=True))
    assert with_think["context_sha256"] != preview["context_sha256"]
    assert with_think["model_context"]["steps"][0]["facts"]["value"]["think"] == "actor opinion"


def test_missing_media_and_empty_trajectory_have_no_fabricated_image():
    snapshot = Snapshot.create(encode_json({"task_id": "synthetic-missing", "instruction": "x",
        "traj": [{"image": "https://invalid.example/a.png"}, {"image": None}]}))
    preview = prepare_input(snapshot, InputOptions())
    assert [image["availability"] for image in preview["images"]] == ["unbound", "missing"]
    assert not any(image["selected"] for image in preview["images"])
    empty = Snapshot.create(encode_json({"task_id": "synthetic-empty", "instruction": "x", "traj": []}))
    assert prepare_input(empty, InputOptions())["step_count"] == 0


def test_api_validates_options_and_never_mutates_source():
    repository = MemorySnapshots()
    snapshot = synthetic_snapshot()
    repository.put(snapshot)
    app = create_app(Settings(demo=True, _env_file=None), repository, MemoryAssets())
    with TestClient(app) as client:
        url = f"/api/v1/snapshots/{snapshot.id}/evaluation-input"
        assert client.post(url, json={}).json() == prepare_input(snapshot, InputOptions())
        for invalid in ({"max_images": -1}, {"include_think": "false"}, {"images": "unknown"}):
            assert client.post(url, json=invalid).status_code == 422
        assert client.post("/api/v1/snapshots/" + "0" * 64 + "/evaluation-input", json={}).status_code == 404
        assert client.get(f"/api/v1/snapshots/{snapshot.id}/trajectory").content == snapshot.trajectory_json


def test_cli_accepts_platform_trajectory(tmp_path):
    path = tmp_path / "synthetic.json"
    path.write_bytes(synthetic_snapshot(1).trajectory_json)
    result = subprocess.run([sys.executable, "-m", "evonext.app.cli", "prepare-evaluation", str(path)],
                            check=True, capture_output=True, text=True,
                            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")})
    preview = json.loads(result.stdout)
    assert preview["step_count"] == 1
    assert preview["model_called"] is False
    assert preview["images"][0]["availability"] == "unbound"


class SyntheticLedger:
    def __init__(self):
        self.rows = {}

    def record(self, key, snapshot_id, kind, payload):
        row = {"snapshot_id": snapshot_id, "kind": kind, "payload": payload}
        if key in self.rows and self.rows[key] != row:
            raise ValueError("conflicting synthetic operation")
        self.rows[key] = row

    def get(self, key):
        return self.rows.get(key)


def test_fast_judge_recovers_received_response_and_validates_refs():
    import httpx
    import pytest
    from evonext.contracts.trajectory import ContractError
    from evonext.evaluation.service import EvalRequest, submit, run
    from evonext.evidence.service import EvidenceService
    from evonext.providers.gateway import ModelGateway
    from evonext.providers.receipts import MemoryCallReceipts
    from evonext.providers.telemetry import Tracing

    snapshot = synthetic_snapshot(1)
    repository = MemorySnapshots()
    repository.put(snapshot)
    settings = Settings(demo=True, _env_file=None, model_name="synthetic-model",
        model_api_key="synthetic-key", model_base_url="https://synthetic.invalid/v1",
        model_calls_enabled=True)
    service = EvidenceService(repository, MemoryAssets(), settings)
    ledger = SyntheticLedger()
    calls = []
    judgment = {"check_id": "task_goal", "judgment": "unknown", "evidence_refs": [],
                "reason": "No independent post-action observation"}
    response = {"checks": [judgment], "findings": []}

    def transport(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(response)}}]})

    gateway = ModelGateway(settings, transport=httpx.MockTransport(transport),
                           receipts=MemoryCallReceipts(), tracing=Tracing(settings))
    try:
        submit(snapshot, EvalRequest(investigation="off", operation_id="synthetic-unknown", options=InputOptions(max_images=0)), ledger)
        result = run("synthetic-unknown", service, ledger, gateway)
        assert result["outcome"] == "unknown"
        assert run("synthetic-unknown", service, ledger, gateway) == result
        assert len(calls) == 1
        judgment.update(judgment="pass", evidence_refs=["unseen/image"])
        submit(snapshot, EvalRequest(investigation="off", operation_id="synthetic-invalid", options=InputOptions(max_images=0)), ledger)
        with pytest.raises(ContractError, match="outside"):
            run("synthetic-invalid", service, ledger, gateway)
        with pytest.raises(ContractError, match="outside"):
            run("synthetic-invalid", service, ledger, gateway)
        assert len(calls) == 2
        judgment.update(judgment="pass", evidence_refs=[snapshot.id + "/steps/0"],
                        reason="Synthetic independent state observation confirms goal")
        response["findings"] = [{"check_id": "recovered_error", "judgment": "fail",
            "evidence_refs": [snapshot.id + "/steps/0"], "reason": "Synthetic error then recovery"}]
        submit(snapshot, EvalRequest(investigation="off", operation_id="synthetic-recovered", options=InputOptions(max_images=0)), ledger)
        recovered = run("synthetic-recovered", service, ledger, gateway)
        assert recovered["outcome"] == "success"
        assert recovered["native_result"]["findings"][0]["judgment"] == "fail"
        assets = MemoryAssets()
        raw = b"\x89PNG\r\n\x1a\nsynthetic-image-bytes"
        digest = assets.put(raw)
        pictured = Snapshot.create(snapshot.trajectory_json, media={"images/0.png": digest})
        repository.put(pictured)
        judgment["evidence_refs"] = [pictured.id + "/steps/0/image"]
        response["findings"] = []
        submit(pictured, EvalRequest(investigation="off", operation_id="synthetic-picture"), ledger)
        picture_result = run("synthetic-picture", EvidenceService(repository, assets, settings), ledger, gateway)
        assert picture_result["native_result"]["media_receipts"][0]["sha256"] == digest
        sent = json.loads(calls[-1].content)["messages"][1]["content"]
        assert sent[-1]["image_url"]["url"].startswith("data:image/png;base64,")
    finally:
        gateway.close()
