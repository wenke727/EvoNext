"""Explicit, bounded author/reviewer loop on the existing gateway and PG ledger."""
import base64
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from evonext.contracts.model_request import chat_payload
from evonext.contracts.trajectory import ContractError, encode_json, load_json, sha256
from evonext.evidence.packages import media_type
from evonext.skills.workshop.authoring import diet, validate_files
from evonext.skills.workshop.drafts import Drafts


class SourceWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    snapshot_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    positions: list[int] = Field(min_length=1, max_length=12)
    # None preserves the legacy all-bound-images selection; [] explicitly selects none.
    image_positions: list[int] | None = Field(default=None, max_length=4)


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
    sources: list[SourceWindow] = Field(min_length=1, max_length=8)
    cases: list[CaseInput] = Field(default_factory=list, max_length=4)
    instruction: str = Field(min_length=1, max_length=4000)
    include_images: bool = False
    evidence_mode: Literal["selected", "on_demand"] = "selected"


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
    evidence_refs: list[str] = Field(max_length=96)


class EvidenceRead(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    evidence_ref: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)


class EvidenceQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    read_evidence: list[EvidenceRead] = Field(min_length=1, max_length=4)


class EvidenceStop(Exception):
    """A completed, non-success learning outcome when a shared bound is reached."""


def evidence_context(data, rows, delivered, feedback):
    return {**data, "image_inventory": [{"evidence_ref": r["ref"],
                "available": r["image_available"]} for r in rows],
            "image_refs_in_this_request": delivered, "evidence_feedback": feedback,
            "read_protocol": {"read_evidence": [{"evidence_ref": "snapshot:position",
                "reason": "The state or transition to verify"}]},
            "evidence_limits": {"images": 4, "read_rounds": 2, "model_calls": 6}}


def keys(operation_id):
    return "workshop-" + sha256(operation_id.encode())


def source_input(request, evidence):
    rows, images = [], []
    for window in request.sources:
        snapshot = evidence.get(window.snapshot_id)
        if snapshot is None:
            raise ContractError("Workshop source snapshot is unavailable")
        if window.image_positions is not None:
            if not set(window.image_positions).issubset(window.positions):
                raise ContractError("Image positions must belong to the selected text window")
            if window.image_positions and not request.include_images:
                raise ContractError("Explicit image selection requires include_images")
        image_positions = set(window.positions if window.image_positions is None
                              else window.image_positions)
        for position in sorted(set(window.positions)):
            if not 0 <= position < len(snapshot.document["traj"]):
                raise ContractError("Source position is outside the frozen trajectory")
            step = snapshot.document["traj"][position]
            reference = f"{snapshot.id}:{position}"
            locator = step.get("image")
            delivered = request.include_images and position in image_positions and locator in snapshot.media
            rows.append({"ref": reference, "instruction": snapshot.document["instruction"],
                         "step": step, "image_attached_to_input": delivered,
                         "image_available": locator in snapshot.media})
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


def submit(request, library, evidence, ledger, cases=None, *, settings=None, learning=None):
    key = keys(request.operation_id)
    previous = ledger.get(key)
    if previous:
        if previous["payload"]["request"] != request.model_dump():
            raise ContractError("Operation ID already binds another Workshop request")
        if previous["payload"]["owner"] != library.owner:
            raise ContractError("Operation belongs to another Workshop owner")
        return status(request.operation_id, ledger, library.owner)
    payload, rows, images = prepare_authoring(request, library, evidence, cases)
    if learning is not None:
        payload.update(learning)
    if settings is not None and input_budget(payload, rows, images, settings)["input_budget_exceeded"]:
        raise ContractError("Workshop input exceeds the configured byte budget; preview and select fewer images or configure an explicit larger budget")
    ledger.record(key, request.sources[0].snapshot_id, "workshop_request.v1", payload)
    return status(request.operation_id, ledger, library.owner)


def prepare_authoring(request, library, evidence, cases=None):
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
    return payload, rows, images


def messages_for(policy, role, data, images):
    return [{"role": "system", "content": policy + "\nPerform " + role + " now."},
            {"role": "user", "content": [{"type": "text", "text": encode_json(data).decode()},
                                       *images]}]


def author_context(payload, rows):
    context = {"request": payload["request"], "original": payload["original"],
               "source_steps": rows, "cases": payload["cases"]}
    if "retrieval" in payload:
        context["source_selection"] = payload["retrieval"]["sources"]
    return context


def input_budget(payload, rows, images, settings):
    context = {**author_context(payload, rows), "repair_feedback": None,
               "previous_proposal": None}
    if payload["request"].get("evidence_mode") == "on_demand":
        attached = sorted({r["ref"] for r in rows if r["image_attached_to_input"]})
        context = evidence_context(context, rows, attached, [])
    messages = messages_for(payload["policy"], "AUTHOR", context, images)
    size = len(encode_json(chat_payload(settings.model_name, messages, 4096)))
    return {"initial_request_bytes": size, "max_request_bytes": settings.model_max_request_bytes,
            "input_budget_exceeded": size > settings.model_max_request_bytes,
            "model_configured": bool(settings.model_name),
            "budget_scope": "initial_author_only; review and repair checked before each call"}


