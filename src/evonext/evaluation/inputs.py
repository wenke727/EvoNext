"""Prepare a bounded model view without changing or truncating source evidence."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from evonext.contracts.trajectory import encode_json, sha256


class InputOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    images: Literal["auto", "all", "last_three"] = "auto"
    markers: Literal["auto", "off"] = "auto"
    include_think: bool = False
    max_images: int = Field(default=10, ge=0, le=100)
    max_text_bytes: int = Field(default=256 * 1024, ge=1024, le=1024 * 1024)


# This is a named projection profile, not a serializer for the source document.
# Unknown fields remain available through the original trajectory endpoint.
FACT_FIELDS = (
    "tool_call", "action", "dispatch", "dispatched_action", "execution_result",
    "observed_result", "observation",
)


def prepare_input(snapshot, options: InputOptions):
    document = snapshot.document
    media = snapshot.media
    steps = []
    images = []
    omitted = []
    for position, step in enumerate(document["traj"]):
        value = step.get("value", {})
        fields = FACT_FIELDS + (("think", "thought") if options.include_think else ())
        facts = {}
        runtime = step.get("runtime")
        containers = [("step", step), ("value", value)]
        if isinstance(runtime, dict):
            containers.append(("runtime", runtime))
        for container, source in containers:
            facts[container] = {key: source[key] for key in fields if key in source}
            excluded = sorted(set(source) - set(fields) - (
                ({"index", "source_index", "step_id", "image", "value"}
                 | ({"runtime"} if isinstance(runtime, dict) else set()))
                if container == "step" else set()))
            if excluded:
                omitted.append({"position": position, "container": container, "fields": excluded})
        reference = f"{snapshot.id}/steps/{position}"
        steps.append({"position": position, "evidence_ref": reference,
                      "source_identity": {key: step[key] for key in
                          ("index", "source_index", "step_id") if key in step}, "facts": facts})
        locator = step.get("image")
        images.append({"position": position, "evidence_ref": reference + "/image",
                       "locator": locator, "sha256": media.get(locator),
                       "availability": "bound_unverified" if locator in media else
                           ("unbound" if locator else "missing"), "selected": False})
    candidates = [item for item in images if item["availability"] == "bound_unverified"]
    strategy = options.images
    if strategy == "auto":
        strategy = "all" if len(steps) <= 10 else "last_three"
    preferred = candidates if strategy == "all" else candidates[-3:]
    preferred_positions = {item["position"] for item in preferred}
    # Preserve chronology and report every image omitted by selection or budget.
    selected_positions = {item["position"] for item in preferred[:options.max_images]}
    for item in images:
        item["selected"] = item["position"] in selected_positions
        item["selection_reason"] = (
            item["availability"] if item["availability"] != "bound_unverified" else
            "selected" if item["selected"] else
            "image_budget" if item["position"] in preferred_positions else "strategy")
    context = {"instruction": document["instruction"], "task_id": document["task_id"],
               "steps": steps}
    context_bytes = encode_json(context)
    return {"profile": "evonext.evaluation-input.v1", "snapshot_id": snapshot.id,
            "source_manifest": snapshot.manifest, "source_version": snapshot.summary()["source_version"],
            "source_trajectory_path": f"/api/v1/snapshots/{snapshot.id}/trajectory",
            "step_count": len(steps), "options": options.model_dump(),
            "effective_image_strategy": strategy, "model_context": context,
            "context_sha256": sha256(context_bytes), "text_bytes": len(context_bytes),
            "text_budget_exceeded": len(context_bytes) > options.max_text_bytes,
            "images": images, "projection_omissions": omitted,
            "trajectory_fields_outside_context": sorted(set(document) - {"task_id", "instruction", "traj"}),
            "metadata_in_model_context": False,
            "media_readback_verified": False, "model_called": False,
            "delivered_evidence_refs": [], "evaluation_record": None}
