"""Synthetic scripted responses exercise investigation mechanics, not judge quality."""
import copy
from pathlib import Path

import pytest

from evonext.config import Settings
from evonext.contracts.trajectory import ContractError, Snapshot, encode_json
from evonext.evaluation.core import evaluate
from evonext.evaluation.service import EvalRequest
from evonext.evidence.service import EvidenceService
from evonext.evidence.store import MemoryAssets, MemorySnapshots


class ScriptedGateway:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def complete(self, messages, **identity):
        self.calls.append((copy.deepcopy(messages), identity))
        return {"response": {"choices": [{"message": {"content": encode_json(next(self.replies)).decode()}}]},
                "trace_id": None, "call_key": str(len(self.calls)), "declared_model": "synthetic",
                "observed_model": "synthetic", "usage": None}


def setup():
    assets = MemoryAssets()
    digest = assets.put(b"\x89PNG\r\n\x1a\nsynthetic-investigator")
    snapshot = Snapshot.create(encode_json({"task_id": "synthetic-investigation", "instruction": "test",
        "traj": [{"image": f"images/{p}.png", "value": {"tool_call": {"action": "wait"}}}
                 for p in range(12)]}), media={f"images/{p}.png": digest for p in range(12)})
    repository = MemorySnapshots()
    repository.put(snapshot)
    evidence = EvidenceService(repository, assets, Settings(demo=True, _env_file=None))
    prompt = Path("src/evonext/evaluation/outcome.md").read_text()
    return snapshot, evidence, prompt


def assessment(snapshot, judgment="unknown", position=0, findings=None):
    return {"checks": [{"check_id": "task_goal", "judgment": judgment,
        "reason": "synthetic response", "evidence_refs": [] if judgment == "unknown" else
        [f"{snapshot.id}/steps/{position}/image"]}], "findings": findings or []}


def test_unknown_reads_non_tail_image_and_keeps_initial_assessment():
    snapshot, evidence, prompt = setup()
    gateway = ScriptedGateway([assessment(snapshot), {"read_evidence": [0]},
                               assessment(snapshot, "pass")])
    result = evaluate(snapshot, EvalRequest(operation_id="synthetic"), evidence, gateway, prompt, "synthetic")
    assert result["outcome"] == "success"
    native = result["native_result"]
    assert native["initial_assessment"]["checks"][0]["judgment"] == "unknown"
    assert native["stop_reason"] == "investigator_submitted"
    assert len(native["media_receipts"]) == 4
    assert native["investigation_events"][0]["status"] == "delivered"
    assert gateway.calls[-1][1]["repetition_id"] == "investigation-2"
    assert len(native["calls"]) == 3


def test_success_can_trigger_independent_process_investigation():
    snapshot, evidence, prompt = setup()
    finding = {"check_id": "recovered-error", "judgment": "fail", "reason": "synthetic error then recovery",
               "evidence_refs": [f"{snapshot.id}/steps/0/image"]}
    gateway = ScriptedGateway([assessment(snapshot, "pass", 11), {"read_evidence": [0]},
                               assessment(snapshot, "pass", 11, [finding])])
    request = EvalRequest(operation_id="synthetic", investigation="always", focus_positions=[0])
    result = evaluate(snapshot, request, evidence, gateway, prompt, "synthetic")
    assert result["outcome"] == "success"
    assert result["native_result"]["findings"][0]["check_id"] == "recovered-error"


