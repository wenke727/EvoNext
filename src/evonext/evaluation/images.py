"""Render source-declared coordinates on a derived copy of the owning step image."""
import base64
from io import BytesIO
from math import atan2, cos, pi, sin

from PIL import Image, ImageDraw

from evonext.contracts.trajectory import ContractError, encode_json, sha256
from evonext.evidence.packages import media_type
from evonext.evidence.image_views import JPEG_PROFILE, SOURCE_PROFILE, model_image


def marker_action(step):
    runtime = step.get("runtime") or {}
    action = runtime.get("dispatched_action") if isinstance(runtime, dict) else None
    source = "dispatched"
    if action is None:
        source = "proposed"
        action = step.get("value", {}).get("tool_call")
        if isinstance(action, dict) and action.get("name") == "mobile_use":
            action = action.get("arguments")
    return action, source


def frame_binding(step):
    """Named step-frame profile: source declarations, never inferred adjacency.

    Step frame_relation/action_id bind its single image to a source action.
    The selected action must carry the same nonempty ID; a step ID alone is
    insufficient. Other source layouts remain unknown until explicitly adapted.
    """
    relation = step.get("frame_relation")
    if not isinstance(relation, str) or relation not in {"before_action", "after_action", "terminal", "unbound"}:
        relation = "unknown"
    action, source = marker_action(step)
    action_id = action.get("action_id") if isinstance(action, dict) else None
    bound = (isinstance(action_id, str) and bool(action_id)
             and step.get("action_id") == action_id
             and (not isinstance(action, dict) or action.get("step_id", step.get("step_id")) == step.get("step_id")))
    return {"profile": "step-frame-binding.v1", "frame_relation": relation,
            "action_binding": "source_bound" if bound else "unknown",
            "action_id": action_id if bound else None, "step_id": step.get("step_id"),
            "action_source": source if bound else None,
            "execution_verified": False}


def marked_image(raw, step, runtime_coordinate_profile="source", *, lossless=False):
    binding = frame_binding(step)
    if binding["frame_relation"] != "before_action" or binding["action_binding"] != "source_bound":
        return raw, None
    action, source = marker_action(step)
    space = action.get("coordinate_space")
    if space not in ("pixel", "normalized_1000", "normalized_fraction"):
        space = step.get("coordinate_space")
    if space is None and source == "dispatched" and runtime_coordinate_profile == "evoloop_fraction_v1":
        space = "normalized_fraction"
    if space not in ("pixel", "normalized_1000", "normalized_fraction"):
        return raw, None
    kind = action.get("action")
    if kind in ("swipe", "drag"):
        points = [action.get("start_coordinate", action.get("coordinate")),
                  action.get("end_coordinate", action.get("coordinate2"))]
    elif kind in ("click", "tap", "long_press", "double_click"):
        points = [action.get("coordinate")]
    else:
        return raw, None
    with Image.open(BytesIO(raw)) as image:
        if image.width * image.height > 16_000_000 or image.getexif().get(274, 1) != 1:
            return raw, None
        xy = []
        for point in points:
            if not isinstance(point, list) or len(point) != 2:
                return raw, None
            limits = ((1000, 1000) if space == "normalized_1000" else
                      (1, 1) if space == "normalized_fraction" else (image.width-1, image.height-1))
            if any(type(n) not in (int, float) or not 0 <= n <= limit for n, limit in zip(point, limits)):
                return raw, None
            xy.append(tuple(round(n * (size-1) / max(limit, 1))
                            for n, size, limit in zip(point, image.size, limits)))
        canvas = image.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    x, y = xy[-1]
    r = max(4, min(canvas.size) // 65)
    if len(xy) == 1:
        draw.ellipse((x-r, y-r, x+r, y+r), outline="red", width=2)
    else:
        angle = atan2(y-xy[0][1], x-xy[0][0])
        draw.line(xy, fill="red", width=3)
        for offset in (-pi/6, pi/6):
            draw.line([(x,y), (x-2*r*cos(angle+offset), y-2*r*sin(angle+offset))], fill="red", width=3)
    output = BytesIO()
    if runtime_coordinate_profile == "evoloop_fraction_v1" and not lossless:
        canvas.save(output, format="JPEG", quality=98, subsampling=0, optimize=True)
    else:
        canvas.save(output, format="PNG")
    return output.getvalue(), source


def image_message(snapshot, descriptor, evidence, mode, runtime_coordinate_profile="source",
                  image_profile=JPEG_PROFILE):
    raw = evidence.read_media(snapshot.id, descriptor["locator"])
    if sha256(raw) != descriptor["sha256"]:
        raise ContractError("Screenshot hash mismatch")
    data, source = (marked_image(raw, snapshot.document["traj"][descriptor["position"]],
                                 runtime_coordinate_profile, lossless=image_profile != SOURCE_PROFILE)
                    if mode == "auto" else (raw, None))
    view = None
    if image_profile != SOURCE_PROFILE:
        data, view = model_image(data, image_profile)
        view["rendered_sha256"] = view["source_sha256"]
        view["source_sha256"] = descriptor["sha256"]
        view["source_bytes"] = len(raw)
    reference = descriptor["evidence_ref"]
    binding = frame_binding(snapshot.document["traj"][descriptor["position"]])
    label = f"{reference} (frame_relation={binding['frame_relation']}, action_binding={binding['action_binding']}; source declaration, execution unverified)"
    if source is not None:
        label += f" ({source} marker)"
    receipt = {"evidence_ref": reference, "sha256": descriptor["sha256"],
               "view_sha256": sha256(data), "marker_source": source, "frame_binding": binding,
               "runtime_coordinate_profile": runtime_coordinate_profile,
               "renderer": ("action-marker.evoloop-fraction.jpeg98.v1"
                            if runtime_coordinate_profile == "evoloop_fraction_v1" and image_profile == SOURCE_PROFILE
                            else "action-marker.v1")
                   if source else None}
    if view is not None:
        receipt["image_view"] = view
        # Preserve the relationship to source pixel coordinates after resizing.
        label += "\nImage consumption view (source coordinates unchanged): " + encode_json(view).decode()
    url = f"data:{media_type(data)};base64," + base64.b64encode(data).decode()
    return [{"type": "text", "text": label}, {"type": "image_url", "image_url": {"url": url}}], receipt
