"""A0-A3 tests using only immutable synthetic evidence and a demo Case owner."""
import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from evonext.app.api import create_app
from evonext.config import Settings
from evonext.contracts.trajectory import Snapshot, encode_json
from evonext.evidence.store import MemoryAssets, MemorySnapshots
from evonext.review.corrections import CorrectionDraft


def image(color):
    value = Image.new("RGB", (1080, 1920), color)
    with io.BytesIO() as out:
        value.save(out, format="PNG")
        return out.getvalue()


@pytest.fixture()
def rig():
    repo, assets = MemorySnapshots(), MemoryAssets()
    raw1, raw2 = image("white"), image("gray")
    sha1, sha2 = assets.put(raw1), assets.put(raw2)
    source = Snapshot.create(encode_json({
        "task_id": "900719925474099312345",
        "instruction": "Synthetic device navigation, no actual execution",
        "_version_info": {"version_number": 0},
        "traj": [
            {"step_id": "first", "image": None,
             "value": {"raw_model_output": "error noticed"}},
            {"step_id": "recovery-1", "image": "images/one.png",
             "value": {"raw_model_output": "attempt 1"}},
            {"step_id": "recovery-2", "image": "images/two.png",
             "value": {"tool_call": {"name": "mobile_use", "arguments": {"action": "click"}}},
             "runtime": {"dispatched_action": {"action": "click"}}},
        ],
    }), encode_json({"do_not_train": True, "source_kind": "synthetic"}),
        {"images/one.png": sha1, "images/two.png": sha2})
    repo.put(source)
    with TestClient(create_app(Settings(demo=True, _env_file=None), repo, assets)) as client:
        yield client, repo, assets, source, sha1, sha2


def new_case(source, *, position=2):
    # Position 2 is a valid later recovery Step, not necessarily the first error.
    return {
        "case_id": str(uuid4()), "snapshot_id": source.id,
        "position": position,
        "source_step_id": ("first", "recovery-1", "recovery-2")[position],
        "issue_kind": "step_action",
        "summary": "This specific recovery step needs a documented correction.",
        "evidence_refs": [f"step:{position}"],
        "analysis_refs": [],
    }


def region(pos, sha, *, role="original_target", locator=None):
    return {
        "role": role, "space": "normalized_1000",
        "xyxy": [100.5, 200.25, 400.75, 650.5],
        "media_locator": locator or f"images/{'one' if pos == 1 else 'two'}.png",
        "media_sha256": sha, "image_width": 1080, "image_height": 1920,
        "orientation_profile": "upright_v1",
    }


def item(pos, sha, *, verdict="accepted"):
    return {
        "item_id": str(uuid4()), "position": pos,
        "source_step_id": f"recovery-{pos}",
        "source_action_stage": "unknown", "source_action_ref": None,
        "kind": "region_only", "regions": [region(pos, sha)],
        "suggested_action": None, "verdict": verdict,
        "reason": "Source region is supported by the frozen frame." if verdict != "not_reviewed" else "",
    }


def saved(rig, body=None):
    client, _, _, source, _, sha2 = rig
    case = client.post("/api/v1/cases", json=new_case(source)).json()
    assert case["review_status"] == "pending"
    first, alternative = item(2, sha2), item(2, sha2)
    alternative["regions"][0]["role"] = "suggested_target"
    draft = body or {"note": "Review two alternatives on the same recovery Step",
                     "items": [first, alternative]}
    command = {"command_id": str(uuid4()), "expected_draft_revision": 0, "draft": draft}
    response = client.put(f"/api/v1/cases/{case['case_id']}/draft", json=command,
                          headers={"If-Match": '"0"'})
    assert response.status_code == 200, response.text
    return case, response.json(), command


def test_case_is_always_one_step_but_may_be_later_than_first_error(rig):
    client, _, _, source, _, _ = rig
    late = client.post("/api/v1/cases", json=new_case(source, position=2))
    assert late.status_code == 201, late.text
    assert late.json()["position"] == 2
    assert late.json()["source_step_id"] == "recovery-2"
    assert late.json()["source_version"] == 0
    earlier = client.post("/api/v1/cases", json=new_case(source, position=1))
    assert earlier.status_code == 201
    assert earlier.json()["case_id"] != late.json()["case_id"]
    assert earlier.json()["position"] == 1
    assert len(client.get("/api/v1/cases?status=pending").json()["items"]) == 2
    invalid = new_case(source, position=2)
    invalid["scope"] = "task"
    invalid["position"] = None
    assert client.post("/api/v1/cases", json=invalid).status_code == 422


