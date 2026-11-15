"""Mirrored EvoLoop/EvoNext image geometry and JPEG codec; no I/O or model calls.

Keep this module byte-identical in both repositories. Domain owners validate source
bindings and persist receipts. Geometry budgets are patches, never billing tokens.
"""
from hashlib import sha256
from io import BytesIO
from math import ceil, floor, sqrt

from PIL import Image, UnidentifiedImageError

JPEG_PROFILE = "jpeg98-qwen32-patch980.pillow.v1"
JPEG90_PROFILE = "jpeg90-qwen32-patch980.pillow.v1"
FACTOR, MAX_PATCHES = 32, 980


def smart_resize(height, width, factor=FACTOR, min_pixels=None, max_pixels=None):
    """Return height/width using Qwen's aligned round/floor/ceil geometry."""
    if any(type(n) is not int or n <= 0 for n in (height, width, factor)):
        raise ValueError("Image dimensions and alignment factor must be positive integers")
    minimum = 4 * factor**2 if min_pixels is None else min_pixels
    maximum = MAX_PATCHES * factor**2 if max_pixels is None else max_pixels
    if (any(type(n) is not int or n <= 0 for n in (minimum, maximum))
            or maximum < minimum or maximum < factor**2):
        raise ValueError("Invalid aligned image pixel budget")
    if max(height, width) / min(height, width) > 200:
        raise ValueError("Unsupported screenshot aspect ratio")
    h, w = (max(factor, round(n / factor) * factor) for n in (height, width))
    if h * w > maximum:
        ratio = sqrt(height * width / maximum)
        h, w = (floor(n / ratio / factor) * factor for n in (height, width))
    elif h * w < minimum:
        ratio = sqrt(minimum / (height * width))
        h, w = (ceil(n * ratio / factor) * factor for n in (height, width))
    if min(h, w) < factor or not minimum <= h * w <= maximum:
        raise ValueError("No aligned image geometry within the requested pixel budget")
    return h, w


def view_size(width, height):
    h, w = smart_resize(height, width)
    return w, h


def jpeg_view(raw, profile=JPEG_PROFILE):
    qualities = {JPEG_PROFILE: 98, JPEG90_PROFILE: 90}
    if profile not in qualities:
        raise ValueError("Unknown model image profile")
    source_hash = sha256(raw).hexdigest()
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Only JPEG, PNG and WebP screenshots are supported")
            if image.width * image.height > 16_000_000:
                raise ValueError("Screenshot exceeds decoded pixel limit")
            if getattr(image, "n_frames", 1) != 1 or image.getexif().get(274, 1) != 1:
                raise ValueError("Animated or rotated screenshots require an explicit source view")
            source_size = image.size
            size = view_size(*source_size)
            pixels = image if image.mode == "RGB" else image.convert("RGB")
            if size != source_size:
                pixels = pixels.resize(size, Image.Resampling.BILINEAR)
            output = BytesIO()
            pixels.save(output, format="JPEG", quality=qualities[profile], subsampling=0, optimize=True)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Cannot decode screenshot for the model image view") from exc
    data = output.getvalue()
    return data, {"profile": profile, "source_sha256": source_hash,
        "view_sha256": sha256(data).hexdigest(), "source_bytes": len(raw), "view_bytes": len(data),
        "source_width": source_size[0], "source_height": source_size[1],
        "width": size[0], "height": size[1], "patch_size": FACTOR,
        "patches": size[0] * size[1] // FACTOR**2, "max_patches": MAX_PATCHES,
        "jpeg_quality": qualities[profile], "jpeg_subsampling": 0, "jpeg_optimize": True,
        "resampling": "pillow-bilinear", "pillow_version": Image.__version__,
        "mime": "image/jpeg", "billing_tokens": None}
