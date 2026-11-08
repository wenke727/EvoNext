"""Read-only, version-pinned eligibility previews. Not admission or publication."""
from evonext.contracts.trajectory import sha256, encode_json

POLICY = "review-use-preview.v1"
PURPOSES = ("diagnosis", "localization", "sft", "dpo")


def preview_case_use(case: dict, review: dict, snapshot, purpose: str):
    if purpose not in PURPOSES:
        raise ValueError("Unsupported use preview")
    items = (review.get("frozen_draft") or {}).get("items") or []
    accepted = [item for item in items if item["verdict"] == "accepted"]
    note = (review.get("frozen_draft") or {}).get("note", "")
    missing, blocked = [], []
    candidates = []
    if review["decision"] != "confirmed":
        missing.append("operator_confirmed_review")
    if purpose == "diagnosis":
        if not case["evidence_refs"]:
            missing.append("frozen_case_evidence")
        # A later recovery/action correction is valuable even when first error is unknown.
        candidates = [{"summary": case["summary"], "evidence_refs": case["evidence_refs"],
                       "correction_item_ids": [i["item_id"] for i in accepted],
                       "first_error_claim": "unknown"}]
    elif purpose == "localization":
        candidates = [{
            "item_id": i["item_id"], "position": i["position"],
            "regions": i["regions"],
            "suggested_action": i["suggested_action"],
        } for i in accepted if i["regions"]]
        if not candidates:
            missing.append("accepted_normalized_bbox_or_target_region")
        # This does not declare a formal regression Gold or a unique correct point.
        missing.append("independent_regression_admission")
    else:
        train_flag = snapshot.metadata.get("do_not_train")
        if train_flag is True:
            blocked.append("do_not_train_source")
        elif train_flag is not False:
            missing.append("trainability_authority_unknown")
        if case["issue_kind"] in {"environment", "tool_execution"}:
            blocked.append("non_actor_failure_requires_specialist_review")
        clicks = [i for i in accepted if i["kind"] == "action_correction" and
                  i["suggested_action"] is not None]
        candidates = [{
            "item_id": i["item_id"], "position": i["position"],
            "suggested_action": i["suggested_action"],
            "source_action_stage": i["source_action_stage"],
        } for i in clicks]
        if not clicks:
            missing.append("accepted_complete_click_action")
        # A visible screenshot is not proof of the historical model-visible input.
        missing.extend(["actor_ex_ante_input_receipt", "independent_usage_admission"])
        if purpose == "dpo":
            missing.extend(["two_distinct_actor_outputs", "explicit_preference_on_same_input",
                            "original_output_and_negative_evidence"])
            if clicks and all(i["source_action_stage"] == "runtime_dispatch" for i in clicks):
                blocked.append("executor_failure_not_actor_negative")
    if blocked:
        status = "blocked"
    elif missing:
        status = "needs_evidence"
    else:
        status = "ready_for_preview"
    # diagnosis can preview a confirmed problem even without a correction candidate.
    if purpose == "diagnosis" and review["decision"] == "confirmed" and case["evidence_refs"]:
        status = "ready_for_preview"
    if review["decision"] == "rejected":
        status = "not_applicable"
    return {
        "schema_version": "evonext.review-use-preview.v1",
        "policy_version": POLICY,
        "case_id": case["case_id"],
        "snapshot_id": case["snapshot_id"],
        "review_revision": review["revision"],
        "review_input_hash": review["review_input_hash"],
        "purpose": purpose,
        "status": status,
        "missing": list(dict.fromkeys(missing)),
        "blocked": list(dict.fromkeys(blocked)),
        "candidate": {
            "case_scope": case["scope"],
            "issue_kind": case["issue_kind"],
            "operator_note": note,
            "accepted_items": candidates,
        },
        "publication_authorized": False,
        "new_trial_executed": False,
        "preview_id": sha256(encode_json({
            "case": case["case_id"], "revision": review["revision"],
            "policy": POLICY, "purpose": purpose,
            "source": case["snapshot_id"], "source_trainability": snapshot.metadata.get("do_not_train"),
        })),
    }