@pytest.mark.parametrize("judgment", ["unknown", "fail"])
def test_localization_review_investigates_unsettled_process_despite_success(judgment):
    snapshot, evidence, prompt = setup()
    finding = {"check_id": "possible-initial-error", "judgment": judgment,
               "reason": "Synthetic process issue needs its original observation",
               "evidence_refs": [f"{snapshot.id}/steps/0"], "position": None}
    initial = assessment(snapshot, "pass", 11, [finding])
    final_finding = dict(finding, judgment="fail", position=0,
                         evidence_refs=[f"{snapshot.id}/steps/0/image"])
    gateway = ScriptedGateway([initial, {"read_evidence": [0]},
                               assessment(snapshot, "pass", 11, [final_finding])])
    request = EvalRequest(operation_id="synthetic", review_localization=True)
    result = evaluate(snapshot, request, evidence, gateway, prompt, "synthetic")
    assert result["outcome"] == "success"
    assert result["native_result"]["findings"][0]["position"] == 0
    assert result["native_result"]["initial_assessment"] == initial
    assert f"{snapshot.id}/steps/0/image" in result["native_result"]["delivered_evidence_refs"]
    assert len(gateway.calls) == 3


@pytest.mark.parametrize(("review", "mode", "has_issue"), [
    (False, "auto", True), (True, "off", True), (True, "auto", False),
])
def test_process_review_preserves_opt_out_and_clean_success_fast_path(review, mode, has_issue):
    snapshot, evidence, prompt = setup()
    findings = [{"check_id": "possible-error", "judgment": "unknown",
                 "reason": "Synthetic uncertainty", "evidence_refs": []}] if has_issue else []
    gateway = ScriptedGateway([assessment(snapshot, "pass", 11, findings)])
    request = EvalRequest(operation_id="synthetic", review_localization=review, investigation=mode)
    result = evaluate(snapshot, request, evidence, gateway, prompt, "synthetic")
    assert result["outcome"] == "success"
    assert result["native_result"]["stop_reason"] == "fast_judge_completed"
    assert len(gateway.calls) == 1


@pytest.mark.parametrize(("positions", "budget", "reason"), [
    ([11], 10, "investigation_no_new_evidence"),
    ([0], 3, "investigation_no_new_evidence"),
    ([0], 10, "investigation_call_budget"),
])
def test_bounded_investigation_preserves_unknown(positions, budget, reason):
    snapshot, evidence, prompt = setup()
    gateway = ScriptedGateway([assessment(snapshot), {"read_evidence": positions}])
    request = EvalRequest(operation_id="synthetic", max_total_images=budget,
                          max_investigation_calls=1 if reason.endswith("call_budget") else 3)
    result = evaluate(snapshot, request, evidence, gateway, prompt, "synthetic")
    assert result["outcome"] == "unknown"
    assert result["native_result"]["stop_reason"] == reason
    assert len(result["native_result"]["media_receipts"]) == 3


def test_cannot_cite_inventory_image_without_reading_it():
    snapshot, evidence, prompt = setup()
    gateway = ScriptedGateway([assessment(snapshot), assessment(snapshot, "pass")])
    with pytest.raises(ContractError, match="outside"):
        evaluate(snapshot, EvalRequest(operation_id="synthetic"), evidence, gateway, prompt, "synthetic")


def test_time_stop_does_not_claim_staged_image_delivered(monkeypatch):
    snapshot, evidence, prompt = setup()
    times = iter([0, 0, 181])
    monkeypatch.setattr("evonext.evaluation.investigator.time.monotonic", lambda: next(times))
    gateway = ScriptedGateway([assessment(snapshot), {"read_evidence": [0]}])
    result = evaluate(snapshot, EvalRequest(operation_id="synthetic"), evidence, gateway, prompt, "synthetic")
    assert result["native_result"]["stop_reason"] == "investigation_time_budget"
    assert f"{snapshot.id}/steps/0/image" not in result["native_result"]["delivered_evidence_refs"]


