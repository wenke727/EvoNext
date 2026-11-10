"""Explicit, bounded author/reviewer loop on the existing gateway and PG ledger."""
import base64
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from evonext.contracts.trajectory import ContractError, encode_json, load_json, sha256
from evonext.evidence.packages import media_type
from evonext.skills.workshop.authoring import diet, validate_files
from evonext.skills.workshop.drafts import Drafts


class SourceWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    snapshot_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    positions: list[int] = Field(min_length=1, max_length=12)


class CaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    case_id: str
    revision: int = Field(ge=1)


class AuthorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation_id: str = Field(min_length=1, max_length=100)
    skill_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    base_revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    mode: Literal["learn", "diet"] = "learn"
    sources: list[SourceWindow] = Field(min_length=1, max_length=4)
    cases: list[CaseInput] = Field(default_factory=list, max_length=4)
    instruction: str = Field(min_length=1, max_length=4000)
    include_images: bool = False


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    decision: Literal["propose", "no_change", "needs_evidence"]
    reason: str = Field(min_length=1, max_length=4000)
    files: dict[str, str] = Field(default_factory=dict, max_length=51)
    headings: list[str] = Field(default_factory=list, max_length=20)


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    verdict: Literal["approved", "rejected", "needs_evidence"]
    notes: str = Field(min_length=1, max_length=8000)
    evidence_refs: list[str] = Field(max_length=48)


def keys(operation_id):
    return "workshop-" + sha256(operation_id.encode())


def source_input(request, evidence):
    rows, images = [], []
    for window in request.sources:
        snapshot = evidence.get(window.snapshot_id)
        if snapshot is None:
            raise ContractError("Workshop source snapshot is unavailable")
        for position in sorted(set(window.positions)):
            if not 0 <= position < len(snapshot.document["traj"]):
                raise ContractError("Source position is outside the frozen trajectory")
            step = snapshot.document["traj"][position]
            reference = f"{snapshot.id}:{position}"
            locator = step.get("image")
            delivered = request.include_images and locator in snapshot.media
            rows.append({"ref": reference, "instruction": snapshot.document["instruction"],
                         "step": step, "image_attached_to_input": delivered})
            if delivered:
                if len(images) // 2 >= 4:
                    raise ContractError("Select at most four bound screenshots per authoring request")
                raw = evidence.read_media(snapshot.id, locator)
                if sha256(raw) != snapshot.media[locator]:
                    raise ContractError("Source screenshot hash mismatch")
                images.extend([{"type": "text", "text": reference + " screenshot"},
                    {"type": "image_url", "image_url": {"url":
                        f"data:{media_type(raw)};base64," + base64.b64encode(raw).decode()}}])
    return rows, images


def submit(request, library, evidence, ledger, cases=None):
    key = keys(request.operation_id)
    previous = ledger.get(key)
    if previous:
        if previous["payload"]["request"] != request.model_dump():
            raise ContractError("Operation ID already binds another Workshop request")
        if previous["payload"]["owner"] != library.owner:
            raise ContractError("Operation belongs to another Workshop owner")
        return status(request.operation_id, ledger, library.owner)
    with library.lock:
        head = library.current(request.skill_id)
        if (head["revision"] if head else None) != request.base_revision:
            raise ContractError("Skill changed; refresh before authoring")
        original = library.files(request.skill_id, request.base_revision) if head else {}
        if request.mode == "diet" and not original:
            raise ContractError("Diet requires an existing Skill")
    rows, images = source_input(request, evidence)
    frozen_cases = []
    for item in request.cases:
        if cases is None:
            raise ContractError("Case store is unavailable")
        case = cases.get(item.case_id)
        review = cases.get_review(item.case_id, item.revision)
        if not any(w.snapshot_id == case["snapshot_id"] and case["position"] in w.positions
                   for w in request.sources):
            raise ContractError("Case must belong to a selected source position")
        frozen_cases.append({"case_id": item.case_id, "summary": case["summary"], "review": review,
                             "meaning": "reviewed correction proposal, not executed success"})
    policy = Path(__file__).with_name("policy.md").read_text(encoding="utf-8")
    payload = {"request": request.model_dump(), "owner": library.owner, "original": original,
               "policy": policy, "policy_hash": sha256(policy.encode()), "cases": frozen_cases,
               "source_input_hash": sha256(encode_json([rows, images]))}
    ledger.record(key, request.sources[0].snapshot_id, "workshop_request.v1", payload)
    return status(request.operation_id, ledger, library.owner)


