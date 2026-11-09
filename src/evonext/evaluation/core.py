"""Core evaluation over a complete frozen trajectory, independent of result storage."""

from pydantic import Field

from evonext.contracts.trajectory import Check, ContractError, EvaluationRecord, encode_json, load_json, sha256
from evonext.evaluation.inputs import prepare_input
from evonext.evaluation.images import image_message


class StepFinding(Check):
    position: int | None = Field(default=None, strict=True, ge=0)
    decision_ref: str | None = Field(default=None, strict=True)


def located_errors(findings):
    return [item for item in findings if item.judgment == "fail" and item.position is not None]


def validate_assessment(native, obligations, refs, bind_decisions=False):
    if set(native) != {"checks", "findings"}:
        raise ContractError("Judge must return checks and findings")
    checks = [Check.model_validate(item) for item in native["checks"]]
    findings = [StepFinding.model_validate(item) for item in native["findings"]]
    if len(checks) != len(obligations) or {c.check_id for c in checks} != set(obligations):
        raise ContractError("Judge obligation coverage mismatch")
    for check in checks + findings:
        if not set(check.evidence_refs) <= refs:
            raise ContractError("Judge cited evidence outside the delivered input")
        if check.judgment in {"pass", "fail"} and not check.evidence_refs:
            raise ContractError("A definite judgment requires delivered evidence")
    for finding in findings:
        if finding.position is not None:
            suffix = f"/steps/{finding.position}"
            if not any(ref.removesuffix("/image").endswith(suffix) or suffix + "/facts/" in ref
                       for ref in finding.evidence_refs):
                raise ContractError("Located finding requires evidence for its owning step")
        if finding.decision_ref is not None:
            if finding.position is None:
                raise ContractError("An unlocated finding must omit decision_ref; cite observations in evidence_refs")
            suffix = f"/steps/{finding.position}/facts/"
            if (finding.position is None or finding.decision_ref not in refs
                or finding.decision_ref not in finding.evidence_refs
                or suffix not in finding.decision_ref
                or finding.decision_ref.rsplit("/", 1)[-1] not in {
                    "tool_call", "action", "dispatch", "dispatched_action", "think", "thought"}):
                raise ContractError("Decision reference must cite a delivered field of its owning step")
        if bind_decisions and finding.judgment == "fail" and finding.position is not None and finding.decision_ref is None:
            raise ContractError("A bound located error requires an explicit source decision_ref")
    outcome = "unknown"
    if any(check.judgment == "fail" for check in checks):
        outcome = "failure"
    elif checks and all(check.judgment == "pass" for check in checks):
        outcome = "success"
    return checks, findings, outcome