def test_known_failure_reads_earlier_steps_for_localization():
    snapshot, evidence, prompt = setup()
    failure = assessment(snapshot, "fail", 11)
    findings = [{"position": p, "judgment": "fail", "check_id": f"error-{p}",
                 "reason": "Synthetic incorrect action", "evidence_refs": [f"{snapshot.id}/steps/{p}/image"]}
                for p in (4, 5)]
    gateway = ScriptedGateway([failure, {"read_evidence": [4, 5]}, dict(failure, findings=findings)])
    request = EvalRequest(operation_id="synthetic")
    result = evaluate(snapshot, request, evidence, gateway, prompt, "synthetic")
    assert result["outcome"] == "failure"
    assert result["native_result"]["findings"] == findings
    assert result["native_result"]["error_localization"] == "located"
    gateway = ScriptedGateway([failure, {"read_evidence": [4]}])
    result = evaluate(snapshot, request.model_copy(update={"max_investigation_calls": 1}),
                      evidence, gateway, prompt, "synthetic")
    assert result["outcome"] == "failure"
    assert result["native_result"]["error_localization"] == "undetermined"


def test_source_marker_changes_only_derived_pixels():
    from io import BytesIO
    from PIL import Image
    from evonext.evaluation.images import marked_image

    buf = BytesIO()
    Image.new("RGB", (100, 100), "white").save(buf, format="PNG")
    raw = buf.getvalue()
    action = {"action": "click", "coordinate": [500, 500], "coordinate_space": "normalized_1000"}
    step = {"runtime": {"dispatched_action": action}, "value": {"bbox": [0, 0, 10, 10]}}
    view, source = marked_image(raw, step)
    assert source == "dispatched"
    assert Image.open(BytesIO(view)).getpixel((50, 46)) == (255, 0, 0)
    assert Image.open(BytesIO(raw)).getpixel((50, 46)) == (255, 255, 255)
    del action["coordinate_space"]
    assert marked_image(raw, step) == (raw, None)


def test_located_failure_stops_after_fast_judge():
    snapshot, evidence, prompt = setup()
    step = f"{snapshot.id}/steps/9"
    finding = {"position": 9, "judgment": "fail", "check_id": "wrong-action",
               "reason": "synthetic wrong action", "evidence_refs": [step]}
    gateway = ScriptedGateway([assessment(snapshot, "fail", 11, [finding])])
    result = evaluate(snapshot, EvalRequest(operation_id="early-stop"), evidence, gateway, prompt, "synthetic")
    assert result["native_result"]["stop_reason"] == "fast_judge_completed"
    assert len(gateway.calls) == 1


def test_opt_in_location_review_can_check_an_earlier_wrong_action():
    snapshot, evidence, prompt = setup()
    late = {"position": 9, "judgment": "fail", "check_id": "late-error",
            "reason": "synthetic late error", "evidence_refs": [f"{snapshot.id}/steps/9"]}
    early = {"position": 4, "judgment": "fail", "check_id": "early-error",
             "reason": "synthetic earlier error", "evidence_refs": [f"{snapshot.id}/steps/4/image"]}
    gateway = ScriptedGateway([
        assessment(snapshot, "fail", 11, [late]),
        {"read_evidence": [4]},
        assessment(snapshot, "fail", 11, [early, late]),
    ])
    request = EvalRequest(operation_id="synthetic-review", review_localization=True)
    result = evaluate(snapshot, request, evidence, gateway, prompt, "synthetic")
    assert result["native_result"]["findings"] == [early, late]
    assert len(gateway.calls) == 3
    assert result["native_result"]["initial_assessment"]["findings"] == [late]


def test_opt_in_review_can_repair_an_invalid_reference_after_explicit_feedback():
    snapshot, evidence, prompt = setup()
    invalid = assessment(snapshot, "fail", 11)
    invalid["checks"][0]["evidence_refs"] = ["wrong-snapshot/steps/11"]
    gateway = ScriptedGateway([invalid, assessment(snapshot, "fail", 11)])
    result = evaluate(snapshot, EvalRequest(operation_id="synthetic-invalid",
                                           review_localization=True),
                      evidence, gateway, prompt, "synthetic")
    assert result["native_result"]["initial_assessment"] == invalid
    assert "outside" in result["native_result"]["initial_validation_error"]
    assert result["outcome"] == "failure"
    assert len(gateway.calls) == 2


