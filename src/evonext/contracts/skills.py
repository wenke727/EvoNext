"""Portable, immutable references shared by Workshop and Runtime."""
from pydantic import BaseModel, ConfigDict, Field

Digest = str


class SkillRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    skill_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    owner: str = Field(min_length=1, max_length=128)
    revision: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    content_hash: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    source_snapshots: tuple[str, ...] = ()
    stage: str = Field(default="candidate", pattern=r"^candidate$")


class SkillBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    ref: SkillRef
    document: str
