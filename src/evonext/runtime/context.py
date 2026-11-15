"""Freeze context and validate an external Runtime handoff; no device implementation.

The external adapter owns execution, device leases, persistence, state verification
and irreversible-action approval. A prepared plan is NOT an executed trial.
"""
from dataclasses import dataclass
import time

from evonext.contracts.runtime import ExecutionGrant, RuntimeRequest
from evonext.contracts.trajectory import ContractError, Snapshot, encode_json, sha256
from evonext.contracts.skills import skill_content_hash


@dataclass(frozen=True)
class PreparedTrial:
    plan_json: bytes
    context_json: bytes

    @property
    def id(self):
        return sha256(self.plan_json)

    @property
    def context_hash(self):
        return sha256(self.context_json)


def prepare_trial(request: RuntimeRequest, snapshot: Snapshot) -> PreparedTrial:
    if request.snapshot_id != snapshot.id or request.task_id != snapshot.document["task_id"]:
        raise ContractError("Runtime input must match the frozen task and snapshot")
    steps = snapshot.document["traj"]
    if request.before_step_position > len(steps):
        raise ContractError("Context cutoff exceeds the source trajectory")
    if request.context_mode == "raw":
        # This is a declared source-context view, not a sanitized independent-judge input.
        # The actor must not get source human labels or outcomes.
        context = {"mode": "raw", "steps": []}
        for step in steps[:request.before_step_position]:
            value = step.get("value", {})
            context["steps"].append({"step_id": step.get("step_id"), "image": step.get("image"),
                "raw_model_output": value.get("raw_model_output"),
                "tool_call": value.get("tool_call"), "execution_result": value.get("execution_result")})
    elif request.context_mode == "skill":
        bundles = []
        for skill in request.skills:
            if (skill.ref.owner != request.owner
                    or skill_content_hash(skill.document, skill.assets, skill.format_version)
                    != skill.ref.content_hash):
                raise ContractError("Skill owner or content hash mismatch")
            bundles.append(skill.model_dump(mode="json"))
        context = {"mode": "skill", "skills": bundles}
    else:
        context = {"mode": "none"}
    if request.recovery is not None:
        ids = [step.get("step_id") for step in steps]
        if ids.count(request.recovery.source_step_id) != 1:
            raise ContractError("Recovery needs one unambiguous recorded source step ID")
        cutoff = ids.index(request.recovery.source_step_id)
        if request.recovery.correction_boundary == "after_action":
            cutoff += 1
        if request.context_mode == "raw" and request.before_step_position > cutoff:
            raise ContractError("Raw recovery context would expose future source steps")
    context_bytes = encode_json(context)
    if len(context_bytes) > 256 * 1024:
        raise ContractError("Runtime context exceeds the 256 KiB limit")
    plan = request.model_dump(mode="json", exclude={"skills"})
    plan.update(schema_version="evonext.runtime-plan.v1", context_hash=sha256(context_bytes),
                skill_refs=[s.ref.model_dump(mode="json") for s in request.skills],
                status="prepared_not_executed")
    return PreparedTrial(encode_json(plan), context_bytes)


def check_grant(request: RuntimeRequest, grant: ExecutionGrant, *, now=None):
    now = int(time.time()) if now is None else now
    for name in ("trial_id", "task_id", "snapshot_id", "owner", "target"):
        if getattr(request, name) != getattr(grant, name):
            raise PermissionError("Execution grant does not match the requested scope")
    if now >= grant.expires_at_epoch or request.max_actions > grant.max_actions:
        raise PermissionError("Execution grant is expired or action budget is exceeded")
    if request.skills and not grant.allow_candidate_skills:
        raise PermissionError("Candidate Skill consumption requires explicit experimental approval")
    if any(s.ref not in grant.allowed_skills for s in request.skills):
        raise PermissionError("Skill revision/hash binding is outside the approved scope")
    if request.recovery is not None and not grant.allow_recovery:
        raise PermissionError("Recovery is not authorized")


def verify_usage(plan: PreparedTrial, receipt: dict):
    """Verify linkage only. Does not prove physical execution or independent success."""
    from evonext.contracts.trajectory import load_json
    frozen = load_json(plan.plan_json)
    if frozen.get("context_hash") != plan.context_hash:
        raise ContractError("Prepared plan context has changed")
    expected = {"plan_id": plan.id, "trial_id": frozen["trial_id"],
                "task_id": frozen["task_id"], "snapshot_id": frozen["snapshot_id"],
                "context_hash": plan.context_hash, "skill_refs": frozen["skill_refs"]}
    if any(receipt.get(k) != v for k, v in expected.items()):
        raise ContractError("Runtime consumption receipt does not match its frozen plan")
    if not isinstance(receipt.get("new_trajectory_ref"), str) or not receipt["new_trajectory_ref"]:
        raise ContractError("External Runtime must return a new trajectory reference")
    if receipt["new_trajectory_ref"] == frozen["snapshot_id"]:
        raise ContractError("Original snapshot is not a new execution")
    return {"binding_verified": True, "execution_verified": False, "outcome": "not_assessed"}
