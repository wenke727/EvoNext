"""Synthetic authoring evidence and transport only; no device or paid model calls."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from evonext.app.api import create_app
from evonext.config import Settings
from evonext.contracts.runtime import RuntimeRequest, Target
from evonext.contracts.skills import SkillAsset
from evonext.contracts.trajectory import ContractError, Snapshot, encode_json, load_json, sha256
from evonext.evidence.service import EvidenceService
from evonext.evidence.store import MemoryAssets, MemorySnapshots
from evonext.providers.gateway import ModelGateway
from evonext.providers.receipts import CallHeld, MemoryCallReceipts
from evonext.runtime.context import prepare_trial
from evonext.skills.workshop import Workshop
from evonext.skills.workshop.authoring import diet, validate_files
from evonext.skills.workshop.drafts import Drafts
from evonext.skills.workshop.service import AuthorRequest, SourceWindow, keys, run, source_input, status, submit

DOCUMENT = (Path(__file__).parents[1] / "examples/skills/check-target.md").read_text(encoding="utf-8")


class SyntheticLedger:
    def __init__(self):
        self.rows = {}

    def record(self, key, snapshot_id, kind, payload):
        row = {"snapshot_id": snapshot_id, "kind": kind, "payload": copy.deepcopy(payload)}
        if key in self.rows and self.rows[key] != row:
            raise ContractError("Operation ID already has a different result")
        self.rows[key] = row

    def get(self, key):
        return copy.deepcopy(self.rows.get(key))


@pytest.fixture
def env(tmp_path):
    settings = Settings(demo=True, _env_file=None)
    evidence = EvidenceService(MemorySnapshots(), MemoryAssets(), settings)
    snapshot = Snapshot.create(encode_json({"task_id": "synthetic-workshop",
        "instruction": "Read the selected target", "traj": [
            {"step_id": "before", "image": None, "value": {"text": "Target visible"}},
            {"step_id": "after", "image": None, "value": {"text": "FUTURE-EVIDENCE"}}]}))
    evidence.accept(snapshot)
    return Workshop(tmp_path / "skills", "operator"), evidence, snapshot, SyntheticLedger()


def create(env, document=DOCUMENT, base=None, reason="synthetic"):
    library, _, snapshot, _ = env
    return Drafts(library).create(skill_id="check-target", base_revision=base,
        files={"SKILL.md": document}, sources=[snapshot.id], reason=reason)


def approve(drafts, draft):
    return drafts.review(draft["draft_id"], verdict="approved", notes="Synthetic review",
                         actor="operator")


def request(env, **kwargs):
    return AuthorRequest(operation_id="synthetic-author", skill_id="check-target",
        instruction="Learn the repeatable target check",
        sources=[SourceWindow(snapshot_id=env[2].id, positions=[0])], **kwargs)


def proposal(text=DOCUMENT):
    return {"decision": "propose", "reason": "Synthetic source supports target check",
            "files": {"SKILL.md": text}, "headings": []}


def review(env, verdict="approved"):
    return {"verdict": verdict, "notes": "Synthetic rule audit", "evidence_refs": [env[2].id + ":0"]}


def model(responses):
    calls = []
    def handler(req):
        calls.append(json.loads(req.content))
        result = responses[len(calls) - 1]
        if isinstance(result, Exception):
            raise result
        return httpx.Response(200, json={"model": "synthetic",
            "choices": [{"message": {"content": json.dumps(result)}}]})
    settings = Settings(demo=True, _env_file=None, model_calls_enabled=True, model_name="synthetic",
        model_api_key=SecretStr("synthetic"), model_base_url="https://synthetic.invalid/v1")
    return ModelGateway(settings, transport=httpx.MockTransport(handler),
                        receipts=MemoryCallReceipts()), calls


def test_multifile_restore_archive_and_frozen_runtime(env):
    library, _, snapshot, _ = env
    a = library.save("check-target", DOCUMENT, expected_revision=None,
        source_snapshots=[snapshot.id], reason="synthetic", actor="operator",
        assets={"references/check.md": "# Check\nRead state before action.\n"})
    bundle = library.export("check-target", a["revision"])
    assert bundle.format_version == "v2"
    req = RuntimeRequest(trial_id="synthetic", session_id="session", task_id=snapshot.document["task_id"],
        snapshot_id=snapshot.id, owner="operator", target=Target(kind="local_device", resource_id="none"),
        context_mode="skill", skills=(bundle,))
    assert b"Read state" in prepare_trial(req, snapshot).context_json
    forged = bundle.model_copy(update={"assets": (SkillAsset(path="references/check.md", content="changed"),)})
    with pytest.raises(ContractError, match="hash"):
        prepare_trial(req.model_copy(update={"skills": (forged,)}), snapshot)
    b = library.save("check-target", DOCUMENT, expected_revision=a["revision"],
        source_snapshots=[snapshot.id], reason="synthetic change", actor="operator",
        assets={"references/check.md": "# Check\nStop on unknown state.\n"})
    assert "Stop on unknown" in library.diff("check-target", a["revision"], b["revision"])
    c = library.restore("check-target", a["revision"], expected_revision=b["revision"], actor="operator")
    assert library.export("check-target", c["revision"]).assets == bundle.assets
    archived = library.archive("check-target", expected_revision=c["revision"], actor="operator")
    assert library.files("check-target", archived["revision"])["references/check.md"] == bundle.assets[0].content


@pytest.mark.parametrize("path", ["../escape", "references/../escape", "references\\bad.md",
                                 "/root.md", "scripts/C:/bad", "assets/.hidden"])
def test_unsafe_asset_paths_rejected(path):
    with pytest.raises(ValueError):
        validate_files("check-target", {"SKILL.md": DOCUMENT, path: "bad"})


def test_case_insensitive_asset_collisions_rejected():
    with pytest.raises(ContractError, match="Duplicate"):
        validate_files("check-target", {"SKILL.md": DOCUMENT, "assets/a": "", "assets/A": ""})


def test_missing_reference_and_anchor_rejected():
    for link in ["references/no.md", "references/check.md#absent", "javascript:alert"]:
        with pytest.raises(ContractError):
            validate_files("check-target", {"SKILL.md": DOCUMENT + f"\n[Read]({link})",
                                           "references/check.md": "# Check\nStop."})
    validate_files("check-target", {"SKILL.md": DOCUMENT + "\n[Read](references/check.md#check)",
                                  "references/check.md": "# Check\nStop."})


def test_markdown_reference_links_are_checked_and_code_examples_are_inert():
    validate_files("check-target", {"SKILL.md": DOCUMENT +
        "\n[Read][conditions]\n\n[conditions]: references/check.md#check\n"
        "\n```\n[Example](not-a-real-file.md)\n```\n",
        "references/check.md": "# Check\nStop."})
    with pytest.raises(ContractError, match="Missing"):
        validate_files("check-target", {"SKILL.md": DOCUMENT +
            "\n[Read][conditions]\n\n[conditions]: references/absent.md\n"})
    with pytest.raises(ContractError, match="reachable"):
        validate_files("check-target", {"SKILL.md": DOCUMENT, "references/orphan.md": "Stop."})


def test_old_v1_export_and_runtime_context_bytes_stay_compatible(env):
    library, _, snapshot, _ = env
    saved = library.save("check-target", DOCUMENT, expected_revision=None,
        source_snapshots=[snapshot.id], reason="synthetic", actor="operator")
    bundle = library.export("check-target", saved["revision"])
    assert set(bundle.model_dump()) == {"ref", "document"}
    assert bundle.ref.content_hash == sha256(DOCUMENT.encode())
    req = RuntimeRequest(trial_id="synthetic", session_id="session", task_id=snapshot.document["task_id"],
        snapshot_id=snapshot.id, owner="operator", target=Target(kind="local_device", resource_id="none"),
        context_mode="skill", skills=(bundle,))
    assert prepare_trial(req, snapshot).context_json == encode_json(
        {"mode": "skill", "skills": [{"ref": bundle.ref.model_dump(mode="json"), "document": DOCUMENT}]})


def test_draft_requires_review_and_exact_base(env):
    library = env[0]
    drafts = Drafts(library)
    a = create(env)
    with pytest.raises(ContractError, match="approved"):
        drafts.commit(a["draft_id"], "operator")
    approve(drafts, a)
    competing = create(env, DOCUMENT + "\nOther change", reason="competing")
    approve(drafts, competing)
    drafts.commit(competing["draft_id"], "operator")
    with pytest.raises(ContractError, match="changed"):
        drafts.commit(a["draft_id"], "operator")
    assert drafts.get(a["draft_id"])["state"] == "approved"


def test_review_does_not_transfer_to_edited_draft(env):
    drafts = Drafts(env[0])
    first = create(env)
    approve(drafts, first)
    edited = create(env, DOCUMENT + "\nNew condition")
    assert edited["review"] is None
    with pytest.raises(ContractError, match="approved"):
        drafts.commit(edited["draft_id"], "operator")


def test_revision_keeps_original_evidence_when_learning_from_another_snapshot(env):
    drafts = Drafts(env[0])
    first = create(env)
    approve(drafts, first)
    base = drafts.commit(first["draft_id"], "operator")["commit"]["revision"]
    second = drafts.create(skill_id="check-target", base_revision=base,
        files={"SKILL.md": DOCUMENT + "\nCheck ambiguity."}, sources=["a" * 64],
        reason="Another synthetic observation")
    assert set(second["proposal"]["sources"]) == {env[2].id, "a" * 64}


def test_commit_reconciles_crash_after_head_update(env, monkeypatch):
    import evonext.skills.workshop.drafts as module
    drafts = Drafts(env[0])
    item = create(env)
    approve(drafts, item)
    original = module._atomic
    def fail_receipt(path, data):
        if load_json(data).get("state") == "committed":
            raise OSError("synthetic disk failure")
        original(path, data)
    monkeypatch.setattr(module, "_atomic", fail_receipt)
    with pytest.raises(OSError):
        drafts.commit(item["draft_id"], "operator")
    assert len(env[0].history("check-target")) == 1
    monkeypatch.setattr(module, "_atomic", original)
    assert Drafts(env[0]).commit(item["draft_id"], "operator")["state"] == "committed"
    assert len(env[0].history("check-target")) == 1


def test_concurrent_commit_same_draft_is_idempotent(env):
    drafts = Drafts(env[0])
    item = create(env)
    approve(drafts, item)
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: drafts.commit(item["draft_id"], "operator"), range(4)))
    assert len({r["commit"]["revision"] for r in results}) == 1
    assert len(env[0].history("check-target")) == 1
    assert create(env)["state"] == "committed"


def test_draft_tampering_and_discard(env):
    drafts = Drafts(env[0])
    item = create(env)
    drafts.discard(item["draft_id"])
    with pytest.raises(ContractError):
        approve(drafts, item)
    path = drafts._path(item["draft_id"])
    data = load_json(path.read_bytes())
    data["proposal"]["files"]["SKILL.md"] += "\nTampered"
    path.write_bytes(encode_json(data))
    with pytest.raises(ContractError, match="identity"):
        drafts.get(item["draft_id"])


def test_diet_preserves_sections_and_frontmatter():
    section = "## Recovery\n" + "If state is unknown, stop and ask for evidence.\n" * 25
    files = {"SKILL.md": DOCUMENT + "\n" + section}
    result = diet(files, ["Recovery"])
    assert section == result["references/diet.md"]
    assert result["SKILL.md"].split("---", 2)[:2] == DOCUMENT.split("---", 2)[:2]
    assert "before applying this section" in result["SKILL.md"]
    validate_files("check-target", result)
    with pytest.raises(ContractError):
        diet(result, ["Recovery"])


@pytest.mark.parametrize("section", ["## Recovery\nShort\n",
    "## Recovery\n[Link](references/old.md)\n" + "Long rule\n" * 100,
    "## Recovery\n```\n## False heading\n```\n" + "Long rule\n" * 100])
def test_diet_stops_when_relocation_cannot_be_verified(section):
    with pytest.raises(ContractError):
        diet({"SKILL.md": DOCUMENT + "\n" + section}, ["Recovery"])


def test_source_selection_never_includes_unselected_steps(env):
    rows, images = source_input(request(env), env[1])
    assert len(rows) == 1 and not images
    assert b"FUTURE-EVIDENCE" not in encode_json(rows)
    assert not rows[0]["image_attached_to_input"]
    bad = request(env)
    bad.sources[0].positions = [99]
    with pytest.raises(ContractError):
        source_input(bad, env[1])


def test_learning_reviews_without_auto_commit_and_result_reuses(env):
    library, evidence, _, ledger = env
    req = request(env)
    submit(req, library, evidence, ledger)
    gateway, calls = model([proposal(), review(env)])
    try:
        result = run(req.operation_id, library, evidence, ledger, gateway)
        assert result["outcome"] == "approved" and not result["auto_committed"]
        assert library.current("check-target") is None
        draft = Drafts(library).get(result["draft_ids"][0])
        assert draft["review"]["kind"] == "model"
        assert draft["review"]["evidence_refs"] == [env[2].id + ":0"]
        assert draft["proposal"]["provenance"]["source_windows"][0]["positions"] == [0]
        assert run(req.operation_id, library, evidence, ledger, gateway) == result
        assert len(calls) == 2
    finally:
        gateway.close()


@pytest.mark.parametrize("decision", ["no_change", "needs_evidence"])
def test_no_change_and_missing_evidence_are_completed_results(env, decision):
    library, evidence, _, ledger = env
    req = request(env)
    submit(req, library, evidence, ledger)
    gateway, calls = model([{"decision": decision, "reason": "Insufficient basis", "files": {}, "headings": []}])
    try:
        result = run(req.operation_id, library, evidence, ledger, gateway)
        assert result["outcome"] == decision and not result["draft_ids"] and len(calls) == 1
    finally:
        gateway.close()


def test_repair_is_bounded_to_one_and_preserves_rejected_draft(env):
    library, evidence, _, ledger = env
    req = request(env)
    submit(req, library, evidence, ledger)
    gateway, calls = model([proposal(), review(env, "rejected"),
                            proposal(DOCUMENT + "\nCheck observed state."), review(env, "rejected")])
    try:
        result = run(req.operation_id, library, evidence, ledger, gateway)
        assert result["outcome"] == "rejected" and len(calls) == 4
        assert len(result["draft_ids"]) == 2 and library.current("check-target") is None
    finally:
        gateway.close()


def test_explicit_diet_uses_host_movement_and_model_review(env):
    library, evidence, snapshot, ledger = env
    section = "## Recovery\n" + "Stop when state is ambiguous; request evidence before acting.\n" * 30
    saved = library.save("check-target", DOCUMENT + "\n" + section, expected_revision=None,
        source_snapshots=[snapshot.id], reason="synthetic", actor="operator")
    req = request(env, mode="diet", base_revision=saved["revision"])
    submit(req, library, evidence, ledger)
    gateway, calls = model([{"decision": "propose", "reason": "Move recovery details",
                            "headings": ["Recovery"], "files": {}}, review(env)])
    try:
        result = run(req.operation_id, library, evidence, ledger, gateway)
        draft = Drafts(library).get(result["draft_ids"][0])
        assert draft["proposal"]["files"]["references/diet.md"] == section
        assert len(calls) == 2 and library.current("check-target")["revision"] == saved["revision"]
    finally:
        gateway.close()


def test_case_inputs_freeze_exact_review_and_require_selected_step(env):
    from uuid import uuid4
    from evonext.review.contracts import CaseProposal, verify_proposal
    from evonext.review.store import MemoryCases
    from evonext.skills.workshop.service import CaseInput
    library, evidence, snapshot, ledger = env
    cases = MemoryCases()
    case_id = str(uuid4())
    case = CaseProposal(case_id=case_id, snapshot_id=snapshot.id, position=0,
                        issue_kind="step_action", summary="Synthetic ambiguous target",
                        evidence_refs=["step:0"])
    cases.create(verify_proposal(case, snapshot), actor="operator")
    cases.decide(case_id, 0, "needs_evidence", "No observed execution", actor="operator")
    req = request(env, cases=[CaseInput(case_id=case_id, revision=1)])
    submit(req, library, evidence, ledger, cases)
    frozen = ledger.get(keys(req.operation_id))["payload"]["cases"][0]
    assert frozen["review"]["revision"] == 1 and "not executed" in frozen["meaning"]
    other = req.model_copy(deep=True)
    other.operation_id = "other"
    other.sources[0].positions = [1]
    with pytest.raises(ContractError, match="selected"):
        submit(other, library, evidence, ledger, cases)


def test_unknown_review_cannot_rebill_author_or_retry_review(env):
    library, evidence, _, ledger = env
    req = request(env)
    submit(req, library, evidence, ledger)
    gateway, calls = model([proposal(), httpx.ReadTimeout("synthetic unknown")])
    try:
        with pytest.raises(httpx.ReadTimeout):
            run(req.operation_id, library, evidence, ledger, gateway)
        with pytest.raises(CallHeld):
            run(req.operation_id, library, evidence, ledger, gateway)
        assert len(calls) == 2 and Drafts(library).list()[0]["state"] == "pending"
        gateway.settings.model_name = "changed"
        with pytest.raises(ContractError, match="different result"):
            run(req.operation_id, library, evidence, ledger, gateway)
        assert len(calls) == 2
    finally:
        gateway.close()


def test_wrong_evidence_reference_stops_review(env):
    library, evidence, _, ledger = env
    req = request(env)
    submit(req, library, evidence, ledger)
    gateway, _ = model([proposal(), {**review(env), "evidence_refs": ["invented:0"]}])
    try:
        with pytest.raises(ContractError, match="cite"):
            run(req.operation_id, library, evidence, ledger, gateway)
        assert Drafts(library).list()[0]["state"] == "pending"
    finally:
        gateway.close()


def test_operation_identity_cannot_change_evidence(env):
    library, evidence, _, ledger = env
    req = request(env)
    submit(req, library, evidence, ledger)
    req.sources[0].positions = [1]
    with pytest.raises(ContractError, match="another"):
        submit(req, library, evidence, ledger)
    assert ledger.get(keys(req.operation_id))["payload"]["request"]["sources"][0]["positions"] == [0]
    assert status(req.operation_id, ledger, "different-owner") is None


def test_api_manual_draft_review_commit_and_reopen(env, tmp_path):
    settings = Settings(demo=True, _env_file=None, workshop_root=str(tmp_path / "api-skills"),
                        workshop_owner="operator", review_operator_id="operator")
    repository, assets = MemorySnapshots(), MemoryAssets()
    app = create_app(settings, repository, assets)
    with TestClient(app) as client:
        snapshot = client.post("/api/v1/snapshots", json={"trajectory": env[2].document}).json()
        body = {"skill_id": "check-target", "files": {"SKILL.md": DOCUMENT},
                "source_snapshots": [snapshot["snapshot_id"]], "reason": "synthetic"}
        response = client.post("/api/v1/workshop/drafts", json=body)
        assert response.status_code == 201, response.text
        unsafe = {**body, "files": {"SKILL.md": DOCUMENT, "../unsafe": "inert"}}
        assert client.post("/api/v1/workshop/drafts", json=unsafe).status_code == 400
        draft_id = response.json()["draft_id"]
        path = "/api/v1/workshop/drafts/" + draft_id
        assert client.post(path + "/commit").status_code == 400
        assert client.post(path + "/review", json={"verdict": "approved", "notes": "Synthetic"}).status_code == 200
        saved = client.post(path + "/commit").json()
        assert saved["state"] == "committed"
        exported = client.get("/api/v1/workshop/skills/check-target/export/" + saved["commit"]["revision"])
        assert exported.status_code == 200 and exported.json()["document"] == DOCUMENT
        assert client.post("/api/v1/workshop/operations", json=request(env).model_dump()).status_code == 403
    with TestClient(create_app(settings, repository, assets)) as restarted:
        assert restarted.get(path).json()["commit"] == saved["commit"]
        assert len(restarted.get("/api/v1/workshop").json()["skills"]) == 1


def test_api_requires_explicit_root_and_auth():
    settings = Settings(api_key=SecretStr("synthetic"), _env_file=None)
    with TestClient(create_app(settings, MemorySnapshots(), MemoryAssets())) as client:
        assert client.get("/api/v1/workshop").status_code == 401
        assert client.get("/api/v1/workshop", headers={"X-API-Key": "synthetic"}).status_code == 503
