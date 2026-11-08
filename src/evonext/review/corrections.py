"""A Review correction is a candidate, not a replayed action or training label."""
import io
from typing import Literal
from uuid import UUID

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from evonext.contracts.trajectory import ContractError, encode_json, sha256

HASH = r"^[0-9a-f]{64}$"
UUID4 = r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$"


class NormalizedBox(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    role: Literal["original_target", "suggested_target"]
    space: Literal["normalized_1000"] = "normalized_1000"
    xyxy: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]
    media_locator: str = Field(min_length=1, max_length=512)
    media_sha256: str = Field(pattern=HASH)
    image_width: int = Field(gt=0, le=20000)
    image_height: int = Field(gt=0, le=20000)
    orientation_profile: Literal["upright_v1"] = "upright_v1"

    @model_validator(mode="after")
    def bounds(self):
        x1, y1, x2, y2 = self.xyxy
        if not 0 <= x1 < x2 <= 1000 or not 0 <= y1 < y2 <= 1000:
            raise ValueError("BBox must be finite normalized_1000 xyxy with positive area")
        return self


class SuggestedClick(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Literal["click"]
    space: Literal["normalized_1000"] = "normalized_1000"
    point: tuple[FiniteFloat, FiniteFloat]

    @model_validator(mode="after")
    def bounds(self):
        if any(not 0 <= x <= 1000 for x in self.point):
            raise ValueError("Click coordinates must be in 0..1000")
        return self


class CorrectionItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    item_id: str = Field(pattern=UUID4)
    position: int = Field(ge=0)
    source_step_id: str | None = Field(default=None, min_length=1, max_length=256)
    source_action_stage: Literal["model_proposal", "resolved_action",
                                 "runtime_dispatch", "unknown"] = "unknown"
    source_action_ref: str | None = Field(default=None, min_length=1, max_length=256)
    kind: Literal["region_only", "action_correction", "no_action"]
    regions: list[NormalizedBox] = Field(default_factory=list, max_length=8)
    suggested_action: SuggestedClick | None = None
    verdict: Literal["accepted", "rejected", "unknown", "not_reviewed"] = "not_reviewed"
    reason: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def shape(self):
        if UUID(self.item_id).version != 4 or str(UUID(self.item_id)) != self.item_id:
            raise ValueError("Correction ID must be canonical UUIDv4")
        if self.kind == "region_only" and (not self.regions or self.suggested_action):
            raise ValueError("region_only requires a region, not an implicit action")
        if self.kind == "action_correction" and not self.suggested_action:
            raise ValueError("action_correction requires explicit click coordinates")
        if self.kind == "no_action" and (self.regions or self.suggested_action):
            raise ValueError("no_action cannot include geometry or an action")
        if self.verdict != "not_reviewed" and not self.reason.strip():
            raise ValueError("Reviewing an individual correction requires a reason")
        if self.source_action_stage != "unknown" and not self.source_action_ref:
            raise ValueError("Action stage requires a source action locator")
        return self


class CorrectionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    note: str = Field(default="", max_length=4000)
    items: list[CorrectionItem] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def distinct(self):
        ids = [i.item_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Correction item IDs must be unique")
        if len(encode_json(self.model_dump(mode="json"))) > 128 * 1024:
            raise ValueError("Correction draft exceeds the 128 KiB limit")
        return self

    def digest(self):
        return sha256(encode_json(self.model_dump(mode="json")))


class DraftCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    command_id: str = Field(pattern=UUID4)
    expected_draft_revision: int = Field(ge=0)
    draft: CorrectionDraft

    @model_validator(mode="after")
    def command_identity(self):
        if UUID(self.command_id).version != 4 or str(UUID(self.command_id)) != self.command_id:
            raise ValueError("Command ID must be canonical UUIDv4")
        return self


class FrozenReviewCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    command_id: str = Field(pattern=UUID4)
    expected_review_revision: int = Field(ge=0)
    draft_revision: int = Field(ge=1)
    draft_hash: str = Field(pattern=HASH)
    decision: Literal["confirmed", "rejected", "needs_evidence"]
    reason: str = Field(min_length=8, max_length=2000)

    @model_validator(mode="after")
    def command_identity(self):
        if UUID(self.command_id).version != 4 or str(UUID(self.command_id)) != self.command_id:
            raise ValueError("Command ID must be canonical UUIDv4")
        return self


def verify_draft(draft: CorrectionDraft, snapshot, assets):
    """Check each correction's independent anchor and bound, upright source image.

    Source index, the Case detection anchor, and the first-error hypothesis are
    not equivalent to a correction target position.
    """
    if snapshot is None:
        raise ContractError("Frozen source is unavailable")
    steps = snapshot.document["traj"]
    size_cache = {}
    for item in draft.items:
        if item.position >= len(steps):
            raise ContractError("Correction references a non-existent source position")
        step = steps[item.position]
        if item.source_step_id is not None and step.get("step_id") != item.source_step_id:
            raise ContractError("Correction source_step_id does not match the source")
        if item.source_action_stage != "unknown":
            ref = item.source_action_ref or ""
            value = step.get("value", {})
            runtime = step.get("runtime", {})
            known = {
                "model_proposal": {"value.tool_call", "value.raw_model_output"},
                "resolved_action": {"value.tool_call"},
                "runtime_dispatch": {"runtime.dispatched_action"},
            }
            if ref not in known[item.source_action_stage]:
                raise ContractError("Correction action reference does not match its stage")
            if (item.source_action_stage == "runtime_dispatch" and
                (not isinstance(runtime, dict) or runtime.get("dispatched_action") is None)):
                raise ContractError("Recorded runtime dispatch is absent")
            if (item.source_action_stage in {"model_proposal", "resolved_action"} and
                (not isinstance(value, dict) or value.get(ref.split(".")[1]) is None)):
                raise ContractError("Recorded model action is absent")
        if item.suggested_action and not step.get("image"):
            raise ContractError("A normalized click needs the corresponding source image")
        for region in item.regions:
            locator = region.media_locator
            if locator != step.get("image"):
                raise ContractError("Correction BBox must bind its own step's before-action media")
            if snapshot.media.get(locator) != region.media_sha256:
                raise ContractError("Correction image SHA does not match frozen media manifest")
            if locator not in size_cache:
                try:
                    original = assets.get(region.media_sha256)
                    with Image.open(io.BytesIO(original)) as decoded:
                        if decoded.format not in {"JPEG", "PNG", "WEBP"}:
                            raise ContractError("Unsupported region image format")
                        if decoded.getexif().get(274, 1) != 1:
                            raise ContractError("Image orientation must be explicitly normalized")
                        width, height = decoded.size
                        decoded.verify()
                        size_cache[locator] = (width, height)
                except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
                    raise ContractError("Correction media cannot be decoded") from exc
            if size_cache[locator] != (region.image_width, region.image_height):
                raise ContractError("Correction media dimensions differ from the frozen image")
    return draft
