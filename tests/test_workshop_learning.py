"""Synthetic standard-learning acceptance. No provider, legacy service or device calls."""
import io
import json

from PIL import Image
from fastapi.testclient import TestClient
import pytest

from evonext.app.api import create_app
from evonext.config import Settings
from evonext.contracts.trajectory import Snapshot, encode_json
from evonext.evidence.service import EvidenceService
from evonext.evidence.store import MemorySnapshots, MemoryAssets
from evonext.skills.workshop import Workshop
from evonext.skills.workshop.drafts import Drafts
from evonext.skills.workshop.learning import LearningRequest, plan, submit_learning, select_window
from evonext.skills.workshop.service import AuthorRequest, run, submit
from test_workshop_authoring import SyntheticLedger, model, DOCUMENT


@pytest.fixture
def env(tmp_path):
    settings = Settings(demo=True, _env_file=None)
    evidence = EvidenceService(MemorySnapshots(), MemoryAssets(), settings)
    library = Workshop(tmp_path / "workshop", "synthetic-owner")
    return library, evidence, SyntheticLedger(), settings


def source(env, task, label="unknown", *, meta=None, count=16, image=False, family=None):
    library, evidence, _, _ = env
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
    digest = evidence.assets.put(buf.getvalue())
    snapshot = Snapshot.create(encode_json({"task_id": task,
        "instruction": "Inspect synthetic account sorting", "evaluation": {"prediction": {"task_status": label}},
        "traj": [{"image": f"{i}.png", "value": {"text": "synthetic sorting page"}}
                 for i in range(count)]}), encode_json({"split": "dev", **(meta or {}),
            **({"family_id": family} if family else {})}),
        {f"{i}.png": digest for i in range(count)} if image else {})
    evidence.accept(snapshot)
    return snapshot


def query(**kwargs):
    return LearningRequest(operation_id="synthetic-learning", topic="account sorting",
                           skill_id="check-target", **kwargs)


def response(ref, verdict="approved"):
    return {"verdict": verdict, "notes": "Synthetic source audit", "evidence_refs": [ref]}


def proposal():
    return {"decision": "propose", "reason": "Synthetic method", "files": {"SKILL.md": DOCUMENT}}


def test_retrieval_has_eight_sources_mixed_labels_no_holdout_or_duplicate_revision(env):
    library, evidence, _, settings = env
    for i in range(8):
        source(env, f"synthetic-{i}", "perfect" if i % 2 else "failed")
    old = source(env, "synthetic-0", "failed", meta={"version_note": "another upload"})
    source(env, "synthetic-heldout", "perfect", meta={"split": "holdout"})
    source(env, "synthetic-revoked", meta={"revoked": True})
    view = plan(query(source_limit=8), library, evidence, settings)
    report = view["retrieval"]
    assert report["selected_count"] == report["independent_family_count"] == 8
    assert set(s["source_label_hint"] for s in report["sources"]) == {"success", "failure"}
    assert {s["reason"] for s in report["excluded"]} >= {"held_out_source", "source_restricted"}
    assert len({s["task_id"] for s in report["sources"]}) == 8
    assert all(s["label_authority"] == "unverified_source" for s in report["sources"])
    assert len(view["author_request"]["sources"]) == 8
    assert all(w["image_positions"] == [] for w in view["author_request"]["sources"])
    assert old.trajectory_json == evidence.get(old.id).trajectory_json


def test_related_success_failure_pair_kept_without_claiming_independence(env):
    library, evidence, _, settings = env
    source(env, "synthetic-fail", "failed", family="synthetic-family")
    source(env, "synthetic-fixed", "perfect", family="synthetic-family")
    source(env, "synthetic-fail-retry", "failed", family="synthetic-family")
    report = plan(query(), library, evidence, settings)["retrieval"]
    assert report["selected_count"] == 2 and report["independent_family_count"] == 1
    assert report["shortfall"] == 2
    assert any(row["reason"] == "same_lineage_redundant" for row in report["excluded"])


def test_window_finds_middle_action_and_keeps_before_after_without_changing_source(env):
    doc = {"task_id": "synthetic-middle", "instruction": "sorting", "traj": [
        {"value": {"raw_model_output": "<action>wait</action>"}} for _ in range(40)]}
    doc["traj"][23]["value"]["raw_model_output"] = "<action>open sorting menu</action>"
    snap = Snapshot.create(encode_json(doc))
    original = snap.trajectory_json
    positions = select_window(snap, "sorting menu").positions
    assert positions == list(range(positions[0], positions[0] + 12))
    assert 22 in positions and 23 in positions and 24 in positions and positions[0] > 0
    assert snap.trajectory_json == original