def test_failed_review_keeps_an_invalid_response_unaccepted():
    snapshot, evidence, prompt = setup()
    invalid = assessment(snapshot, "fail", 11)
    invalid["checks"][0]["evidence_refs"] = ["wrong-snapshot/steps/11"]
    gateway = ScriptedGateway([invalid, invalid])
    with pytest.raises(ContractError, match="outside"):
        evaluate(snapshot, EvalRequest(operation_id="synthetic-unrepaired",
                                       review_localization=True),
                 evidence, gateway, prompt, "synthetic")


def test_decision_binding_rejects_another_steps_delivered_action():
    from evonext.evaluation.core import validate_assessment
    snapshot, _, _ = setup()
    step = f"{snapshot.id}/steps/9"
    other = f"{snapshot.id}/steps/10/facts/value/tool_call"
    finding = {"position": 9, "judgment": "fail", "check_id": "synthetic",
               "decision_ref": other, "evidence_refs": [step, other]}
    with pytest.raises(ContractError, match="Decision reference"):
        validate_assessment({"checks": [], "findings": [finding]}, {}, {step, other}, True)


def test_bound_investigator_can_fix_unlocated_reference_without_inventing_a_position():
    snapshot, evidence, prompt = setup()
    decision = f"{snapshot.id}/steps/9/facts/value/tool_call"
    valid = {"position": 9, "judgment": "fail", "check_id": "bound",
             "decision_ref": decision, "evidence_refs": [decision]}
    unlocated = {"position": None, "judgment": "unknown", "check_id": "uncertain",
                 "decision_ref": decision, "evidence_refs": [decision]}
    fixed = dict(unlocated)
    del fixed["decision_ref"]
    gateway = ScriptedGateway([
        assessment(snapshot, "fail", 11, [valid]),
        assessment(snapshot, "fail", 11, [valid, unlocated]),
        assessment(snapshot, "fail", 11, [valid, fixed]),
    ])
    result = evaluate(snapshot, EvalRequest(operation_id="synthetic-bound-repair", bind_decisions=True,
                                           investigation="always"), evidence, gateway, prompt, "synthetic")
    assert result["native_result"]["findings"][1]["position"] is None
    assert "decision_ref" not in result["native_result"]["findings"][1]
    assert result["native_result"]["investigation_events"][0]["status"] == "assessment_validation_error"
    assert len(gateway.calls) == 3

def test_bound_decision_is_kept_with_its_source_field_and_effective_policy_hash():
    from evonext.contracts.trajectory import sha256
    snapshot, evidence, prompt = setup()
    decision = f"{snapshot.id}/steps/9/facts/value/tool_call"
    finding = {"position": 9, "judgment": "fail", "check_id": "synthetic",
               "decision_ref": decision, "evidence_refs": [decision]}
    gateway = ScriptedGateway([assessment(snapshot, "fail", 11, [finding])])
    result = evaluate(snapshot, EvalRequest(operation_id="synthetic-bound", bind_decisions=True,
                                           investigation="off"),
                      evidence, gateway, prompt, "synthetic")
    assert result["native_result"]["findings"][0]["decision_ref"] == decision
    assert decision in result["native_result"]["delivered_evidence_refs"]
    effective_prompt = gateway.calls[0][0][0]["content"]
    assert result["grader_version"] == sha256(effective_prompt.encode())
    assert result["grader_version"] != sha256(prompt.encode())


