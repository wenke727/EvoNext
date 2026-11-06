from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from evonext.contracts.runtime import ExecutionGrant, RecoveryRequest, RuntimeRequest, Target
from evonext.contracts.trajectory import ContractError, Snapshot, encode_json, load_json
from evonext.runtime.context import check_grant, prepare_trial, verify_usage
from evonext.skills.workshop import Workshop

DOCUMENT = (Path(__file__).resolve().parents[1] / "examples/skills/check-target.md").read_text()


def source():
    return Snapshot.create(encode_json({"task_id": "synthetic", "instruction": "Read only",
        "traj": [{"step_id": "s1", "image": None, "value": {"raw_model_output": "first", "human_gold": "SECRET"}},
                 {"step_id": "s2", "image": None, "value": {"raw_model_output": "future"}}]}))


def save(library, text=DOCUMENT, expected=None):
    return library.save("check-target", text, expected_revision=expected,
        source_snapshots=[source().id], reason="synthetic", actor="operator")


def test_skill_create_patch_history_no_change_and_undo(tmp_path):
    library = Workshop(tmp_path, "owner")
    a = save(library)
    assert a["changed"]
    assert not save(library, expected=a["revision"])["changed"]
    b = save(library, DOCUMENT + "\nStop before changing a setting.\n", expected=a["revision"])
    assert len(library.history("check-target")) == 2
    assert "Stop before" in library.diff("check-target", a["revision"], b["revision"])
    undo = library.restore("check-target", a["revision"], expected_revision=b["revision"], actor="operator")
    assert undo["revision"] not in {a["revision"], b["revision"]}
    assert library.read("check-target")[1] == DOCUMENT
    assert library.read("check-target", b["revision"])[1].endswith("setting.\n")
    assert len(library.history("check-target")) == 3


def test_stale_skill_edit_rejected(tmp_path):
    library = Workshop(tmp_path, "owner")
    save(library)
    with pytest.raises(ContractError, match="changed"):
        save(library, DOCUMENT + "\nnew")


def test_skill_owner_and_revision_integrity(tmp_path):
    library = Workshop(tmp_path, "owner")
    a = save(library)
    with pytest.raises(ContractError, match="different owner"):
        Workshop(tmp_path, "someone-else")
    path = tmp_path / "check-target" / "revisions" / a["revision"] / "SKILL.md"
    path.write_text(DOCUMENT + "tampered")
    with pytest.raises(ContractError, match="hash"):
        library.export("check-target", a["revision"])


def test_archive_blocks_new_export_but_preserves_old_snapshot(tmp_path):
    library = Workshop(tmp_path, "owner")
    a = save(library)
    frozen = library.export("check-target", a["revision"])
    library.archive("check-target", expected_revision=a["revision"], actor="operator")
    with pytest.raises(ContractError, match="Archived"):
        library.export("check-target", a["revision"])
    assert frozen.document == DOCUMENT


@pytest.mark.parametrize("name", ["../escape", "a/b", "UPPER", ".", ""])
def test_workshop_rejects_unsafe_identity(tmp_path, name):
    library = Workshop(tmp_path, "owner")
    with pytest.raises(ContractError):
        library.read(name)


def test_symlinked_skill_root_rejected(tmp_path):
    library = Workshop(tmp_path / "library", "owner")
    other = tmp_path / "other"
    other.mkdir()
    (tmp_path / "library" / "check-target").symlink_to(other, target_is_directory=True)
    with pytest.raises(ContractError):
        save(library)


def test_duplicate_yaml_and_mismatching_name_rejected(tmp_path):
    library = Workshop(tmp_path, "owner")
    for text in [DOCUMENT.replace("name: check-target", "name: check-target\nname: check-target"),
                 DOCUMENT.replace("name: check-target", "name: unrelated")]:
        with pytest.raises(ContractError):
            save(library, text)


def test_concurrent_skill_cas_one_winner(tmp_path):
    library = Workshop(tmp_path, "owner")
    a = save(library)
    def update(i):
        try:
            save(Workshop(tmp_path, "owner"), DOCUMENT + f"\nchange {i}", expected=a["revision"])
            return True
        except ContractError:
            return False
    with ThreadPoolExecutor(4) as pool:
        assert sum(pool.map(update, range(4))) == 1
    assert len(library.history("check-target")) == 2


def test_frozen_runtime_context_ignores_later_workshop_edits(tmp_path):
    library = Workshop(tmp_path, "owner")
    a = save(library)
    bundle = library.export("check-target", a["revision"])
    snapshot = source()
    request = RuntimeRequest(trial_id="trial-1", session_id="session", task_id="synthetic",
        snapshot_id=snapshot.id, owner="owner", target=Target(kind="local_device", resource_id="device-1"),
        context_mode="skill", skills=(bundle,))
    plan = prepare_trial(request, snapshot)
    save(library, DOCUMENT + "\nfuture-edit", expected=a["revision"])
    assert b"future-edit" not in plan.context_json
    assert plan == prepare_trial(request, snapshot)
    assert load_json(plan.plan_json)["status"] == "prepared_not_executed"
    grant = ExecutionGrant(grant_id="grant", trial_id=request.trial_id, task_id=request.task_id,
        snapshot_id=snapshot.id, owner="owner", target=request.target, max_actions=20,
        expires_at_epoch=100, allowed_skills=(bundle.ref,), allow_candidate_skills=True)
    check_grant(request, grant, now=10)
    with pytest.raises(PermissionError):
        check_grant(request, grant, now=100)
    with pytest.raises(PermissionError):
        check_grant(request, grant.model_copy(update={"allow_candidate_skills": False}), now=10)
    with pytest.raises(PermissionError):
        check_grant(request, grant.model_copy(update={"allowed_skills": ()}), now=10)