def test_existing_skill_is_frozen_for_patch_and_no_new_discovery_on_recovery(env):
    library, evidence, ledger, settings = env
    source(env, "synthetic-one")
    saved = library.save("check-target", DOCUMENT, expected_revision=None,
        source_snapshots=["a" * 64], reason="synthetic", actor="synthetic")
    req = query()
    submit_learning(req, library, evidence, ledger, settings)
    frozen = next(iter(ledger.rows.values()))["payload"]
    assert frozen["request"]["base_revision"] == saved["revision"]
    source(env, "synthetic-two")
    assert submit_learning(req, library, evidence, ledger, settings)["status"] == "pending"
    assert len(frozen["request"]["sources"]) == 1
    with pytest.raises(ValueError, match="another learning request"):
        submit_learning(req.model_copy(update={"topic": "different"}), library, evidence, ledger, settings)


def test_author_requests_image_lazily_and_review_reuses_it(env):
    library, evidence, ledger, settings = env
    snap = source(env, "synthetic-image", image=True, count=3)
    req = query()
    settings.model_name = "synthetic"
    view = plan(req, library, evidence, settings)
    submit_learning(req, library, evidence, ledger, settings)
    ref = snap.id + ":1"
    gateway, calls = model([{"read_evidence": [{"evidence_ref": ref, "reason": "Check sorting state"}]},
                            proposal(), response(ref)])
    reads = []
    original_read = evidence.read_media
    evidence.read_media = lambda *args: (reads.append(args), original_read(*args))[1]
    try:
        result = run(req.operation_id, library, evidence, ledger, gateway)
        assert result["outcome"] == "approved" and len(calls) == 3
        assert "image_url" not in json.dumps(calls[0])
        assert "image_url" in json.dumps(calls[1]) and "image_url" in json.dumps(calls[2])
        assert view["budget"]["initial_request_bytes"] == len(encode_json(calls[0]))
        assert len(reads) == 1
        assert result["delivered_image_refs"] == [ref]
        assert result["evidence_events"][0]["image_hash"] == snap.media["1.png"]
        assert library.current("check-target") is None
        draft = Drafts(library).get(result["draft_ids"][0])
        assert draft["review"]["kind"] == "model" and draft["state"] == "approved"
        assert run(req.operation_id, library, evidence, ledger, gateway) == result
        assert len(calls) == 3
    finally:
        gateway.close()


def test_reviewer_can_request_images_and_missing_images_stop_without_success(env):
    library, evidence, ledger, settings = env
    snap = source(env, "synthetic-missing", count=2)
    req = query()
    submit_learning(req, library, evidence, ledger, settings)
    gateway, calls = model([proposal(), {"read_evidence": [{"evidence_ref": snap.id + ":0",
                                                           "reason": "Need after state"}]}])
    try:
        result = run(req.operation_id, library, evidence, ledger, gateway)
        assert result["outcome"] == "needs_evidence" and len(calls) == 2
        assert not result["delivered_image_refs"]
        assert result["evidence_events"][0]["status"] == "missing_image"
        assert Drafts(library).get(result["draft_ids"][0])["state"] == "pending"
    finally:
        gateway.close()


def test_image_request_outside_frozen_window_is_rejected(env):
    library, evidence, ledger, settings = env
    snap = source(env, "synthetic-bounds", image=True, count=40)
    req = query()
    submit_learning(req, library, evidence, ledger, settings)
    gateway, calls = model([{"read_evidence": [{"evidence_ref": snap.id + ":39", "reason": "Outside"}]}])
    try:
        with pytest.raises(ValueError, match="outside the frozen"):
            run(req.operation_id, library, evidence, ledger, gateway)
        assert len(calls) == 1
    finally:
        gateway.close()


def test_byte_budget_does_not_mark_loaded_images_as_delivered(env):
    library, evidence, ledger, settings = env
    snap = source(env, "synthetic-budget", image=True, count=2)
    request = AuthorRequest(operation_id="synthetic-byte-budget", skill_id="check-target",
        sources=[{"snapshot_id": snap.id, "positions": [0], "image_positions": []}],
        evidence_mode="on_demand", instruction="Inspect state")
    submit(request, library, evidence, ledger)
    gateway, calls = model([{"read_evidence": [{"evidence_ref": snap.id + ":0", "reason": "Need state"}]}])
    # First request fits; attached image exceeds the exact same configured limit.
    from evonext.skills.workshop.service import preview
    first = preview(request, library, evidence, gateway.settings)["initial_request_bytes"]
    gateway.settings.model_max_request_bytes = first + 20
    try:
        result = run(request.operation_id, library, evidence, ledger, gateway)
        assert result["outcome"] == "needs_evidence" and result["notes"] == "input_byte_budget"
        assert len(calls) == 1 and not result["delivered_image_refs"]
    finally:
        gateway.close()


