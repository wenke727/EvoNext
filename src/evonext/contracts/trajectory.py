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


@dataclass(frozen=True)
class Snapshot:
    trajectory_json: bytes
    metadata_json: bytes = b"{}"
    media: dict[str, str] = field(default_factory=dict)

    @classmethod
    def create(cls, trajectory: bytes, metadata: bytes = b"{}", media=None, max_steps=10000):
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
            raise ContractError("Snapshot JSON exceeds the Mongo-safe 12 MiB limit")
        bindings = copy.deepcopy(media or {})
        if not all(isinstance(k, str) and isinstance(v, str) and len(v) == 64
                   and all(c in "0123456789abcdef" for c in v) for k, v in bindings.items()):
            raise ContractError("Invalid media digest binding")
        return cls(bytes(trajectory), bytes(metadata), bindings)

    @property
    def document(self) -> dict:
        return load_json(self.trajectory_json)

    @property
    def metadata(self) -> dict:
        return load_json(self.metadata_json)

    @property
    def manifest(self) -> dict:
        return {"profile": "evonext.snapshot-bytes.v1",
                "trajectory_sha256": sha256(self.trajectory_json),
                "metadata_sha256": sha256(self.metadata_json), "media": dict(self.media)}

    @property
    def id(self) -> str:
        return sha256(encode_json(self.manifest))

    def summary(self) -> dict:
        doc = self.document
        versions = []
        for source in (doc, self.metadata):
            info = source.get("_version_info")
            if isinstance(info, dict) and type(info.get("version_number")) is int:
                versions.append(info["version_number"])
        origin = self.metadata.get("source_snapshot")
        if isinstance(origin, dict) and type(origin.get("platform_version_number")) is int:
            versions.append(origin["platform_version_number"])
        version = versions[0] if versions and len(set(versions)) == 1 else None
        return {"snapshot_id": self.id, "task_id": doc["task_id"],
                "instruction": doc["instruction"][:600], "step_count": len(doc["traj"]),
                "source_version": version, "media_count": len(self.media)}


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
