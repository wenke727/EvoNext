#!/usr/bin/env python3
"""Generate *synthetic*, internally linked Flywheel contract fixtures.

Never uses production data, provider calls, or real screenshots. Deterministic.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
EVIDENCE.mkdir(exist_ok=True)


def jdump(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def sha_bytes(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def dump(name, obj):
    path = HERE / name
    data = jdump(obj)
    path.write_bytes(data)
    return sha_bytes(data)


content = {
    "step_0_before.txt": "SYNTHETIC OBSERVATION. Auto brightness = OFF. BEFORE tap. NOT A SCREENSHOT.\n",
    "step_0_dispatch.txt": "SYNTHETIC EXECUTION RECEIPT. dispatched tap(toggle_auto_brightness); transport_ack=true. Does NOT establish effect.\n",
    "step_1_after.txt": "SYNTHETIC OBSERVATION. Auto brightness = OFF. AFTER dispatched tap. No effect observed. NOT A SCREENSHOT.\n",
}
hashes = {}
for name, value in content.items():
    data = value.encode("utf-8")
    (EVIDENCE / name).write_bytes(data)
    hashes[name] = sha_bytes(data)

SOURCE_ID = "202611061840001234567890"
SOURCE_REV = "source-r1"
TRIAL = "trial-original-01"
TASK_REV = "task-rev-1"
CASE = "case-001"
REVIEW = "review-001-r1"
REC = "record-001"

raw = {
    "schema_version": "rollout.synthetic.v1",
    "synthetic": True,
    "source_system": "rollout-synthetic",
    "source_key": "batch-001/trial-001",
    "source_revision": SOURCE_REV,
    "task_id": SOURCE_ID,
    "trajectory_id": "traj-001",
    "agent_trial_id": TRIAL,
    "instruction": "在设置中开启自动亮度",
    "task_contract": {
        "contract_revision": "goal-contract-r1",
        "obligations": [
            {"check_id": "action.tap_dispatched", "criterion": "确实派发了开关点击动作"},
            {"check_id": "goal.mode_on", "criterion": "自动亮度最终为开启"},
        ],
        "negative_constraints": [],
        "completion_boundary": "自动亮度开启后结束",
    },
    "steps": [
        {
            "step_id": "step-A",
            "source_ordinal": 0,
            "observation_before_ref": "evidence/step_0_before.txt",
            "proposed_action": {"action_id": "tap-01", "kind": "tap", "target": "auto_brightness_toggle"},
            "dispatched_action": {"action_id": "tap-01", "kind": "tap", "target": "auto_brightness_toggle"},
            "execution_receipt_ref": "evidence/step_0_dispatch.txt",
            "observation_after_ref": "evidence/step_1_after.txt",
        },
        {
            "step_id": "step-Z",
            "source_ordinal": 1,
            "observation_before_ref": "evidence/step_1_after.txt",
            "proposed_action": None,
            "dispatched_action": None,
            "terminal_reason": "agent_declared_done",
        },
    ],
}
raw_hash = dump("source_rollout.synthetic.v1.json", raw)

source_binding = {
    "source_system": raw["source_system"],
    "source_key": raw["source_key"],
    "source_revision": SOURCE_REV,
    "source_content_hash": raw_hash,
    "task_id": SOURCE_ID,
    "trajectory_id": raw["trajectory_id"],
    "agent_trial_id": TRIAL,
    "raw_payload_ref": "source_rollout.synthetic.v1.json",
}

receipts = {
    "schema_version": "ingestion_receipt.synthetic.v1",
    "synthetic": True,
    "job_id": "import-001",
    "requested_items": 1,
    "idempotency_key": "synthetic-import-001",
    "status": "succeeded",
    "source_binding": source_binding,
    "items": [
        {
            "item_id": "item-001",
            "status": "succeeded",
            "task_revision_id": "task-rev-0",
            "source_content_hash": raw_hash,
        }
    ],
    "counters": {"requested": 1, "succeeded": 1, "failed": 0, "cancelled": 0, "pending": 0},
}
dump("ingestion_receipt.synthetic.v1.json", receipts)

evidence = [
    {
        "evidence_id": "ev-before",
        "kind": "text_observation",
        "step_id": "step-A",
        "frame_relation": "before_action",
        "action_id": "tap-01",
        "object_ref": "evidence/step_0_before.txt",
        "content_hash": hashes["step_0_before.txt"],
        "available": True,
    },
    {
        "evidence_id": "ev-dispatch",
        "kind": "execution_receipt",
        "step_id": "step-A",
        "action_id": "tap-01",
        "object_ref": "evidence/step_0_dispatch.txt",
        "content_hash": hashes["step_0_dispatch.txt"],
        "available": True,
    },
    {
        "evidence_id": "ev-after",
        "kind": "text_observation",
        "step_id": "step-Z",
        "frame_relation": "after_action",
        "action_id": "tap-01",
        "object_ref": "evidence/step_1_after.txt",
        "content_hash": hashes["step_1_after.txt"],
        "available": True,
    },
    {
        "evidence_id": "ev-image-not-present",
        "kind": "image",
        "step_id": "step-A",
        "frame_relation": "before_action",
        "action_id": "tap-01",
        "object_ref": None,
        "content_hash": None,
        "available": False,
        "reason": "synthetic_missing_media",
    },
]

task = {
    "schema_version": "task_revision.synthetic.v1",
    "synthetic": True,
    "task_id": SOURCE_ID,
    "trajectory_id": "traj-001",
    "revision_id": TASK_REV,
    "parent_revision_id": "task-rev-0",
    "revision_kind": "derived_patch",
    "review_status": "unreviewed",
    "review_authority_ref": None,
    "source_binding": source_binding,
    "instruction": raw["instruction"],
    "task_contract": raw["task_contract"],
    "step_ids_in_source_order": ["step-A", "step-Z"],
    "evidence_manifest": evidence,
    "evidence_manifest_hash": sha_bytes(jdump(evidence)),
    "raw_task_revision_id": "task-rev-0",
}
dump("task_revision.synthetic.v1.json", task)

review_case = {
    "schema_version": "review_case.synthetic.v1",
    "synthetic": True,
    "review": {
        "review_revision_id": REVIEW,
        "review_id": "review-001",
        "task_revision_id": TASK_REV,
        "reviewer_id": "synthetic-reviewer",
        "decision": "approved",
        "finding": "点击回执存在，但后态显示自动亮度仍关闭",
        "evidence_refs": ["ev-dispatch", "ev-after"],
        "rubric_revision": "human-review-r1",
    },
    "case": {
        "case_id": CASE,
        "locator": {
            "locator_revision": 1,
            "task_revision_id": TASK_REV,
            "step_ids": ["step-A", "step-Z"],
            "module_key": "gui_executor",
        },
        "review_revision_ref": REVIEW,
        "memberships": [{"pool": "bad_case", "purpose": "diagnostic", "decision_ref": REVIEW}],
        "failure_lifecycle": {
            "state": "reviewed",
            "root_cause_locus": "unknown",
            "intervention_route": "unknown",
            "unknowns": ["无法仅从 ack+后态确认是坐标偏移、点击无效还是 UI 延时"],
        },
    },
}
dump("review_case.synthetic.v1.json", review_case)

record = {
    "schema_version": "evaluation_run.synthetic.v1",
    "synthetic": True,
    "run": {
        "run_id": "run-001",
        "dataset_revision_id": "dataset-snapshot-001-r1",
        "spec_revision_id": "spec-outcome-r1",
        "status": "completed",
        "publication_mode": "none",
        "input_task_revision_id": TASK_REV,
        "frozen_source_content_hash": raw_hash,
        "evidence_manifest_hash": task["evidence_manifest_hash"],
    },
    "request": {
        "request_id": "request-001",
        "attempt_id": "attempt-001",
        "grader_binding_id": "outcome-trajectory-retrospective-r1",
        "requested_check_ids": ["action.tap_dispatched", "goal.mode_on"],
        "grading_repeat_index": 0,
        "agent_trial_id": TRIAL,
    },
    "record": {
        "record_id": REC,
        "source_task_revision_id": TASK_REV,
        "execution_status": "completed",
        "outcome_status": "failure",
        "native_result": {"format_id": "task_outcome.synthetic.v1", "label": "failed", "outcome_mapping_revision": "outcome-map-r1"},
        "checks": [
            {"check_id": "action.tap_dispatched", "judgment": "pass", "reason_code": "receipt_observed", "evidence_refs": ["ev-dispatch"]},
            {"check_id": "goal.mode_on", "judgment": "fail", "reason_code": "observed_unmet_obligation", "evidence_refs": ["ev-after"]},
        ],
        "coverage": {"requested": 2, "pass": 1, "fail": 1, "unknown": 0, "not_applicable": 0, "not_assessed": 0},
        "grader_kind": "deterministic_code",
        "evidence_delivery_receipt": {
            "read_by_deterministic_grader": ["ev-before", "ev-dispatch", "ev-after"],
            "delivered_to_model": [],
            "unavailable": ["ev-image-not-present"],
            "note": "Contract fixture for a code grader. No model call or image delivery occurred.",
        },
        "usage": {"provider_calls": 0, "known_cost": 0, "synthetic": True},
    },
}
dump("evaluation_run.synthetic.v1.json", record)

snapshot = {
    "schema_version": "dataset_snapshot.synthetic.v1",
    "synthetic": True,
    "dataset_id": "dataset-001",
    "dataset_revision_id": "dataset-snapshot-001-r1",
    "sealed": True,
    "purpose": "diagnostic",
    "source_policy_revision": "diagnostic-admission-r1",
    "members": [
        {
            "item_id": "item-001",
            "task_id": SOURCE_ID,
            "task_revision_id": TASK_REV,
            "source_content_hash": raw_hash,
            "review_revision_id": REVIEW,
            "case_id": CASE,
            "agent_trial_id": TRIAL,
            "family_id": "synthetic-family-001",
            "split": "diagnostic",
            "contamination_status": "unchecked",
            "formal_train_admitted": False,
            "admission_reason": "diagnostic_only_and_contamination_unchecked",
        }
    ],
}
snapshot["membership_manifest_hash"] = sha_bytes(jdump(snapshot["members"]))
dump("dataset_snapshot.synthetic.v1.json", snapshot)

handoff = {
    "schema_version": "intervention_handoff.synthetic.v1",
    "synthetic": True,
    "handoff_id": "handoff-001",
    "case_id": CASE,
    "review_revision_id": REVIEW,
    "task_revision_id": TASK_REV,
    "evaluation_record_id": REC,
    "intervention_route": "unknown",
    "request_owner": "skill-workshop",
    "request": "请根据当前证据判断是否存在可复用的流程经验缺口",
    "response": {
        "status": "needs_evidence",
        "reason": "尚未证明是 skill 知识缺口；应先确定点击无效的因果路径",
        "candidate_ref": None,
        "trial_id": None,
    },
    "authorized_execution": False,
}
dump("intervention_handoff.synthetic.v1.json", handoff)

matrix_verdicts = ["pass", "pass", "pass", "fail", "fail", "unknown", "unknown", "not_applicable", "not_assessed", "not_assessed", "not_assessed", "not_assessed"]
matrix = {
    "schema_version": "evaluation_matrix.synthetic.v1",
    "synthetic": True,
    "requested": 12,
    "items": [
        {"request_id": f"matrix-{i:02d}", "check_id": "demo.check", "judgment": status, "reason_code": "synthetic_fixture"}
        for i, status in enumerate(matrix_verdicts, start=1)
    ],
    "counts": {label: matrix_verdicts.count(label) for label in ["pass", "fail", "unknown", "not_applicable", "not_assessed"]},
}
dump("evaluation_matrix.synthetic.v1.json", matrix)

# Oracle is external test-only. It must never go to model input or candidate generation.
oracle = {
    "schema_version": "hidden_oracle.synthetic.v1",
    "synthetic": True,
    "source_task_id": SOURCE_ID,
    "source_task_revision_id": TASK_REV,
    "gold_authority": "synthetic_test_oracle_not_human_gold",
    "expected_business_outcome": "failure",
    "expected_checks": {"action.tap_dispatched": "pass", "goal.mode_on": "fail"},
    "do_not_include_in_model_input": True,
}
dump("hidden_oracle.DO_NOT_SEND_TO_MODEL.json", oracle)

print("Generated 9 JSON fixtures, 3 evidence files. All identities and hashes are synthetic.")