def test_http_learning_preview_needs_no_paid_config_and_marks_source_shortfall(env):
    library, evidence, _, _ = env
    source(env, "synthetic-http")
    settings = Settings(demo=True, _env_file=None, workshop_root=str(library.root),
                        workshop_owner=library.owner, review_operator_id="synthetic-operator")
    with TestClient(create_app(settings, evidence.repository, evidence.assets)) as client:
        r = client.post("/api/v1/workshop/learning/preview", json=query().model_dump())
        assert r.status_code == 200 and r.json()["retrieval"]["shortfall"] == 3
        assert r.json()["author_request"]["evidence_mode"] == "on_demand"
        assert client.post("/api/v1/workshop/learning/operations", json=query().model_dump()).status_code == 403


def test_reviewer_loads_new_picture_without_repeating_author_image_reads(env):
    library, evidence, ledger, settings = env
    snap = source(env, "synthetic-review-image", image=True, count=2)
    submit_learning(query(), library, evidence, ledger, settings)
    ref = snap.id + ":0"
    gateway, calls = model([proposal(), {"read_evidence": [{"evidence_ref": ref,
        "reason": "Verify proposal against observed state"}]}, response(ref)])
    try:
        result = run(query().operation_id, library, evidence, ledger, gateway)
        assert result["outcome"] == "approved" and result["model_calls"] == 3
        assert "image_url" not in json.dumps(calls[1])
        assert "image_url" in json.dumps(calls[2])
        assert result["delivered_image_refs"] == [ref]
    finally:
        gateway.close()


def test_shared_image_and_round_budgets_end_as_needs_evidence(env):
    library, evidence, ledger, settings = env
    snap = source(env, "synthetic-shared-budget", image=True, count=6)
    submit_learning(query(), library, evidence, ledger, settings)
    refs = [snap.id + ":" + str(i) for i in range(6)]
    def read(group):
        return {"read_evidence": [{"evidence_ref": r, "reason": "Check state"} for r in group]}
    gateway, calls = model([read(refs[:4]), read(refs[4:])])
    try:
        result = run(query().operation_id, library, evidence, ledger, gateway)
        assert result["outcome"] == "needs_evidence" and len(calls) == 2
        assert len(result["delivered_image_refs"]) == 4
        assert [e["status"] for e in result["evidence_events"]][-2:] == ["image_budget"] * 2
    finally:
        gateway.close()


def test_no_change_consumes_one_call_without_reading_media(env):
    library, evidence, ledger, settings = env
    source(env, "synthetic-no-change", image=True)
    submit_learning(query(), library, evidence, ledger, settings)
    evidence.read_media = lambda *_: pytest.fail("No image was requested")
    gateway, calls = model([{"decision": "no_change", "reason": "No reusable increment"}])
    try:
        result = run(query().operation_id, library, evidence, ledger, gateway)
        assert result["outcome"] == "no_change" and not result["draft_ids"]
        assert len(calls) == 1 and not result["delivered_image_refs"]
    finally:
        gateway.close()


def test_invalid_repair_does_not_lose_prior_draft_or_break_result(env):
    library, evidence, ledger, settings = env
    snap = source(env, "synthetic-invalid-repair", count=2)
    submit_learning(query(), library, evidence, ledger, settings)
    gateway, calls = model([proposal(), response(snap.id + ":0", "rejected"),
                            {"decision": "propose", "reason": "Bad repair", "files": {}}])
    try:
        result = run(query().operation_id, library, evidence, ledger, gateway)
        assert result["outcome"] == "rejected" and len(result["draft_ids"]) == 1
        assert result["body_chars"] > 0
    finally:
        gateway.close()