def evaluate(snapshot, request, evidence, gateway, prompt, record_id, before_call=None):
    obligations = request.obligations or {"task_goal": snapshot.document["instruction"]}
    if any(not key.strip() or not value.strip() for key, value in obligations.items()):
        raise ContractError("Obligation IDs and descriptions must be nonempty")
    preview = prepare_input(snapshot, request.options)
    if any(type(p) is not int or not 0 <= p < preview["step_count"] for p in request.focus_positions):
        raise ContractError("Investigation focus is outside the frozen trajectory")
    if sum(image["selected"] for image in preview["images"]) > request.max_total_images:
        raise ContractError("Initial images exceed the total image budget")
    if preview["text_budget_exceeded"]:
        raise ContractError("Complete text exceeds budget; adjust input policy before sending")
    refs = {step["evidence_ref"] for step in preview["model_context"]["steps"]}
    refs.update(ref for step in preview["model_context"]["steps"]
                for container in step["fact_refs"].values() for ref in container.values())
    refs.add(preview["model_context"]["source_context"]["evidence_ref"])
    content = [{"type": "text", "text": encode_json({
        "obligations": obligations, "trajectory": preview["model_context"]}).decode()}]
    media_receipts = []
    for image in preview["images"]:
        if not image["selected"]:
            continue
        parts, receipt = image_message(snapshot, image, evidence, request.options.markers,
                                       request.options.runtime_coordinate_profile)
        refs.add(image["evidence_ref"])
        media_receipts.append(receipt)
        content.extend(parts)
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": content}]
    if request.bind_decisions:
        messages[0]["content"] += (
            "\nFor every located fail finding, include decision_ref and cite that exact delivered "
            "fact_refs field in evidence_refs. Bind the faulty recorded decision, not only its "
            "later outcome. When position is null, omit decision_ref and use evidence_refs "
            "for supporting observations. Do not assign a position merely to satisfy this schema. Bind "
            "the original field rather than an assistant paraphrase. Compare proposed and dispatched actions; "
            "a rejected/retry proposal is not a delivered answer. Retain uncertain proposal issues "
            "as unknown when adoption is unproved. Inspect the earliest recorded decision that "
            "relies on an unsupported absence or unmet precondition, including an initial "
            "handoff before a later repeated termination. Missing a named control does not "
            "prove a function is disabled; keep visible selected state and unknown state distinct."
        )
    prompt = messages[0]["content"]
    policy_hash = sha256(prompt.encode())
    # Mirror the gateway's hard limit before admission, including base64 and prompt overhead.
    if len(encode_json(messages)) > request.max_request_bytes:
        raise ContractError("Combined image/text request exceeds gateway budget")
    if before_call is not None:
        before_call(messages, "0")
    output = gateway.complete(messages, snapshot_id=snapshot.id, operation_id=request.operation_id,
        max_tokens=4096, policy_version=policy_hash, repetition_id="0")
    native = load_json(output["response"]["choices"][0]["message"]["content"].encode())
    initial_validation_error = None
    try:
        checks, findings, outcome = validate_assessment(native, obligations, refs, request.bind_decisions)
    except (ValueError, ContractError) as exc:
        if not request.review_localization or request.investigation == "off" or not request.max_investigation_calls:
            raise
        initial_validation_error = str(exc)
        checks, findings, outcome = [], [], "unknown"
    initial = native
    calls = [output]
    events = []
    stop_reason = "fast_judge_completed"
    should_investigate = request.investigation == "always" or (
        request.investigation == "auto" and (outcome == "unknown" or (outcome == "failure" and not located_errors(findings))))
    if request.review_localization and request.investigation == "auto":
        # Task success does not settle an explicitly reported process uncertainty.
        if any(item.judgment == "unknown" or
               (item.judgment == "fail" and item.position is None) for item in findings):
            should_investigate = True
        located = located_errors(findings)
        if located:
            earliest = min(item.position for item in located)
            if any(image["position"] <= earliest and image["evidence_ref"] not in refs
                   for image in preview["images"]):
                should_investigate = True
    if should_investigate:
        from evonext.evaluation.investigator import investigate
        native, calls, events, stop_reason = investigate(
            snapshot, request, evidence, gateway, prompt, preview, messages,
            refs, media_receipts, initial, calls, before_call, initial_validation_error)
        checks, findings, outcome = validate_assessment(native, obligations, refs, request.bind_decisions)
    record = EvaluationRecord(record_id=record_id, snapshot_id=snapshot.id,
        grader_id="fast_judge_investigator" if len(calls) > 1 else "fast_judge",
        grader_version=policy_hash, execution_status="completed",
        outcome=outcome, checks=checks, trace_id=output["trace_id"], native_result={
            "findings": [{key: value for key, value in finding.model_dump().items()
                          if key != "decision_ref" or value is not None} for finding in findings],
            "error_localization": "located" if located_errors(findings) else "undetermined",
            "process_coverage": "not_exhaustive", "call_key": output["call_key"],
            "initial_assessment": initial, "investigation_events": events,
            "initial_validation_error": initial_validation_error,
            "calls": [{key: call[key] for key in ("call_key", "declared_model", "observed_model", "usage", "trace_id")} for call in calls],
            "declared_model": output["declared_model"], "observed_model": output["observed_model"],
            "usage": output["usage"], "usage_scope": "fast_judge_only",
            "input_profile": preview["profile"],
            "localization_review_requested": request.review_localization,
            "decisions_bound": request.bind_decisions,
            "cost": None, "delivered_evidence_refs": sorted(refs),
            "media_receipts": media_receipts, "input_context_sha256": preview["context_sha256"],
            "stop_reason": stop_reason}).model_dump(mode="json")
    return record
