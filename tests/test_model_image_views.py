"""Synthetic pixel-to-wire contracts; never call a model or change source evidence."""
import base64
from io import BytesIO

from PIL import Image, JpegImagePlugin
import pytest

from evonext.config import Settings
from evonext.contracts.trajectory import ContractError, Snapshot, encode_json, sha256
from evonext.evidence.image_views import (JPEG_PROFILE, JPEG90_PROFILE, SOURCE_PROFILE,
                                        model_image, view_size)
from evonext.evaluation.images import image_message
from evonext.evaluation.inputs import InputOptions, prepare_input
from evonext.evidence.service import EvidenceService
from evonext.evidence.store import MemoryAssets, MemorySnapshots


def picture(size=(1060, 2376), mode='RGB'):
    out = BytesIO()
    Image.new(mode, size, 'white').save(out, format='PNG')
    return out.getvalue()


@pytest.mark.parametrize('size', [(1060, 2376), (2376, 1060), (64, 64), (8, 8), (1, 200)])
def test_geometry_and_wire_metadata_preserve_source_bytes(size):
    raw = picture(size)
    original = bytes(raw)
    data, view = model_image(raw)
    with Image.open(BytesIO(data)) as image:
        assert image.format == 'JPEG' and image.mode == 'RGB'
        assert image.size == view_size(*size)
        assert JpegImagePlugin.get_sampling(image) == 0
    assert view['width'] % 32 == view['height'] % 32 == 0
    assert 4 <= view['patches'] <= 980
    assert view['source_sha256'] == sha256(original)
    assert view['view_sha256'] == sha256(data)
    assert view['source_bytes'] == len(raw) and view['view_bytes'] == len(data)
    assert view['billing_tokens'] is None
    assert raw == original and model_image(raw) == (data, view)


def test_geometry_matches_evoloop_phone_budget_and_quality_is_explicit():
    raw = picture()
    assert view_size(1060, 2376) == (640, 1472)
    for profile, quality in [(JPEG_PROFILE, 98), (JPEG90_PROFILE, 90)]:
        _, view = model_image(raw, profile)
        assert view['jpeg_quality'] == quality and view['patches'] == 920
        assert view['jpeg_subsampling'] == 0 and view['jpeg_optimize']
    assert Settings(demo=True, _env_file=None).model_image_quality == 98
    with pytest.raises(ValueError):
        Settings(demo=True, _env_file=None, model_image_quality=70)
    with pytest.raises(ContractError, match='Unknown'):
        model_image(raw, 'unreviewed-uploaded-transform')


@pytest.mark.parametrize('mode', ['RGBA', 'L'])
def test_supported_pixel_modes_become_rgb(mode):
    data, _ = model_image(picture((64, 64), mode))
    assert Image.open(BytesIO(data)).mode == 'RGB'


def test_corrupt_rotated_extreme_and_oversized_inputs_do_not_fall_back_to_raw():
    with pytest.raises(ContractError, match='decode'):
        model_image(b'\x89PNG\r\n\x1a\nsynthetic-corrupt')
    with pytest.raises(ContractError, match='aspect ratio'):
        model_image(picture((1, 201)))
    with pytest.raises(ContractError, match='pixel limit'):
        model_image(picture((4001, 4000)))
    image = Image.new('RGB', (64, 96), 'white')
    exif = Image.Exif()
    exif[274] = 6
    out = BytesIO()
    image.save(out, format='JPEG', exif=exif)
    with pytest.raises(ContractError, match='rotated'):
        model_image(out.getvalue())