def status(operation_id, ledger, owner=None):
    key = keys(operation_id)
    row = ledger.get(key)
    if (row is None or row["kind"] != "workshop_request.v1"
            or (owner is not None and row["payload"]["owner"] != owner)):
        return None
    result, error = ledger.get(key + "-result"), ledger.get(key + "-error")
    return {"operation_id": operation_id,
            "status": "completed" if result else "needs_attention" if error else "pending",
            "result": result["payload"] if result else None,
            "error": error["payload"] if error and not result else None}


def run(operation_id, library, evidence, ledger, gateway):
    key = keys(operation_id)
    row = ledger.get(key)
    if row is None or row["payload"]["owner"] != library.owner:
        raise ContractError("Workshop request unavailable for this owner")
    saved = ledger.get(key + "-result")
    if saved:
        return saved["payload"]
    payload = row["payload"]
    request = AuthorRequest.model_validate(payload["request"])
    rows, images = source_input(request, evidence)
    if sha256(encode_json([rows, images])) != payload["source_input_hash"]:
        raise ContractError("Frozen authoring evidence changed")
    context = {"request": request.model_dump(), "original": payload["original"],
               "source_steps": rows, "cases": payload["cases"]}
    call_keys = []

    def call(role, data, repetition, schema):
        messages = [{"role": "system", "content": payload["policy"] + "\nPerform " + role + " now."},
                    {"role": "user", "content": [{"type": "text", "text": encode_json(data).decode()},
                                               *images]}]
        # Pin effective transport/config before gateway admission; changed config cannot resend.
        ledger.record(key + "-" + repetition, row["snapshot_id"], "workshop_input.v1",
            {"messages_hash": sha256(encode_json(messages)), "model": gateway.settings.model_name,
             "endpoint": gateway.settings.model_base_url,
             "budget_scope": gateway.settings.model_budget_scope, "max_tokens": 4096,
             "policy_hash": payload["policy_hash"]})
        response = gateway.complete(messages, snapshot_id=row["snapshot_id"], operation_id=key,
            repetition_id=repetition, policy_version=payload["policy_hash"], max_tokens=4096)
        call_keys.append(response["call_key"])
        return schema.model_validate(load_json(
            response["response"]["choices"][0]["message"]["content"].encode()))

    feedback, drafts, outcome = None, [], "needs_evidence"
    # At most author + review + one author repair + one review. No automatic commit.
    for attempt in range(2):
        proposed = call("AUTHOR", {**context, "repair_feedback": feedback}, f"author{attempt}", Proposal)
        if proposed.decision != "propose":
            outcome, feedback = proposed.decision, proposed.reason
            break
        try:
            files = (diet(payload["original"], proposed.headings) if request.mode == "diet"
                     else proposed.files)
            validate_files(request.skill_id, files)
        except ValueError as exc:
            feedback = str(exc)
            outcome = "rejected"
            continue
        draft = Drafts(library).create(skill_id=request.skill_id,
            base_revision=request.base_revision, files=files,
            sources=[s.snapshot_id for s in request.sources],
            reason=f"{key} attempt:{attempt} {proposed.reason}", mode=request.mode,
            provenance={"operation_id": operation_id, "source_windows": request.model_dump()["sources"],
                        "cases": request.model_dump()["cases"],
                        "source_input_hash": payload["source_input_hash"]})
        drafts.append(draft["draft_id"])
        review = call("REVIEW", {**context, "proposed_files": files},
                      f"review{attempt}", Review)
        valid_refs = {r["ref"] for r in rows}
        if (not set(review.evidence_refs).issubset(valid_refs)
                or (review.verdict == "approved" and not review.evidence_refs)):
            raise ContractError("Review must cite supplied source steps")
        Drafts(library).review(draft["draft_id"], verdict=review.verdict, notes=review.notes,
            actor="model:" + gateway.settings.model_name, kind="model", policy_hash=payload["policy_hash"],
            evidence_refs=review.evidence_refs)
        outcome, feedback = review.verdict, review.notes
        if outcome != "rejected":
            break
    result = {"outcome": outcome, "notes": feedback, "draft_ids": drafts, "call_keys": call_keys,
              "source_refs": [r["ref"] for r in rows], "auto_committed": False,
              "execution_verified": False, "policy_hash": payload["policy_hash"]}
    ledger.record(key + "-result", row["snapshot_id"], "workshop_result.v1", result)
    return result