def test_correction_for_other_step_requires_a_separate_case(rig):
    client, _, _, source, sha1, _ = rig
    case = client.post("/api/v1/cases", json=new_case(source, position=2)).json()
    cross_step = item(1, sha1)
    response = client.put(
        f"/api/v1/cases/{case['case_id']}/draft",
        json={"command_id": str(uuid4()), "expected_draft_revision": 0,
              "draft": {"items": [cross_step]}},
        headers={"If-Match": '"0"'},
    )
    assert response.status_code == 400
    assert "single source step" in response.json()["error"]



def test_different_later_corrections_share_case_but_have_independent_verdicts(rig):
    case, draft, _ = saved(rig)
    assert case["position"] == 2
    assert [x["position"] for x in draft["draft"]["items"]] == [2, 2]
    assert [x["verdict"] for x in draft["draft"]["items"]] == ["accepted", "accepted"]
    assert draft["draft_revision"] == 1
    assert draft["draft_hash"]


def test_shared_draft_cas_replay_and_conflict(rig):
    client, _, _, _, _, _ = rig
    case, draft, cmd = saved(rig)
    path = f"/api/v1/cases/{case['case_id']}/draft"
    assert client.put(path, json=cmd, headers={"If-Match": '"0"'}).json() == draft
    changed = {**cmd, "draft": {"note": "changed", "items": cmd["draft"]["items"]}}
    assert client.put(path, json=changed, headers={"If-Match": '"0"'}).status_code == 409
    stale = {**changed, "command_id": str(uuid4())}
    assert client.put(path, json=stale, headers={"If-Match": '"0"'}).status_code == 412
    assert client.put(path, json=stale).status_code == 428
    assert client.get(path).json() == draft
    next_cmd = {**stale, "expected_draft_revision": 1}
    newer = client.put(path, json=next_cmd, headers={"If-Match": '"1"'})
    assert newer.status_code == 200
    assert newer.json()["draft_revision"] == 2
    # An old duplicate after a newer version exists returns its exact prior receipt.
    assert client.put(path, json=cmd, headers={"If-Match": '"0"'}).json() == draft


def test_review_freezes_seen_draft_and_replay_even_after_newer_reviews(rig):
    client, repo, _, source, _, _ = rig
    raw = source.trajectory_json
    case, draft, _ = saved(rig)
    path = f"/api/v1/cases/{case['case_id']}/review"
    request = {
        "command_id": str(uuid4()), "expected_review_revision": 0,
        "draft_revision": draft["draft_revision"], "draft_hash": draft["draft_hash"],
        "decision": "confirmed", "reason": "Two separate recovery decisions were reviewed.",
    }
    response = client.post(path, json=request, headers={"If-Match": '"0"'})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["review_status"] == "operator_confirmed"
    old_review = client.get(f"/api/v1/cases/{case['case_id']}/reviews/1").json()
    assert [item["position"] for item in old_review["frozen_draft"]["items"]] == [2, 2]
    assert old_review["draft_hash"] == draft["draft_hash"]
    assert old_review["review_input_hash"]
    assert client.post(path, json=request, headers={"If-Match": '"0"'}).json() == result
    assert client.post(path, json={"decision": "confirmed", "reason": "bypass the draft"},
                       headers={"If-Match": '"1"'}).status_code == 409

    second_draft = {
        "command_id": str(uuid4()), "expected_draft_revision": 1,
        "draft": {"note": "Only second item reconsidered", "items": [draft["draft"]["items"][1]]},
    }
    draft2 = client.put(f"/api/v1/cases/{case['case_id']}/draft",
                        json=second_draft, headers={"If-Match": '"1"'}).json()
    request2 = {**request, "command_id": str(uuid4()),
        "expected_review_revision": 1, "draft_revision": 2, "draft_hash": draft2["draft_hash"],
        "reason": "Reviewed the second recovery attempt separately."}
    assert client.post(path, json=request2, headers={"If-Match": '"1"'}).status_code == 200
    assert client.post(path, json=request, headers={"If-Match": '"0"'}).json() == result
    assert client.get(f"/api/v1/cases/{case['case_id']}/reviews/1").json() == old_review
    assert repo.get(source.id).trajectory_json == raw


def test_stale_frozen_review_rejected_with_explanation(rig):
    client, _, _, _, _, _ = rig
    case, draft, _ = saved(rig)
    request = {
        "command_id": str(uuid4()), "expected_review_revision": 0,
        "draft_revision": 1, "draft_hash": draft["draft_hash"],
        "decision": "confirmed", "reason": "Reviewing a properly frozen draft.",
    }
    path = f"/api/v1/cases/{case['case_id']}/review"
    modified = {"command_id": str(uuid4()), "expected_draft_revision": 1,
                "draft": {"note": "new revision", "items": draft["draft"]["items"]}}
    assert client.put(f"/api/v1/cases/{case['case_id']}/draft",
                      json=modified, headers={"If-Match": '"1"'}).status_code == 200
    assert client.post(path, json=request, headers={"If-Match": '"0"'}).status_code == 412