def test_seed_holdout_and_ambiguous_skills_fail_before_any_operation(env):
    library, evidence, ledger, settings = env
    heldout = source(env, "synthetic-test", meta={"split": "test"})
    with pytest.raises(ValueError, match="held_out_source"):
        submit_learning(query(seed_snapshot_id=heldout.id), library, evidence, ledger, settings)
    assert not ledger.rows
    source(env, "synthetic-ok")
    for sid in ("first-guide", "second-guide"):
        document = f"---\nname: {sid}\ndescription: account sorting\n---\nInspect account sorting.\n"
        library.save(sid, document, expected_revision=None, source_snapshots=["a" * 64],
                     actor="synthetic", reason="synthetic")
    with pytest.raises(ValueError, match="Ambiguous"):
        plan(LearningRequest(operation_id="synthetic-ambiguous", topic="account sorting"),
             library, evidence, settings)
    assert not ledger.rows


def test_http_submit_and_get_share_existing_worker_operation(env, monkeypatch):
    pytest.importorskip("celery", reason="queue assembly requires the infra extra")
    from pydantic import SecretStr
    library, evidence, ledger, _ = env
    snap = source(env, "synthetic-api-queue", count=2)
    monkeypatch.setattr("evonext.operations.ledger.Ledger", lambda _: ledger)
    queued = []
    monkeypatch.setattr("celery.Celery.send_task", lambda self, name, **kw: queued.append((name, kw)))
    settings = Settings(_env_file=None, api_key=SecretStr("synthetic"),
        postgres_dsn=SecretStr("postgresql://synthetic-unused"), model_calls_enabled=True,
        model_name="synthetic", review_operator_id="synthetic-operator",
        workshop_root=str(library.root), workshop_owner=library.owner)
    ledger.close = lambda: None
    headers = {"X-API-Key": "synthetic"}
    with TestClient(create_app(settings, evidence.repository, evidence.assets)) as client:
        result = client.post("/api/v1/workshop/learning/operations", json=query().model_dump(), headers=headers)
        assert result.status_code == 202 and result.json()["status"] == "pending"
        assert queued[0][0] == "evonext.workshop"
        assert queued[0][1]["args"] == [query().operation_id]
        gateway, calls = model([proposal(), response(snap.id + ":0")])
        try:
            run(query().operation_id, library, evidence, ledger, gateway)
            saved = client.get("/api/v1/workshop/operations/" + query().operation_id, headers=headers).json()
            assert saved["result"]["outcome"] == "approved"
            assert saved["result"]["retrieval"]["selected_count"] == 1
            assert client.post("/api/v1/workshop/learning/operations", json=query().model_dump(),
                               headers=headers).json()["status"] == "completed"
            assert len(queued) == 1 and len(calls) == 2
        finally:
            gateway.close()


def test_author_review_and_repair_share_six_call_limit(env):
    library, evidence, ledger, settings = env
    snap = source(env, "synthetic-six", image=True, count=3)
    submit_learning(query(), library, evidence, ledger, settings)
    refs = [snap.id + ":" + str(i) for i in range(3)]
    def read(ref):
        return {"read_evidence": [{"evidence_ref": ref, "reason": "Check state"}]}
    gateway, calls = model([read(refs[0]), proposal(), read(refs[1]), response(refs[1], "rejected"),
                            proposal(), read(refs[2])])
    try:
        result = run(query().operation_id, library, evidence, ledger, gateway)
        assert result["outcome"] == "needs_evidence" and len(calls) == 6
        assert result["notes"] == "evidence_round_budget"
        assert len(result["delivered_image_refs"]) == 2
    finally:
        gateway.close()


def test_window_rare_operation_terms_outweigh_repeated_account_name():
    steps = [{"value": {"raw_model_output": "<action>open synthetic account</action>"}}
             for _ in range(30)]
    for pos in (22, 23, 24):
        steps[pos]["value"]["raw_model_output"] = "<action>inspect sorting menu</action>"
    snapshot = Snapshot.create(encode_json({"task_id": "synthetic-weighted-span",
        "instruction": "account sorting menu", "metadata": None,
        "evaluation": {"prediction": {"task_status": {"unknown_source_field": True}}}, "traj": steps}))
    positions = select_window(snapshot, "account sorting menu").positions
    assert {21, 22, 23, 24, 25}.issubset(positions)
    from evonext.skills.workshop.learning import lineage, source_label
    assert lineage(snapshot) == "synthetic-weighted-span"
    assert source_label(snapshot) == "unknown"


def test_chinese_name_bigrams_do_not_count_as_several_query_chunks():
    steps = [{"value": {"text": "等待"}} for _ in range(40)]
    for pos in (3, 6, 7, 9):
        steps[pos]["value"]["text"] = "查看青小禾账号"
    for pos in (8, 23, 24, 25):
        steps[pos]["value"]["text"] = "打开作品排序"
    steps[26]["value"]["text"] = "查看作品"
    snapshot = Snapshot.create(encode_json({'task_id': 'synthetic-chinese-window',
        'instruction': '作品排序', 'traj': steps}))
    positions = select_window(snapshot, '青小禾 作品 排序').positions
    assert {22, 23, 24, 25, 26}.issubset(positions)
    assert positions[0] > 9


