#!/usr/bin/env python3
"""Structural/identity/provenance checks for synthetic contract fixtures.

Not a substitute for JSON Schema, integration, browser, or semantic evaluation.
"""
import hashlib
import json
from pathlib import Path
from collections import Counter

D = Path(__file__).resolve().parent


def load(filename):
    return json.loads((D / filename).read_text(encoding="utf-8"))


def hash_file(filename):
    return "sha256:" + hashlib.sha256((D / filename).read_bytes()).hexdigest()


def canonical_hash(obj):
    data = (json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


source = load("source_rollout.synthetic.v1.json")
receipt = load("ingestion_receipt.synthetic.v1.json")
task = load("task_revision.synthetic.v1.json")
case = load("review_case.synthetic.v1.json")
eval_run = load("evaluation_run.synthetic.v1.json")
dataset = load("dataset_snapshot.synthetic.v1.json")
handoff = load("intervention_handoff.synthetic.v1.json")
matrix = load("evaluation_matrix.synthetic.v1.json")
oracle = load("hidden_oracle.DO_NOT_SEND_TO_MODEL.json")

assert source["synthetic"] and oracle["gold_authority"] == "synthetic_test_oracle_not_human_gold"
assert isinstance(source["task_id"], str) and len(source["task_id"]) > 16
assert source["task_id"] == task["task_id"] == dataset["members"][0]["task_id"]
assert source["source_key"] == task["source_binding"]["source_key"]
assert receipt["source_binding"] == task["source_binding"]
assert receipt["source_binding"]["source_content_hash"] == hash_file("source_rollout.synthetic.v1.json")
assert task["source_binding"]["source_content_hash"] == eval_run["run"]["frozen_source_content_hash"]
assert task["revision_id"] == case["review"]["task_revision_id"] == case["case"]["locator"]["task_revision_id"]
assert task["revision_id"] == eval_run["run"]["input_task_revision_id"]
assert task["revision_kind"] == "derived_patch" and task["review_status"] == "unreviewed"
assert case["review"]["decision"] == "approved"  # Independent review record, not TaskRevision's version number
assert case["case"]["case_id"] == dataset["members"][0]["case_id"] == handoff["case_id"]
assert case["review"]["review_revision_id"] == dataset["members"][0]["review_revision_id"] == handoff["review_revision_id"]
assert eval_run["record"]["record_id"] == handoff["evaluation_record_id"]
assert eval_run["request"]["agent_trial_id"] == source["agent_trial_id"]
assert dataset["dataset_revision_id"] == eval_run["run"]["dataset_revision_id"]
assert task["evidence_manifest_hash"] == canonical_hash(task["evidence_manifest"])
for ev in task["evidence_manifest"]:
    if ev["available"]:
        assert ev["content_hash"] == hash_file(ev["object_ref"]), ev
    else:
        assert ev["content_hash"] is None and ev["object_ref"] is None, ev

assert dataset["sealed"] and dataset["membership_manifest_hash"] == canonical_hash(dataset["members"])
assert dataset["members"][0]["contamination_status"] == "unchecked"
assert not dataset["members"][0]["formal_train_admitted"]

requested = eval_run["request"]["requested_check_ids"]
checks = eval_run["record"]["checks"]
assert set(requested) == {x["check_id"] for x in checks} and len(requested) == len(checks)
counts = Counter(x["judgment"] for x in checks)
coverage = eval_run["record"]["coverage"]
assert coverage["requested"] == len(checks)
for label in ["pass", "fail", "unknown", "not_applicable", "not_assessed"]:
    assert coverage[label] == counts[label]
assert eval_run["record"]["outcome_status"] == oracle["expected_business_outcome"]
assert {x["check_id"]: x["judgment"] for x in checks} == oracle["expected_checks"]
assert eval_run["record"]["usage"]["provider_calls"] == 0  # deterministic fixture, no model call
assert not eval_run["record"]["evidence_delivery_receipt"]["delivered_to_model"]
assert handoff["response"]["status"] == "needs_evidence" and handoff["response"]["candidate_ref"] is None
assert not handoff["authorized_execution"]

assert matrix["requested"] == len(matrix["items"])
assert matrix["requested"] == sum(matrix["counts"].values()) == 12
assert matrix["counts"] == dict(Counter(x["judgment"] for x in matrix["items"]))

# Ensure no hidden Gold marker/field slipped into the raw model-visible payload.
raw_model_input = (D / "source_rollout.synthetic.v1.json").read_text(encoding="utf-8")
for disallowed in ("expected_business_outcome", "gold_authority", "synthetic_test_oracle_not_human_gold"):
    assert disallowed not in raw_model_input

print("PASS: 9 JSON fixtures; hashes, identities, review/version separation, evidence refs, coverage, sealed snapshot, no-Gold raw payload")