def preview(request, library, evidence, settings, cases=None, *, retrieval=None):
    payload, rows, images = prepare_authoring(request, library, evidence, cases)
    if retrieval is not None:
        payload["retrieval"] = retrieval
    return {"steps": rows, "bound_images": len(images) // 2, "model_called": False,
            **input_budget(payload, rows, images, settings)}


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
    context = author_context(payload, rows)
    call_keys, evidence_events = [], []
    state = {"calls": 0, "reads": 0}
    available = {r["ref"]: r for r in rows}
    loaded = {r["ref"] for r in rows if r["image_attached_to_input"]}
    delivered = set()
    deadline = time.monotonic() + 180

    def call(role, data, repetition, schema):
        feedback = []
        while True:
            if time.monotonic() >= deadline:
                raise EvidenceStop("time_budget")
            if state["calls"] >= 6:
                raise EvidenceStop("call_budget")
            current = (evidence_context(data, rows, sorted(loaded), feedback)
                       if request.evidence_mode == "on_demand" else data)
            messages = messages_for(payload["policy"], role, current, images)
            wire = chat_payload(gateway.settings.model_name, messages, 4096)
            if len(encode_json(wire)) > gateway.settings.model_max_request_bytes:
                raise EvidenceStop("input_byte_budget")
            identity = repetition if not feedback else repetition + "-read-" + str(state["reads"])
            ledger.record(key + "-" + identity, row["snapshot_id"], "workshop_input.v1",
                {"messages_hash": sha256(encode_json(messages)), "model": gateway.settings.model_name,
                 "endpoint": gateway.settings.model_base_url,
                 "budget_scope": gateway.settings.model_budget_scope, "max_tokens": 4096,
                 "image_refs": sorted(loaded), "request_bytes": len(encode_json(wire)),
                 "policy_hash": payload["policy_hash"]})
            response = gateway.complete(messages, snapshot_id=row["snapshot_id"], operation_id=key,
                repetition_id=identity, policy_version=payload["policy_hash"], max_tokens=4096)
            state["calls"] += 1
            call_keys.append(response["call_key"])
            delivered.update(loaded)
            reply = load_json(response["response"]["choices"][0]["message"]["content"].encode())
            if request.evidence_mode != "on_demand" or "read_evidence" not in reply:
                return schema.model_validate(reply)
            query = EvidenceQuery.model_validate(reply)
            if state["reads"] >= 2:
                raise EvidenceStop("evidence_round_budget")
            state["reads"] += 1
            feedback = []
            for item in query.read_evidence:
                if item.evidence_ref not in available:
                    raise ContractError("Requested image is outside the frozen source window")
                source = available[item.evidence_ref]
                event = {"evidence_ref": item.evidence_ref, "reason": item.reason}
                if item.evidence_ref in loaded:
                    event["status"] = "already_available"
                elif not source["image_available"]:
                    event["status"] = "missing_image"
                elif len(loaded) >= 4:
                    event["status"] = "image_budget"
                else:
                    snapshot_id, position = item.evidence_ref.rsplit(":", 1)
                    # Reuse the same source reader and its byte-hash verification.
                    window = SourceWindow(snapshot_id=snapshot_id, positions=[int(position)],
                                          image_positions=[int(position)])
                    _, additions = source_input(request.model_copy(update={
                        "sources": [window], "include_images": True}), evidence)
                    images.extend(additions)
                    loaded.add(item.evidence_ref)
                    digest = evidence.get(snapshot_id).media[source["step"]["image"]]
                    event.update(status="loaded_not_yet_delivered", image_hash=digest)
                feedback.append(event)
            evidence_events.extend(feedback)
            ledger.record(key + "-evidence-" + str(state["reads"]), row["snapshot_id"],
                "workshop_evidence.v1", {"events": feedback, "delivery": "not_confirmed"})
            if not any(e["status"] == "loaded_not_yet_delivered" for e in feedback):
                raise EvidenceStop("no_new_image_evidence")

    feedback, drafts, outcome = None, [], "needs_evidence"
    previous_proposal = None
    last_draft_files = None
    # At most author + review + one author repair + one review. No automatic commit.
    try:
        for attempt in range(2):
            proposed = call("AUTHOR", {**context, "repair_feedback": feedback,
                                     "previous_proposal": previous_proposal}, f"author{attempt}", Proposal)
            if proposed.decision != "propose":
                outcome, feedback = proposed.decision, proposed.reason
                break
            previous_proposal = {"files": proposed.files, "headings": proposed.headings,
                                 "reason": proposed.reason}
            try:
                files = (diet(payload["original"], proposed.headings) if request.mode == "diet"
                         else proposed.files)
                validate_files(request.skill_id, files)
            except ValueError as exc:
                feedback = str(exc)
                outcome = "rejected"
                continue
            previous_proposal["files"] = files
            draft = Drafts(library).create(skill_id=request.skill_id,
                base_revision=request.base_revision, files=files,
                sources=[s.snapshot_id for s in request.sources],
                reason=f"{key} attempt:{attempt} {proposed.reason}", mode=request.mode,
                provenance={"operation_id": operation_id, "source_windows": request.model_dump()["sources"],
                            "cases": request.model_dump()["cases"],
                            "source_input_hash": payload["source_input_hash"]})
            drafts.append(draft["draft_id"])
            last_draft_files = files
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
    except EvidenceStop as exc:
        outcome, feedback = "needs_evidence", str(exc)
    result = {"outcome": outcome, "notes": feedback, "draft_ids": drafts, "call_keys": call_keys,
              "source_refs": [r["ref"] for r in rows], "auto_committed": False,
              "execution_verified": False, "policy_hash": payload["policy_hash"],
              "evidence_events": evidence_events, "delivered_image_refs": sorted(delivered),
              "model_calls": state["calls"], "retrieval": payload.get("retrieval"),
              "body_chars": (len(last_draft_files["SKILL.md"].split("---", 2)[2].strip())
                             if last_draft_files else None)}
    ledger.record(key + "-result", row["snapshot_id"], "workshop_result.v1", result)
    return result
