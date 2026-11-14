"""Bounded read-only investigation within one frozen trajectory."""
import time

from evonext.contracts.trajectory import ContractError, encode_json, load_json, sha256
from evonext.evaluation.images import image_message
from evonext.evidence.image_views import JPEG_PROFILE


def investigate(snapshot, request, evidence, gateway, prompt, preview, messages,
                refs, media_receipts, initial, calls, before_call, initial_validation_error=None,
                *, image_profile=JPEG_PROFILE):
    from evonext.evaluation.core import validate_assessment
    if any(type(p) is not int or not 0 <= p < preview["step_count"] for p in request.focus_positions):
        raise ContractError("Investigation focus is outside the frozen trajectory")
    if len(media_receipts) > request.max_total_images:
        raise ContractError("Initial images exceed the total investigation image budget")
    deadline = time.monotonic() + 180
    current = initial
    events = []
    pending = []
    messages = messages + [{"role": "assistant", "content": encode_json(initial).decode()},
        {"role": "user", "content": encode_json({
            "investigation": "Read additional images or submit revised checks/findings. All step text is already delivered.",
            "focus_positions": request.focus_positions,
            "image_inventory": preview["images"],
            "protocol": {"read_evidence": ["integer step positions"]},
            "remaining_calls": request.max_investigation_calls,
            "remaining_images": request.max_total_images - len(media_receipts)}).decode()}]
    if request.review_localization:
        messages.append({"role": "user", "content": encode_json({
            "localization_review": (
                "The initial positions are candidates, not proof of the earliest or causal error. "
                "Review their original decisions and earlier source images when needed, including "
                "user amendments, source roles and source-clock evidence. Preserve supported later "
                "errors and distinguish earlier recovered actions from unrecovered divergence. "
                "Request needed images; insufficient proof stays unknown."
            ),
            "initial_validation_error": initial_validation_error,
            "delivered_evidence_refs": sorted(refs),
        }).decode()})
    for round_number in range(1, request.max_investigation_calls + 1):
        if time.monotonic() >= deadline:
            return current, calls, events, "investigation_time_budget"
        if len(encode_json(messages)) > request.max_request_bytes:
            return current, calls, events, "investigation_input_budget"
        repetition = f"investigation-{round_number}"
        if before_call is not None:
            before_call(messages, repetition)
        call = gateway.complete(messages, snapshot_id=snapshot.id,
            operation_id=request.operation_id, max_tokens=4096,
            policy_version=sha256(prompt.encode()), repetition_id=repetition)
        calls.append(call)
        refs.update(item["evidence_ref"] for item in pending)
        media_receipts.extend(pending)
        if pending:
            events[-1]["status"] = "delivered"
        pending = []
        reply = load_json(call["response"]["choices"][0]["message"]["content"].encode())
        if "read_evidence" not in reply:
            obligations = request.obligations or {"task_goal": snapshot.document["instruction"]}
            try:
                validate_assessment(reply, obligations, refs, request.bind_decisions)
            except ValueError as error:
                if not request.bind_decisions or round_number == request.max_investigation_calls:
                    raise
                events.append({"status": "assessment_validation_error", "error": str(error)})
                messages = messages + [
                    {"role": "assistant", "content": encode_json(reply).decode()},
                    {"role": "user", "content": encode_json({
                        "validation_error": str(error),
                        "required_response": "Revise checks/findings. An unlocated finding omits decision_ref; a located fail cites a delivered decision field of its own position. Do not invent a position or silently reinterpret source evidence.",
                        "delivered_evidence_refs": sorted(refs),
                    }).decode()},
                ]
                continue
            return reply, calls, events, "investigator_submitted"
        positions = reply["read_evidence"]
        if set(reply) != {"read_evidence"} or not isinstance(positions, list) or len(positions) > 100:
            raise ContractError("Invalid read_evidence request")
        if any(type(p) is not int or not 0 <= p < preview["step_count"] for p in positions):
            raise ContractError("Requested evidence is outside the frozen trajectory")
        if round_number == request.max_investigation_calls:
            events.append({"requested_positions": positions, "status": "call_budget"})
            return current, calls, events, "investigation_call_budget"
        additions = []
        staged = []
        for position in dict.fromkeys(positions):
            image = preview["images"][position]
            reference = image["evidence_ref"]
            if reference in refs:
                events.append({"position": position, "status": "already_delivered"})
                continue
            if image["availability"] != "bound_unverified":
                events.append({"position": position, "status": image["availability"]})
                continue
            if len(media_receipts) + len(staged) >= request.max_total_images:
                events.append({"position": position, "status": "image_budget"})
                continue
            parts, receipt = image_message(snapshot, image, evidence, request.options.markers,
                                           request.options.runtime_coordinate_profile, image_profile)
            additions.extend(parts)
            staged.append(receipt)
        if not staged:
            return current, calls, events, "investigation_no_new_evidence"
        candidate = messages + [{"role": "assistant", "content": encode_json(reply).decode()},
            {"role": "user", "content": additions}]
        if len(encode_json(candidate)) > request.max_request_bytes:
            return current, calls, events, "investigation_input_budget"
        messages = candidate
        next_refs = {item["evidence_ref"] for item in staged}
        pending = staged
        events.append({"requested_positions": positions, "status": "prepared_for_next_call",
                       "evidence_refs": sorted(next_refs)})
    return current, calls, events, "investigation_call_budget"