@pytest.mark.parametrize("kind", ["local_device", "cloud_batch"])
def test_runtime_targets_and_raw_cutoff(kind):
    snapshot = source()
    request = RuntimeRequest(trial_id="trial", session_id="session", task_id="synthetic",
        snapshot_id=snapshot.id, owner="owner", target=Target(kind=kind, resource_id="resource"),
        context_mode="raw", before_step_position=1)
    plan = prepare_trial(request, snapshot)
    assert b"first" in plan.context_json
    assert b"future" not in plan.context_json
    assert b"SECRET" not in plan.context_json
    receipt = {"plan_id": plan.id, "trial_id": "trial", "task_id": "synthetic",
        "snapshot_id": snapshot.id, "context_hash": plan.context_hash, "skill_refs": [],
        "new_trajectory_ref": "new-trial-evidence"}
    assert verify_usage(plan, receipt)["outcome"] == "not_assessed"
    assert not verify_usage(plan, receipt)["execution_verified"]
    receipt["context_hash"] = "changed"
    with pytest.raises(ContractError):
        verify_usage(plan, receipt)


def test_recovery_is_request_not_claim_of_restore():
    snapshot = source()
    request = RuntimeRequest(trial_id="trial", session_id="session", task_id="synthetic",
        snapshot_id=snapshot.id, owner="owner", target=Target(kind="local_device", resource_id="device"),
        recovery=RecoveryRequest(strategy="replay_prefix", reviewed_case_ref="case@1",
            source_step_id="s1", correction_boundary="before_action", expected_state_hash="0" * 64))
    plan = prepare_trial(request, snapshot)
    assert load_json(plan.plan_json)["status"] == "prepared_not_executed"
    bad = request.model_copy(update={"recovery": request.recovery.model_copy(update={"source_step_id": "missing"})})
    with pytest.raises(ContractError):
        prepare_trial(bad, snapshot)


def test_runtime_input_identity_mismatch():
    snapshot = source()
    request = RuntimeRequest(trial_id="trial", session_id="session", task_id="wrong",
        snapshot_id=snapshot.id, owner="owner", target=Target(kind="cloud_batch", resource_id="batch"))
    with pytest.raises(ContractError):
        prepare_trial(request, snapshot)


def test_approved_revision_cannot_be_rebound_to_other_content(tmp_path):
    from evonext.contracts.trajectory import sha256
    library = Workshop(tmp_path, "owner")
    saved = save(library)
    bundle = library.export("check-target", saved["revision"])
    snapshot = source()
    request = RuntimeRequest(trial_id="trial", session_id="session", task_id="synthetic",
        snapshot_id=snapshot.id, owner="owner", target=Target(kind="local_device", resource_id="device"),
        context_mode="skill", skills=(bundle,))
    grant = ExecutionGrant(grant_id="grant", trial_id="trial", task_id="synthetic",
        snapshot_id=snapshot.id, owner="owner", target=request.target, max_actions=20,
        expires_at_epoch=100, allow_candidate_skills=True, allowed_skills=(bundle.ref,))
    text = bundle.document + "\nMalicious replacement"
    forged = bundle.model_copy(update={"document": text,
        "ref": bundle.ref.model_copy(update={"content_hash": sha256(text.encode())})})
    forged_request = request.model_copy(update={"skills": (forged,)})
    prepare_trial(forged_request, snapshot)  # Valid bytes alone do not establish approved identity.
    with pytest.raises(PermissionError, match="hash binding"):
        check_grant(forged_request, grant, now=1)


def test_skill_crlf_bytes_remain_verifiable(tmp_path):
    library = Workshop(tmp_path, "owner")
    text = DOCUMENT.replace("\n", "\r\n")
    saved = save(library, text)
    assert library.export("check-target", saved["revision"]).document == text


def test_recovery_raw_context_cannot_read_beyond_anchor():
    snapshot = source()
    request = RuntimeRequest(trial_id="trial", session_id="session", task_id="synthetic",
        snapshot_id=snapshot.id, owner="owner", target=Target(kind="local_device", resource_id="device"),
        context_mode="raw", before_step_position=2,
        recovery=RecoveryRequest(strategy="replay_prefix", reviewed_case_ref="case@1",
            source_step_id="s1", correction_boundary="before_action", expected_state_hash="0" * 64))
    with pytest.raises(ContractError, match="future"):
        prepare_trial(request, snapshot)
