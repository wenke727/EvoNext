"""Core evaluation over a complete frozen trajectory, independent of result storage."""

from pydantic import Field

from evonext.contracts.trajectory import Check, ContractError, EvaluationRecord, encode_json, load_json, sha256
from evonext.evaluation.inputs import prepare_input
from evonext.evaluation.images import image_message


class StepFinding(Check):
    position: int | None = Field(default=None, strict=True, ge=0)


def located_errors(findings):
    return [item for item in findings if item.judgment == "fail" and item.position is not None]


def validate_assessment(native, obligations, refs):
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
            if not any(ref.removesuffix("/image").endswith(suffix) for ref in finding.evidence_refs):
                raise ContractError("Located finding requires evidence for its owning step")
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
    policy_hash = sha256(prompt.encode())
    preview = prepare_input(snapshot, request.options)
    if any(type(p) is not int or not 0 <= p < preview["step_count"] for p in request.focus_positions):
        raise ContractError("Investigation focus is outside the frozen trajectory")
    if sum(image["selected"] for image in preview["images"]) > request.max_total_images:
        raise ContractError("Initial images exceed the total image budget")
    if preview["text_budget_exceeded"]:
        raise ContractError("Complete text exceeds budget; adjust input policy before sending")
    refs = {step["evidence_ref"] for step in preview["model_context"]["steps"]}
    content = [{"type": "text", "text": encode_json({
        "obligations": obligations, "trajectory": preview["model_context"]}).decode()}]
    media_receipts = []
    for image in preview["images"]:
        if not image["selected"]:
            continue
        parts, receipt = image_message(snapshot, image, evidence, request.options.markers)
        refs.add(image["evidence_ref"])
        media_receipts.append(receipt)
        content.extend(parts)
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": content}]
    # Mirror the gateway's hard limit before admission, including base64 and prompt overhead.
    if len(encode_json(messages)) > 950 * 1024:
        raise ContractError("Combined image/text request exceeds gateway budget")
    if before_call is not None:
        before_call(messages, "0")
    output = gateway.complete(messages, snapshot_id=snapshot.id, operation_id=request.operation_id,
        max_tokens=4096, policy_version=policy_hash, repetition_id="0")
    native = load_json(output["response"]["choices"][0]["message"]["content"].encode())
    checks, findings, outcome = validate_assessment(native, obligations, refs)
    initial = native
    calls = [output]
    events = []
    stop_reason = "fast_judge_completed"
    should_investigate = request.investigation == "always" or (
        request.investigation == "auto" and (outcome == "unknown" or (outcome == "failure" and not located_errors(findings))))
    if should_investigate:
        from evonext.evaluation.investigator import investigate
        native, calls, events, stop_reason = investigate(
            snapshot, request, evidence, gateway, prompt, preview, messages,
            refs, media_receipts, initial, calls, before_call)
        checks, findings, outcome = validate_assessment(native, obligations, refs)
    record = EvaluationRecord(record_id=record_id, snapshot_id=snapshot.id,
        grader_id="fast_judge_investigator" if len(calls) > 1 else "fast_judge",
        grader_version=policy_hash, execution_status="completed",
        outcome=outcome, checks=checks, trace_id=output["trace_id"], native_result={
            "findings": [finding.model_dump() for finding in findings],
            "error_localization": "located" if located_errors(findings) else "undetermined",
            "process_coverage": "not_exhaustive", "call_key": output["call_key"],
            "initial_assessment": initial, "investigation_events": events,
            "calls": [{key: call[key] for key in ("call_key", "declared_model", "observed_model", "usage", "trace_id")} for call in calls],
            "declared_model": output["declared_model"], "observed_model": output["observed_model"],
            "usage": output["usage"], "usage_scope": "fast_judge_only",
            "cost": None, "delivered_evidence_refs": sorted(refs),
            "media_receipts": media_receipts, "input_context_sha256": preview["context_sha256"],
            "stop_reason": stop_reason}).model_dump(mode="json")
    return record