def test_image_request_timeout_retains_loaded_hash_and_never_resends_unknown(env):
    import httpx
    from evonext.providers.receipts import CallHeld
    from evonext.skills.workshop.service import keys
    library, evidence, ledger, settings = env
    snap = source(env, 'synthetic-image-timeout', image=True, count=2)
    submit_learning(query(), library, evidence, ledger, settings)
    ref = snap.id + ':0'
    gateway, calls = model([{'read_evidence': [{'evidence_ref': ref, 'reason': 'Check state'}]},
                            httpx.WriteTimeout('synthetic send timeout')])
    try:
        with pytest.raises(httpx.WriteTimeout):
            run(query().operation_id, library, evidence, ledger, gateway)
        key = keys(query().operation_id)
        event = ledger.get(key + '-evidence-1')['payload']
        assert event['delivery'] == 'not_confirmed'
        assert event['events'][0]['status'] == 'loaded_not_yet_delivered'
        assert event['events'][0]['image_hash'] == snap.media['0.png']
        assert ledger.get(key + '-author0-read-1')['payload']['image_refs'] == [ref]
        assert ledger.get(key + '-result') is None
        with pytest.raises(CallHeld):
            run(query().operation_id, library, evidence, ledger, gateway)
        assert len(calls) == 2
    finally:
        gateway.close()


def test_image_quality_is_frozen_and_preview_measures_the_sent_jpeg(env):
    import base64
    from evonext.contracts.trajectory import sha256
    from evonext.evidence.image_views import JPEG90_PROFILE
    from evonext.skills.workshop.service import SourceWindow, preview, keys
    library, evidence, ledger, settings = env
    snap = source(env, 'synthetic-quality', image=True, count=1)
    request = AuthorRequest(operation_id='synthetic-quality', skill_id='check-target',
        instruction='Inspect synthetic state', include_images=True,
        sources=[SourceWindow(snapshot_id=snap.id, positions=[0])])
    settings.model_name = 'synthetic'
    settings.model_image_quality = 90
    view = preview(request, library, evidence, settings)
    assert view['image_profile'] == JPEG90_PROFILE
    assert view['image_views'][0]['jpeg_quality'] == 90
    submit(request, library, evidence, ledger, settings=settings)
    settings.model_image_quality = 98
    gateway, calls = model([proposal(), response(snap.id + ':0')])
    try:
        result = run(request.operation_id, library, evidence, ledger, gateway)
        assert result['image_profile'] == JPEG90_PROFILE
        assert view['initial_request_bytes'] == len(encode_json(calls[0]))
        url = calls[0]['messages'][1]['content'][-1]['image_url']['url']
        wire = base64.b64decode(url.split(',', 1)[1], validate=True)
        assert url.startswith('data:image/jpeg;base64,')
        assert view['image_views'][0]['view_sha256'] == sha256(wire)
        assert ledger.get(keys(request.operation_id))['payload']['image_profile'] == JPEG90_PROFILE
        assert evidence.read_media(snap.id, '0.png').startswith(b'\x89PNG')
    finally:
        gateway.close()


def test_preexisting_workshop_operation_retains_its_original_image_profile(env):
    from evonext.evidence.image_views import SOURCE_PROFILE
    from evonext.skills.workshop.service import SourceWindow, prepare_authoring, keys
    library, evidence, ledger, _ = env
    snap = source(env, 'synthetic-old-image-profile', image=True, count=1)
    request = AuthorRequest(operation_id='synthetic-old-profile', skill_id='check-target',
        instruction='Inspect synthetic state', include_images=True,
        sources=[SourceWindow(snapshot_id=snap.id, positions=[0])])
    payload, _, _ = prepare_authoring(request, library, evidence, image_profile=SOURCE_PROFILE)
    del payload['image_profile']
    ledger.record(keys(request.operation_id), snap.id, 'workshop_request.v1', payload)
    gateway, calls = model([proposal(), response(snap.id + ':0')])
    try:
        result = run(request.operation_id, library, evidence, ledger, gateway)
        assert result['image_profile'] == SOURCE_PROFILE and result['image_views'] == {}
        assert calls[0]['messages'][1]['content'][-1]['image_url']['url'].startswith('data:image/png;base64,')
    finally:
        gateway.close()
