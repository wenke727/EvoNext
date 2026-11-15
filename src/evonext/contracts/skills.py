"""Portable, immutable references shared by Workshop and Runtime."""
import re

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from evonext.contracts.trajectory import ContractError, encode_json, sha256

Digest = str


class SkillRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    skill_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    owner: str = Field(min_length=1, max_length=128)
    revision: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    content_hash: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    source_snapshots: tuple[str, ...] = ()
    stage: str = Field(default="candidate", pattern=r"^candidate$")


class SkillAsset(BaseModel):
    """UTF-8 attachment; scripts are inert bytes, never executable capabilities."""
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    path: str
    content: str

    @model_validator(mode="after")
    def safe_path(self):
        parts = self.path.split("/")
        if (len(parts) < 2 or parts[0] not in {"references", "templates", "scripts", "assets"}
                or any(not re.fullmatch(r"[a-zA-Z0-9_-][a-zA-Z0-9_.-]*", p)
                       or p.endswith(".") for p in parts)):
            raise ValueError("Asset requires a safe relative path in an allowed directory")
        return self


def skill_content_hash(document, assets=(), format_version="v1"):
    if format_version == "v1":
        if assets:
            raise ContractError("v1 Skill cannot contain attachments")
        return sha256(document.encode("utf-8"))
    if format_version != "v2":
        raise ContractError("Unsupported Skill bundle version")
    names = [asset.path.casefold() for asset in assets]
    if len(names) != len(set(names)) or len(assets) > 50:
        raise ContractError("Duplicate assets or too many files")
    payload = {"SKILL.md": document, **{a.path: a.content for a in assets}}
    raw = encode_json(payload)
    if len(raw) > 256 * 1024:
        raise ContractError("Skill bundle exceeds 256 KiB")
    return sha256(raw)


class SkillBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    ref: SkillRef
    document: str
    format_version: str = Field(default="v1", pattern=r"^v[12]$")
    assets: tuple[SkillAsset, ...] = ()

    @model_serializer(mode="wrap")
    def compatible_wire(self, handler):
        result = handler(self)
        if self.format_version == "v1" and not self.assets:
            result.pop("format_version", None)
            result.pop("assets", None)
        return result
