"""One bounded Outcome grading request; source and human decisions stay immutable."""
import base64
import io
from pathlib import Path
from typing import Literal
from uuid import UUID

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator

from evonext.contracts.trajectory import Check, ContractError, EvaluationRecord, encode_json, load_json, sha256
from evonext.providers.policies import freeze_policy

POLICIES = Path(__file__).resolve().parents[3] / "policies/gui"


class Obligation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    check_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")
    requirement: str = Field(min_length=4, max_length=1000)


class OutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    run_id: str
    scope: Literal["initial_instruction_only"]
    snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    obligations: list[Obligation] = Field(min_length=1, max_length=12)
    evidence_positions: list[int] = Field(default_factory=list, max_length=4)
    repetition_id: str = Field(default="0", min_length=1, max_length=64)

    @model_validator(mode="after")
    def identities(self):
        if str(UUID(self.run_id)) != self.run_id or UUID(self.run_id).version != 4:
            raise ValueError("Run ID must be a canonical UUIDv4")
        ids = [item.check_id for item in self.obligations]
        if len(set(ids)) != len(ids) or len(set(self.evidence_positions)) != len(self.evidence_positions):
            raise ValueError("Duplicate obligation or evidence position")
        if any(position < 0 for position in self.evidence_positions):
            raise ValueError("Evidence positions must be non-negative")
        return self


def freeze_input(request, evidence, settings):
    snapshot = evidence.get(request.snapshot_id)
    if snapshot is None:
        raise ContractError("Frozen snapshot not found")
    document = snapshot.document
    images, missing = [], []
    image_bytes = 0
    for position in request.evidence_positions:
        if position >= len(document["traj"]):
            raise ContractError("Evidence step is outside the frozen snapshot")
        step = document["traj"][position]
        locator = step.get("image")
        digest = snapshot.media.get(locator)
        if not digest:
            missing.append({"position": position, "reason": "unbound_before_action_image"})
            continue
        raw = evidence.read_media(snapshot.id, locator)
        if sha256(raw) != digest:
            raise ContractError("Evidence bytes differ from the frozen manifest")
        image_bytes += len(raw)
        if image_bytes > 512 * 1024:
            raise ContractError("Selected images exceed this profile's 512 KiB total delivery limit")
        try:
            with Image.open(io.BytesIO(raw)) as decoded:
                if decoded.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ContractError("Unsupported evaluation image format")
                if decoded.getexif().get(274, 1) != 1:
                    raise ContractError("Explicitly upright evidence images are required")
            with Image.open(io.BytesIO(raw)) as decoded:
                decoded.verify()
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ContractError("Evaluation image cannot be validated") from exc
        images.append({"evidence_id": f"step:{position}:image", "position": position,
                       "media_locator": locator, "sha256": digest, "relation": "before_action"})
    # Source assistant prose, legacy judgments, metadata and Review labels are excluded.
    # This first profile is for goals with no mid-trajectory user amendments.
    amendments = any(step.get("role") == "user" or any(
        key in step for key in ("user_instruction", "user_amendment", "user_message", "messages"))
        for step in document["traj"])
    context = {"instruction": document["instruction"], "images": images, "missing": missing,
               "profile": "outcome.instruction-and-before-images.v1",
               "limitations": ["Selected frames retain before_action timing.",
                              "No dispatched-action history or independent post-action receipt provided.",
                              "Mid-trajectory amendments require a separate supported input profile."]}
    policy = freeze_policy(POLICIES, "outcome", {
        "obligations": [item.model_dump() for item in request.obligations], "evidence": context})
    frozen = {"request": request.model_dump(), "context": context,
              "policy_version": policy.version, "prompt": policy.prompt,
              "max_tokens": policy.config["max_tokens"],
              "model": settings.model_name, "endpoint": settings.model_base_url,
              "amendments_detected": amendments}
    input_view = {**frozen, "request": {
        key: value for key, value in frozen["request"].items()
        if key not in {"run_id", "repetition_id"}}}
    frozen["input_hash"] = sha256(encode_json(input_view))
    return frozen


