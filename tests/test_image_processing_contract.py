"""Synthetic geometry/codec contracts shared by the two image consumers."""
from hashlib import sha256
from io import BytesIO
import random

from PIL import Image, JpegImagePlugin
import pytest

from evonext.evidence.image_processing import JPEG_PROFILE, JPEG90_PROFILE, jpeg_view, smart_resize


@pytest.mark.parametrize('height,width,factor,expected', [
    (2376, 1060, 32, (1472, 640)), (1060, 2376, 32, (640, 1472)),
    (1472, 640, 32, (1472, 640)), (64, 32, 32, (96, 64)),
    (720, 1280, 32, (704, 1280)), (70, 110, 28, (56, 112)),
])
def test_frozen_geometry_vectors(height, width, factor, expected):
    assert smart_resize(height, width, factor) == expected


@pytest.mark.parametrize('arguments', [
    (0, 100), (-1, 100), (100.0, 100), (True, 100), (100, 100, 0),
    (100, 100, 1.5), (100, 100, 32, 4096, 1024),
    (100, 100, 32, 0, 4096), (1, 201),
    (1, 200, 32, 4096, 4096),
])
def test_invalid_or_unrepresentable_bounds_never_escape_budget(arguments):
    with pytest.raises(ValueError):
        smart_resize(*arguments)


def test_geometry_invariants_cover_many_orientations_and_boundaries():
    rng = random.Random(17)
    for _ in range(400):
        h, w = rng.randint(1, 6000), rng.randint(1, 6000)
        if max(h, w) / min(h, w) > 200:
            continue
        rh, rw = smart_resize(h, w)
        assert rh % 32 == rw % 32 == 0
        assert min(rh, rw) >= 32
        assert 4 <= rh * rw // 1024 <= 980
        assert smart_resize(w, h) == (rw, rh)


@pytest.mark.parametrize('profile,quality', [(JPEG_PROFILE, 98), (JPEG90_PROFILE, 90)])
def test_codec_actual_bytes_match_metadata_and_source_is_unchanged(profile, quality):
    source = BytesIO()
    image = Image.new('RGB', (1060, 2376), 'white')
    image.paste('red', (64, 80, 256, 500))
    image.save(source, format='PNG')
    raw = source.getvalue()
    data, view = jpeg_view(raw, profile)
    with Image.open(BytesIO(data)) as encoded:
        assert encoded.format == 'JPEG' and encoded.mode == 'RGB'
        assert encoded.size == (640, 1472)
        assert JpegImagePlugin.get_sampling(encoded) == 0
    assert view['source_sha256'] == sha256(raw).hexdigest()
    assert view['view_sha256'] == sha256(data).hexdigest()
    assert view['source_bytes'] == len(raw) and view['view_bytes'] == len(data)
    assert view['jpeg_quality'] == quality and view['billing_tokens'] is None
    assert view['resampling'] == 'pillow-bilinear' and view['patches'] == 920
    assert source.getvalue() == raw
    assert jpeg_view(raw, profile) == (data, view)