def test_fraction_marker_needs_explicit_profile_and_preserves_declared_pixel_space():
    from io import BytesIO
    from PIL import Image
    from evonext.evaluation.images import marked_image
    stream = BytesIO()
    Image.new("RGB", (100, 100), "white").save(stream, format="PNG")
    raw = stream.getvalue()
    step = {"runtime": {"dispatched_action": {"action": "click", "coordinate": [0.5, 0.5]}}}
    assert marked_image(raw, step) == (raw, None)
    view, _ = marked_image(raw, step, "evoloop_fraction_v1")
    color = Image.open(BytesIO(view)).getpixel((50, 46))
    assert color[0] > 220 and color[1] < 40 and color[2] < 40
    assert Image.open(BytesIO(raw)).getpixel((50, 46)) == (255, 255, 255)
    step["runtime"]["dispatched_action"].update(coordinate_space="pixel", coordinate=[80, 80])
    view, _ = marked_image(raw, step, "evoloop_fraction_v1")
    color = Image.open(BytesIO(view)).getpixel((80, 76))
    assert color[0] > 220 and color[1] < 40 and color[2] < 40


def test_distinct_steps_create_distinct_cases_with_machine_provenance():
    from uuid import uuid4
    from evonext.evaluation.service import finding_proposal, FindingConfirmation
    from evonext.review.contracts import verify_proposal
    from evonext.review.store import MemoryCases
    snapshot, _, _ = setup()
    result = {"snapshot_id": snapshot.id, "record_id": "synthetic-evaluation",
              "native_result": {"findings": [
                  {"position": p, "judgment": "fail", "reason": "Synthetic wrong action"}
                  for p in (4, 5)]}}
    store = MemoryCases()
    cases = []
    for index in (0, 1):
        command = FindingConfirmation(case_id=str(uuid4()), summary="Synthetic operator confirmed error", confirmed=True)
        proposal = finding_proposal(result, index, command)
        payload = verify_proposal(proposal, snapshot)
        case = store.create(payload, actor="synthetic-operator")
        assert store.create(payload, actor="synthetic-operator") == case
        cases.append(case)
    assert cases[0]["case_id"] != cases[1]["case_id"]
    assert [case["position"] for case in cases] == [4, 5]
    assert cases[0]["analysis_refs"][0]["record_id"] == result["record_id"]


def test_operator_confirmation_api_uses_saved_finding_and_replays(monkeypatch):
    from uuid import uuid4
    from fastapi.testclient import TestClient
    from evonext.app.api import create_app
    from evonext.evaluation.service import keys
    from evonext.review.store import MemoryCases

    snapshot, evidence, _ = setup()
    result = {"snapshot_id": snapshot.id, "record_id": "synthetic-eval",
              "native_result": {"findings": [
                  {"position": p, "judgment": "fail", "reason": "Synthetic wrong action"}
                  for p in (4, 5)]}}
    request_key, result_key = keys("synthetic-api")

    class SyntheticLedger:
        def __init__(self, dsn): pass
        def close(self): pass
        def get(self, key):
            if key == request_key:
                return {"kind": "evaluation_request.v1", "snapshot_id": snapshot.id}
            if key == result_key:
                return {"payload": result}

    monkeypatch.setattr("evonext.operations.ledger.Ledger", SyntheticLedger)
    repo = MemorySnapshots()
    repo.put(snapshot)
    app = create_app(Settings(_env_file=None, api_key="synthetic-api-key", postgres_dsn="postgresql://synthetic.invalid/test",
                             review_operator_id="synthetic-operator"), repo, MemoryAssets(), MemoryCases())
    with TestClient(app, headers={"X-API-Key": "synthetic-api-key"}) as client:
        cases = []
        for index in (0, 1):
            url = f"/api/v1/evaluations/synthetic-api/findings/{index}/cases"
            body = {"case_id": str(uuid4()), "summary": "Synthetic confirmed action error", "confirmed": True}
            assert client.post(url, json={**body, "confirmed": False}).status_code == 422
            response = client.post(url, json=body)
            assert response.status_code == 201, response.text
            cases.append(response.json())
            assert client.post(url, json=body).json() == cases[-1]
        assert [case["position"] for case in cases] == [4, 5]
        assert cases[0]["case_id"] != cases[1]["case_id"]
        assert cases[0]["review_status"] != "human_gold"