def test_preview_is_readonly_and_training_remains_blocked(rig):
    client, repo, _, source, _, _ = rig
    case, draft, _ = saved(rig)
    request = {
        "command_id": str(uuid4()), "expected_review_revision": 0,
        "draft_revision": 1, "draft_hash": draft["draft_hash"],
        "decision": "confirmed", "reason": "Accepted two localized corrections.",
    }
    path = f"/api/v1/cases/{case['case_id']}/review"
    assert client.post(path, json=request, headers={"If-Match": '"0"'}).status_code == 200
    url = f"/api/v1/cases/{case['case_id']}/reviews/1/previews"
    diagnosis = client.get(url + "/diagnosis").json()
    assert diagnosis["status"] == "ready_for_preview"
    assert diagnosis["candidate"]["accepted_items"][0]["first_error_claim"] == "unknown"
    localization = client.get(url + "/localization").json()
    assert localization["candidate"]["accepted_items"]
    assert localization["publication_authorized"] is False
    assert client.get(url + "/sft").json()["status"] == "blocked"
    assert "do_not_train_source" in client.get(url + "/dpo").json()["blocked"]
    assert client.get(url + "/diagnosis").json() == diagnosis
    assert repo.get(source.id).document["traj"][0]["value"]["raw_model_output"] == "error noticed"


@pytest.mark.parametrize("bbox", [
    [-1, 20, 50, 80], [0, 20, 1001, 40], [50, 20, 10, 40], [0, 0, 0, 10],
])
def test_bbox_normalization_invalid_values_are_rejected(rig, bbox):
    client, _, _, source, _, sha2 = rig
    case = client.post("/api/v1/cases", json=new_case(source)).json()
    current = item(2, sha2)
    current["regions"][0]["xyxy"] = bbox
    command = {"command_id": str(uuid4()), "expected_draft_revision": 0,
               "draft": {"items": [current]}}
    assert client.put(f"/api/v1/cases/{case['case_id']}/draft",
                      json=command, headers={"If-Match": '"0"'}).status_code == 422


@pytest.mark.parametrize("mutation", [
    lambda i: i["regions"][0].update(media_sha256="0" * 64),
    lambda i: i["regions"][0].update(image_width=900),
    lambda i: i["regions"][0].update(media_locator="images/two.png"),
    lambda i: i.update(source_step_id="first"),
])
def test_wrong_media_or_source_binding_rejected(rig, mutation):
    client, _, _, source, _, sha2 = rig
    case = client.post("/api/v1/cases", json=new_case(source)).json()
    current = item(2, sha2)
    mutation(current)
    response = client.put(f"/api/v1/cases/{case['case_id']}/draft",
        json={"command_id": str(uuid4()), "expected_draft_revision": 0,
              "draft": {"items": [current]}}, headers={"If-Match": '"0"'})
    assert response.status_code == 400, response.text


def test_only_bbox_is_not_click_and_two_valid_actions_need_no_dpo_negative(rig):
    client, _, _, source, _, sha2 = rig
    case = client.post("/api/v1/cases", json=new_case(source)).json()
    first = item(2, sha2)
    second = item(2, sha2)
    second["regions"][0]["role"] = "suggested_target"
    draft = {"items": [first, second]}
    data = client.put(f"/api/v1/cases/{case['case_id']}/draft",
        json={"command_id": str(uuid4()), "expected_draft_revision": 0, "draft": draft},
        headers={"If-Match": '"0"'}).json()
    reviewed = client.post(f"/api/v1/cases/{case['case_id']}/review",
        json={"command_id": str(uuid4()), "expected_review_revision": 0,
              "draft_revision": 1, "draft_hash": data["draft_hash"],
              "decision": "confirmed", "reason": "Both regions are legitimate alternatives."},
        headers={"If-Match": '"0"'})
    assert reviewed.status_code == 200
    sft = client.get(f"/api/v1/cases/{case['case_id']}/reviews/1/previews/sft").json()
    assert "accepted_complete_click_action" in sft["missing"]
    assert sft["candidate"]["accepted_items"] == []


def test_click_requires_explicit_point_and_matching_source_image(rig):
    client, _, _, source, _, sha2 = rig
    case = client.post("/api/v1/cases", json=new_case(source)).json()
    current = item(2, sha2)
    current.update(kind="action_correction", suggested_action={
        "action": "click", "space": "normalized_1000", "point": [1000, 999.5]})
    good = {"command_id": str(uuid4()), "expected_draft_revision": 0,
            "draft": {"items": [current]}}
    assert client.put(f"/api/v1/cases/{case['case_id']}/draft", json=good,
                      headers={"If-Match": '"0"'}).status_code == 200
    with pytest.raises(ValueError):
        CorrectionDraft.model_validate({"items": [{
            **current, "suggested_action": {"action": "click",
                       "space": "normalized_1000", "point": [1001, 0]}
        }]})
