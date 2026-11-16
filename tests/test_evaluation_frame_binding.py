"""Synthetic frame declarations; no device or temporal verification is implied."""
import base64
import copy
from io import BytesIO

import pytest
from PIL import Image

from evonext.config import Settings
from evonext.contracts.trajectory import Snapshot, encode_json
from evonext.evaluation.images import image_message
from evonext.evaluation.inputs import InputOptions, prepare_input
from evonext.evidence.image_views import SOURCE_PROFILE
from evonext.evidence.service import EvidenceService
from evonext.evidence.store import MemoryAssets, MemorySnapshots


@pytest.mark.parametrize(("relation", "frame_id", "action_step", "expected_marker"), [
    ("before_action", "tap-1", "step-1", "dispatched"),
    ("after_action", "tap-1", "step-1", None),
    ("terminal", "tap-1", "step-1", None),
    ("unbound", "tap-1", "step-1", None),
    (None, "tap-1", "step-1", None),
    ({"unknown": True}, "tap-1", "step-1", None),
    ("before_action", "other-action", "step-1", None),
    ("before_action", None, "step-1", None),
    ("before_action", "tap-1", "other-step", None),
])
def test_marker_requires_explicit_pre_action_identity(relation, frame_id, action_step, expected_marker):
    pixels = BytesIO()
    Image.new("RGB", (100, 100), "white").save(pixels, format="PNG")
    raw = pixels.getvalue()
    assets, repo = MemoryAssets(), MemorySnapshots()
    digest = assets.put(raw)
    step = {"image": "images/one.png", "step_id": "step-1", "action_id": frame_id,
            "frame_relation": relation, "runtime": {"dispatched_action": {
                "action_id": "tap-1", "step_id": action_step,
                "action": "click", "coordinate": [50, 50], "coordinate_space": "pixel"}}}
    before = copy.deepcopy(step)
    snapshot = Snapshot.create(encode_json({"task_id": "synthetic-frame", "instruction": "inspect",
        "traj": [step]}), media={step["image"]: digest})
    repo.put(snapshot)
    evidence = EvidenceService(repo, assets, Settings(demo=True, _env_file=None))
    preview = prepare_input(snapshot, InputOptions())
    parts, receipt = image_message(snapshot, preview["images"][0], evidence, "auto", image_profile=SOURCE_PROFILE)
    assert receipt["marker_source"] == expected_marker
    binding = receipt["frame_binding"]
    assert binding == preview["images"][0]["frame_binding"]
    assert binding == preview["model_context"]["steps"][0]["observation_relation"]["frame_binding"]
    assert binding["execution_verified"] is False
    assert f"frame_relation={relation if isinstance(relation, str) else 'unknown'}" in parts[0]["text"]
    wire = base64.b64decode(parts[-1]["image_url"]["url"].split(",", 1)[1])
    if expected_marker is None:
        assert wire == raw
    else:
        assert wire != raw
    assert snapshot.document["traj"][0] == before
    assert evidence.read_media(snapshot.id, step["image"]) == raw
