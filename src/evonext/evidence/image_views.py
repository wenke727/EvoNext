"""Versioned model-consumption views; source assets remain byte-for-byte unchanged."""
from evonext.contracts.trajectory import ContractError, sha256
from evonext.evidence.packages import media_type
from evonext.evidence.image_processing import (
    JPEG_PROFILE, JPEG90_PROFILE, FACTOR as FACTOR, MAX_PATCHES as MAX_PATCHES,
    jpeg_view, view_size as _view_size,
)

SOURCE_PROFILE = "source.v1"


def profile_for_quality(quality):
    return {98: JPEG_PROFILE, 90: JPEG90_PROFILE}[quality]


def view_size(width, height):
    """Qwen geometry, matching EvoLoop's factor/min/max pixel rules."""
    try:
        return _view_size(width, height)
    except ValueError as exc:
        raise ContractError(str(exc)) from exc


def model_image(raw, profile=JPEG_PROFILE):
    if profile == SOURCE_PROFILE:
        source_hash = sha256(raw)
        return raw, {"profile": profile, "source_sha256": source_hash,
                     "view_sha256": source_hash, "source_bytes": len(raw), "view_bytes": len(raw),
                     "mime": media_type(raw)}
    try:
        return jpeg_view(raw, profile)
    except ValueError as exc:
        raise ContractError(str(exc)) from exc
