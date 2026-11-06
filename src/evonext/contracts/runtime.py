"""Runtime admission data; configuration and Skill text never grant tool authority."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .skills import SkillBundle, SkillRef


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    kind: Literal["local_device", "cloud_batch"]
    resource_id: str = Field(min_length=1, max_length=128)


class RecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    strategy: Literal["current_state", "replay_prefix"]
    reviewed_case_ref: str = Field(min_length=1)
    source_step_id: str = Field(min_length=1)
    correction_boundary: Literal["before_action", "after_action"]
    expected_state_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class RuntimeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    trial_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1)
    snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    owner: str = Field(min_length=1)
    target: Target
    context_mode: Literal["none", "raw", "skill"] = "none"
    # A fixed prefix: raw decision context never defaults to the whole finished trajectory.
    before_step_position: int = Field(default=0, ge=0)
    skills: tuple[SkillBundle, ...] = ()
    max_actions: int = Field(default=20, ge=1, le=1000)
    recovery: RecoveryRequest | None = None

    @model_validator(mode="after")
    def context_shape(self):
        if (self.context_mode == "skill") != bool(self.skills):
            raise ValueError("Skill mode requires pinned bundles; other modes cannot carry skills")
        identities = [(s.ref.owner, s.ref.skill_id) for s in self.skills]
        if len(set(identities)) != len(identities):
            raise ValueError("One Skill identity may have only one revision in a trial")
        return self


class ExecutionGrant(BaseModel):
    """Supplied by a trusted host, not deserialized from arbitrary model output."""
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    grant_id: str = Field(min_length=1)
    trial_id: str
    task_id: str
    snapshot_id: str
    owner: str
    target: Target
    allowed_skills: tuple[SkillRef, ...] = ()
    max_actions: int = Field(ge=1, le=1000)
    expires_at_epoch: int
    allow_candidate_skills: bool = False
    allow_recovery: bool = False
