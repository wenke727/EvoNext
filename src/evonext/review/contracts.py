"""A Case represents one reported issue at an immutable source locator.

It is not a task revision, a machine evaluation record, an approved training
sample, or an instruction to execute on a device.
"""
from uuid import UUID
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evonext.contracts.trajectory import ContractError, encode_json, sha256

SnapshotId = str


class AnalysisRef(BaseModel):
    """Read-only link to a producer-owned result; not verified or adopted here."""
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["outcome", "diagnosis"]
    producer: str = Field(min_length=1, max_length=80)
    record_id: str = Field(min_length=1, max_length=256)
    snapshot_id: SnapshotId = Field(pattern=r"^[0-9a-f]{64}$")


class CaseProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    # Client-generated stable identity permits safe retry after a lost acknowledgement.
    case_id: UUID
    snapshot_id: SnapshotId = Field(pattern=r"^[0-9a-f]{64}$")
    position: int = Field(ge=0)
    source_step_id: str | None = Field(default=None, min_length=1, max_length=256)
    issue_kind: Literal["task_outcome", "step_action", "tool_execution", "environment",
                        "safety", "data_or_label", "unknown"]
    summary: str = Field(min_length=8, max_length=2000)
    evidence_refs: list[str] = Field(min_length=1, max_length=16)
    analysis_refs: list[AnalysisRef] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def distinct_references(self):
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("Evidence references must be distinct")
        keys = [(ref.producer, ref.record_id) for ref in self.analysis_refs]
        if len(keys) != len(set(keys)):
            raise ValueError("Analysis references must be distinct")
        return self

    def payload(self) -> dict:
        return self.model_dump(mode="json")

    def digest(self) -> str:
        return sha256(encode_json(self.payload()))


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    decision: Literal["confirmed", "rejected", "needs_evidence"]
    reason: str = Field(min_length=8, max_length=2000)


class CaseNotFound(Exception):
    pass


class CaseConflict(Exception):
    pass


class StaleCase(Exception):
    pass


def verify_proposal(proposal: CaseProposal, snapshot) -> dict:
    if snapshot is None or snapshot.id != proposal.snapshot_id:
        raise CaseNotFound("Frozen snapshot not found")
    steps = snapshot.document["traj"]
    if proposal.position >= len(steps):
        raise ContractError("Source step position is outside the frozen trajectory")
    step = steps[proposal.position]
    raw_id = step.get("step_id")
    if proposal.source_step_id is not None and raw_id != proposal.source_step_id:
        raise ContractError("Source step identity does not match the frozen trajectory")
    # A missing source step ID remains unknown. Position is explicitly snapshot-scoped.
    media = snapshot.media
    for ref in proposal.evidence_refs:
        if ref.startswith("step:"):
            ordinal = ref.removeprefix("step:")
            if not ordinal.isdecimal() or int(ordinal) >= len(steps):
                raise ContractError("Evidence step is not in the frozen trajectory")
        elif ref.startswith("media:"):
            locator = ref.removeprefix("media:")
            if locator not in media:
                raise ContractError("Evidence media is not bound to the frozen snapshot")
        else:
            raise ContractError("Evidence references must use step: or media: locators")
    if f"step:{proposal.position}" not in proposal.evidence_refs:
        raise ContractError("Case must cite its own frozen anchor step")
    if any(ref.snapshot_id != proposal.snapshot_id for ref in proposal.analysis_refs):
        raise ContractError("An external analysis reference cannot silently change source")
    return {
        "case_id": str(proposal.case_id),
        "snapshot_id": proposal.snapshot_id,
        "position": proposal.position,
        "source_step_id": proposal.source_step_id,
        "source_version": snapshot.summary()["source_version"],
        "issue_kind": proposal.issue_kind,
        "summary": proposal.summary,
        "evidence_refs": list(proposal.evidence_refs),
        # External refs are pointers, not trusted evaluation/diagnosis conclusions.
        "analysis_refs": [r.model_dump(mode="json") for r in proposal.analysis_refs],
        "proposal_hash": proposal.digest(),
    }