def test_evaluation_markers_precede_resize_and_receipt_binds_actual_wire_bytes():
    raw = picture()
    assets, repo = MemoryAssets(), MemorySnapshots()
    digest = assets.put(raw)
    step = {'image': 'images/source.png', 'runtime': {'dispatched_action': {
        'action': 'click', 'coordinate': [500, 500], 'coordinate_space': 'normalized_1000'}}}
    snap = Snapshot.create(encode_json({'task_id': 'synthetic-derived-marker',
        'instruction': 'Inspect', 'traj': [step]}), media={'images/source.png': digest})
    repo.put(snap)
    evidence = EvidenceService(repo, assets, Settings(demo=True, _env_file=None))
    descriptor = prepare_input(snap, InputOptions())['images'][0]
    parts, receipt = image_message(snap, descriptor, evidence, 'auto')
    url = parts[-1]['image_url']['url']
    assert url.startswith('data:image/jpeg;base64,')
    wire = base64.b64decode(url.split(',', 1)[1], validate=True)
    assert receipt['sha256'] == digest
    assert receipt['view_sha256'] == receipt['image_view']['view_sha256'] == sha256(wire)
    assert receipt['image_view']['source_sha256'] == digest
    assert receipt['image_view']['rendered_sha256'] != digest
    assert receipt['marker_source'] == 'dispatched'
    assert receipt['image_view']['patches'] == 920
    assert 'source coordinates unchanged' in parts[0]['text']
    assert '"source_width":1060' in parts[0]['text'] and '"width":640' in parts[0]['text']
    assert evidence.read_media(snap.id, 'images/source.png') == raw
    # Frozen historical operations retain their original raw profile.
    original, legacy = image_message(snap, descriptor, evidence, 'off', image_profile=SOURCE_PROFILE)
    assert base64.b64decode(original[-1]['image_url']['url'].split(',', 1)[1]) == raw
    assert 'image_view' not in legacy and legacy['view_sha256'] == digest


def test_reviewed_quality_can_be_selected_through_environment(monkeypatch):
    for quality in (90, 98):
        monkeypatch.setenv('EVONEXT_MODEL_IMAGE_QUALITY', str(quality))
        assert Settings(demo=True, _env_file=None).model_image_quality == quality
    monkeypatch.setenv('EVONEXT_MODEL_IMAGE_QUALITY', '95')
    with pytest.raises(ValueError):
        Settings(demo=True, _env_file=None)


def test_evaluation_freezes_quality_and_keeps_legacy_payloads_on_original_bytes():
    from evonext.evaluation.service import EvalRequest, submit, run, keys
    from test_workshop_authoring import SyntheticLedger, model
    assets, repo = MemoryAssets(), MemorySnapshots()
    raw = picture((64, 96))
    digest = assets.put(raw)
    snap = Snapshot.create(encode_json({'task_id': 'synthetic-evaluation-profile',
        'instruction': 'Inspect', 'traj': [{'image': 'images/source.png'}]}),
        media={'images/source.png': digest})
    repo.put(snap)
    evidence = EvidenceService(repo, assets, Settings(demo=True, _env_file=None))
    reply = {'checks': [{'check_id': 'task_goal', 'judgment': 'pass', 'reason': 'Synthetic observation',
        'evidence_refs': [snap.id + '/steps/0/image']}], 'findings': []}
    for legacy in (False, True):
        ledger = SyntheticLedger()
        request = EvalRequest(operation_id='synthetic-frozen-evaluation', investigation='off')
        submit(snap, request, ledger, image_profile=JPEG90_PROFILE)
        if legacy:
            # An operation persisted before profiles existed must retain its PNG payload.
            del ledger.rows[keys(request.operation_id)[0]]['payload']['image_profile']
        # Config updates and duplicate deliveries preserve the original frozen profile.
        assert submit(snap, request, ledger)['status'] == 'pending'
        frozen = ledger.get(keys(request.operation_id)[0])['payload']
        assert frozen.get('image_profile', SOURCE_PROFILE) == (SOURCE_PROFILE if legacy else JPEG90_PROFILE)
        gateway, calls = model([reply])
        try:
            result = run(request.operation_id, evidence, ledger, gateway)
            assert result['native_result']['image_profile'] == (SOURCE_PROFILE if legacy else JPEG90_PROFILE)
            receipt = result['native_result']['media_receipts'][0]
            if not legacy:
                assert receipt['image_view']['jpeg_quality'] == 90
            url = calls[0]['messages'][1]['content'][-1]['image_url']['url']
            assert url.startswith('data:image/png' if legacy else 'data:image/jpeg')
            assert run(request.operation_id, evidence, ledger, gateway) == result and len(calls) == 1
        finally:
            gateway.close()
