"""Validate a view; retain the original JSON, including unknown fields."""
import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr


class ContractError(ValueError):
    pass


class StepView(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    image: str | None = None
    value: dict[str, Any] = Field(default_factory=dict)


class TrajectoryView(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    task_id: StrictStr = Field(min_length=1, max_length=256)
    instruction: StrictStr
    traj: list[StepView]


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise ContractError("Duplicate JSON keys are not accepted")
        out[key] = value
    return out


def _nonfinite(_):
    raise ContractError("Non-finite JSON numbers are not accepted")


def load_json(raw: bytes) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ContractError("Expected a UTF-8 JSON object") from exc
    if not isinstance(value, dict):
        raise ContractError("Expected a JSON object")
    return value


def encode_json(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ContractError("Value is not portable UTF-8 JSON") from exc


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, init=False)
class Snapshot:
    """Validated once; public containers are detached views of immutable byte evidence."""
    trajectory_json: bytes
    metadata_json: bytes
    _media: tuple[tuple[str, str], ...] = field(repr=False)
    _document: dict = field(repr=False, compare=False)
    _metadata: dict = field(repr=False, compare=False)
    _manifest: dict = field(repr=False, compare=False)
    _id: str = field(repr=False)
    _summary: dict = field(repr=False, compare=False)

    def __init__(self, trajectory_json: bytes, metadata_json: bytes = b"{}", media=None,
                 *, max_steps=10000):
        trajectory, metadata = bytes(trajectory_json), bytes(metadata_json)
        document = load_json(trajectory)
        try:
            view = TrajectoryView.model_validate(document)
        except ValueError as exc:
            raise ContractError("Invalid trajectory: require string task_id, instruction and traj") from exc
        if len(view.traj) > max_steps:
            raise ContractError("Trajectory exceeds the configured step limit")
        meta = load_json(metadata)
        encode_json(document)
        encode_json(meta)
        if len(trajectory) + len(metadata) > 12 * 1024 * 1024:
            raise ContractError("Snapshot JSON exceeds the 12 MiB input limit")
        bindings = dict(media or {})
        if not all(isinstance(k, str) and isinstance(v, str) and len(v) == 64
                   and all(c in "0123456789abcdef" for c in v) for k, v in bindings.items()):
            raise ContractError("Invalid media digest binding")
        manifest = {"profile": "evonext.snapshot-bytes.v1",
                    "trajectory_sha256": sha256(trajectory),
                    "metadata_sha256": sha256(metadata), "media": bindings}
        identity = sha256(encode_json(manifest))
        versions = []
        for source in (document, meta):
            info = source.get("_version_info")
            if isinstance(info, dict) and type(info.get("version_number")) is int:
                versions.append(info["version_number"])
        origin = meta.get("source_snapshot")
        if isinstance(origin, dict) and type(origin.get("platform_version_number")) is int:
            versions.append(origin["platform_version_number"])
        version = versions[0] if versions and len(set(versions)) == 1 else None
        summary = {"snapshot_id": identity, "task_id": document["task_id"],
                   "instruction": document["instruction"][:600], "step_count": len(view.traj),
                   "source_version": version, "media_count": len(bindings)}
        for name, value in (("trajectory_json", trajectory), ("metadata_json", metadata),
                            ("_media", tuple(bindings.items())), ("_document", document),
                            ("_metadata", meta), ("_manifest", manifest), ("_id", identity),
                            ("_summary", summary)):
            object.__setattr__(self, name, value)

    @classmethod
    def create(cls, trajectory: bytes, metadata: bytes = b"{}", media=None, max_steps=10000):
        return cls(trajectory, metadata, media, max_steps=max_steps)

    @property
    def media(self) -> dict[str, str]:
        return dict(self._media)

    @property
    def document(self) -> dict:
        return copy.deepcopy(self._document)

    @property
    def metadata(self) -> dict:
        return copy.deepcopy(self._metadata)

    @property
    def manifest(self) -> dict:
        return copy.deepcopy(self._manifest)

    @property
    def id(self) -> str:
        return self._id

    def summary(self) -> dict:
        return dict(self._summary)


class Check(BaseModel):
    model_config = ConfigDict(extra="forbid")
    check_id: str
    judgment: Literal["pass", "fail", "unknown", "not_applicable", "not_assessed"]
    evidence_refs: list[str] = Field(default_factory=list)
    reason: str = ""


class EvaluationRecord(BaseModel):
    """Transport contract only; it does not implement or approve a grader."""
    model_config = ConfigDict(extra="forbid")
    record_id: str
    snapshot_id: str
    grader_id: str
    grader_version: str
    execution_status: Literal["completed", "partial", "error", "cancelled"]
    outcome: Literal["success", "failure", "unknown", "not_assessed"]
    checks: list[Check]
    trace_id: str | None = None
    native_result: dict[str, Any] = Field(default_factory=dict)