def result_record(frozen, *, checks=None, execution="completed", error=None, call=None):
    request = frozen["request"]
    checks = checks or [Check(check_id=item["check_id"], judgment="not_assessed",
                            reason=error or "Not assessed")
                        for item in request["obligations"]]
    judgments = [check.judgment for check in checks]
    if execution == "error":
        outcome = "not_assessed"
    elif "fail" in judgments:
        outcome = "failure"
    elif judgments and all(value == "pass" for value in judgments):
        outcome = "success"
    elif all(value == "not_assessed" for value in judgments):
        outcome = "not_assessed"
    else:
        outcome = "unknown"
    return EvaluationRecord(
        record_id=request["run_id"] + ":record:1", snapshot_id=request["snapshot_id"],
        grader_id="evonext.outcome", grader_version="1", execution_status=execution,
        outcome=outcome, checks=checks, trace_id=(call or {}).get("trace_id"),
        native_result={"input_hash": frozen["input_hash"], "policy_version": frozen["policy_version"],
                       "evidence_delivery": frozen["context"]["images"] if call else [],
                       "missing": frozen["context"]["missing"], "error": error,
                       "call_key": (call or {}).get("call_key"),
                       "declared_model": (call or {}).get("declared_model"),
                       "observed_model": (call or {}).get("observed_model"),
                       "usage": (call or {}).get("usage"), "response": (call or {}).get("response"),
                       "reference_policy": "no_prior_judgments",
                       "spec_revision": sha256(encode_json({
                           "policy": frozen["policy_version"], "obligations": request["obligations"],
                           "model": frozen["model"], "endpoint": frozen["endpoint"]})),
                       "request_id": request["run_id"] + ":request:0",
                       "attempt_id": request["run_id"] + ":attempt:0",
                       "agent_trial_id": None, "grading_repeat_index": request["repetition_id"],
                       "attempt_index": 0}).model_dump(mode="json")


def grade(frozen, evidence, gateway):
    """Injected gateway is mandatory; ordinary tests use an explicitly synthetic transport."""
    if frozen["amendments_detected"]:
        return result_record(frozen, error="unsupported_user_amendments")
    if not frozen["context"]["images"]:
        return result_record(frozen, checks=[Check(
            check_id=item["check_id"], judgment="unknown",
            reason="No selected image was available to evaluate the goal")
            for item in frozen["request"]["obligations"]])
    call = None
    try:
        content = [{"type": "text", "text": frozen["prompt"]}]
        for image in frozen["context"]["images"]:
            raw = evidence.read_media(frozen["request"]["snapshot_id"], image["media_locator"])
            if sha256(raw) != image["sha256"]:
                raise ContractError("Evidence readback hash mismatch")
            if len(raw) > 512 * 1024:
                raise ContractError("Selected image exceeds this profile's 512 KiB delivery limit")
            mime = "image/png" if raw.startswith(b"\x89PNG") else (
                "image/jpeg" if raw.startswith(b"\xff\xd8") else "image/webp")
            content.extend([{"type": "text", "text": image["evidence_id"]},
                {"type": "image_url", "image_url": {"url":
                    f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")}}])
        call = gateway.complete([{"role": "user", "content": content}],
            snapshot_id=frozen["request"]["snapshot_id"],
            operation_id="outcome:" + frozen["request"]["run_id"],
            repetition_id=frozen["request"]["repetition_id"],
            policy_version=frozen["policy_version"], max_tokens=frozen["max_tokens"])
        body = call["response"]["choices"][0]["message"]["content"]
        output = load_json(body.encode("utf-8"))
        if set(output) != {"checks"} or not isinstance(output["checks"], list):
            raise ContractError("Expected exactly checks")
        checks = [Check.model_validate(item, strict=True) for item in output["checks"]]
        expected = [item["check_id"] for item in frozen["request"]["obligations"]]
        if len(checks) != len(expected) or {item.check_id for item in checks} != set(expected):
            raise ContractError("Every requested check must appear exactly once")
        delivered = {item["evidence_id"] for item in frozen["context"]["images"]}
        for check in checks:
            if not check.reason.strip() or len(check.reason) > 2000:
                raise ContractError("Each judgment requires a bounded explanation")
            if len(check.evidence_refs) != len(set(check.evidence_refs)):
                raise ContractError("Duplicate evidence citations")
            if not set(check.evidence_refs) <= delivered:
                raise ContractError("Citation was not delivered")
            if check.judgment in {"pass", "fail"} and not check.evidence_refs:
                raise ContractError("Pass/fail requires delivered image evidence")
            if check.judgment == "not_applicable":
                raise ContractError("All obligations in this profile are mandatory")
        checks.sort(key=lambda item: expected.index(item.check_id))
        return result_record(frozen, checks=checks, call=call)
    except Exception as exc:
        # Original response is already durable in ModelGateway before parsing.
        # CallHeld and timeouts remain technical errors, never GUI failures.
        record = result_record(frozen, execution="error", error=type(exc).__name__, call=call)
        if isinstance(exc, ContractError):
            record["native_result"]["error_reason"] = str(exc)
        return record
