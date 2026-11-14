"""Versioned model-consumption views; source assets remain byte-for-byte unchanged."""
from io import BytesIO
from math import ceil, floor, sqrt

from PIL import Image, UnidentifiedImageError

from evonext.contracts.trajectory import ContractError, sha256
from evonext.evidence.packages import media_type

JPEG_PROFILE = "jpeg98-qwen32-patch980.pillow.v1"
JPEG90_PROFILE = "jpeg90-qwen32-patch980.pillow.v1"
SOURCE_PROFILE = "source.v1"
FACTOR, MAX_PATCHES = 32, 980


def profile_for_quality(quality):
    return {98: JPEG_PROFILE, 90: JPEG90_PROFILE}[quality]


def view_size(width, height):
    """Qwen geometry, matching EvoLoop's factor/min/max pixel rules."""
    if min(width, height) <= 0 or max(width, height) / min(width, height) > 200:
        raise ContractError("Unsupported screenshot aspect ratio")
    minimum, maximum = 4 * FACTOR**2, MAX_PATCHES * FACTOR**2
    w, h = (max(FACTOR, round(n / FACTOR) * FACTOR) for n in (width, height))
    if w * h > maximum:
        ratio = sqrt(width * height / maximum)
        w, h = (floor(n / ratio / FACTOR) * FACTOR for n in (width, height))
    elif w * h < minimum:
        ratio = sqrt(minimum / (width * height))
        w, h = (ceil(n * ratio / FACTOR) * FACTOR for n in (width, height))
    return w, h


def model_image(raw, profile=JPEG_PROFILE):
    source_hash = sha256(raw)
    if profile == SOURCE_PROFILE:
        return raw, {"profile": profile, "source_sha256": source_hash,
                     "view_sha256": source_hash, "source_bytes": len(raw), "view_bytes": len(raw),
                     "mime": media_type(raw)}
    qualities = {JPEG_PROFILE: 98, JPEG90_PROFILE: 90}
    if profile not in qualities:
        raise ContractError("Unknown model image profile")
    media_type(raw)
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.width * image.height > 16_000_000:
                raise ContractError("Screenshot exceeds decoded pixel limit")
            if getattr(image, "n_frames", 1) != 1 or image.getexif().get(274, 1) != 1:
                raise ContractError("Animated or rotated screenshots require an explicit source view")
            source_size = image.size
            size = view_size(*source_size)
            pixels = image.convert("RGB")
            if size != source_size:
                pixels = pixels.resize(size, Image.Resampling.BILINEAR)
            output = BytesIO()
            pixels.save(output, format="JPEG", quality=qualities[profile], subsampling=0, optimize=True)
    except ContractError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ContractError("Cannot decode screenshot for the model image view") from exc
    data = output.getvalue()
    return data, {"profile": profile, "source_sha256": source_hash,
        "view_sha256": sha256(data), "source_bytes": len(raw), "view_bytes": len(data),
        "source_width": source_size[0], "source_height": source_size[1],
        "width": size[0], "height": size[1], "patch_size": FACTOR,
        "patches": size[0] * size[1] // FACTOR**2, "max_patches": MAX_PATCHES,
        "jpeg_quality": qualities[profile], "jpeg_subsampling": 0, "jpeg_optimize": True,
        "resampling": "pillow-bilinear", "pillow_version": Image.__version__,
        "mime": "image/jpeg", "billing_tokens": None}
