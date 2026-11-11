"""Render source-declared coordinates on a derived copy of the owning step image."""
import base64
from io import BytesIO
from math import atan2, cos, pi, sin

from PIL import Image, ImageDraw

from evonext.contracts.trajectory import ContractError, sha256
from evonext.evidence.packages import media_type


def marked_image(raw, step):
    runtime = step.get("runtime") or {}
    action = runtime.get("dispatched_action") if isinstance(runtime, dict) else None
    source = "dispatched"
    if action is None:
        source = "proposed"
        action = step.get("value", {}).get("tool_call")
        if isinstance(action, dict) and action.get("name") == "mobile_use":
            action = action.get("arguments")
    if not isinstance(action, dict):
        return raw, None
    space = action.get("coordinate_space", step.get("coordinate_space"))
    if space not in ("pixel", "normalized_1000"):
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
            limits = (1000, 1000) if space == "normalized_1000" else (image.width-1, image.height-1)
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
    canvas.save(output, format="PNG")
    return output.getvalue(), source


def image_message(snapshot, descriptor, evidence, mode):
    raw = evidence.read_media(snapshot.id, descriptor["locator"])
    if sha256(raw) != descriptor["sha256"]:
        raise ContractError("Screenshot hash mismatch")
    data, source = (marked_image(raw, snapshot.document["traj"][descriptor["position"]])
                    if mode == "auto" else (raw, None))
    reference = descriptor["evidence_ref"]
    label = reference if source is None else f"{reference} (before action, {source} marker)"
    receipt = {"evidence_ref": reference, "sha256": descriptor["sha256"],
               "view_sha256": sha256(data), "marker_source": source,
               "renderer": "action-marker.v1" if source else None}
    url = f"data:{media_type(data)};base64," + base64.b64encode(data).decode()
    return [{"type": "text", "text": label}, {"type": "image_url", "image_url": {"url": url}}], receipt
