import copy
import io
import json
import stat
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from evonext.api import create_app
from evonext.config import Settings
from evonext.domain import ContractError, EvaluationRecord, Snapshot, encode_json, load_json, sha256
from evonext.legacy import BridgeUncertain, LegacyClient
from evonext.models import ModelGateway
from evonext.packages import export_bundle, import_bundle, safe_path
from evonext.storage import MemoryAssets, MemorySnapshots
from evonext.telemetry import Tracing
from evonext.verification import verify_snapshot

# Synthetic bytes, not production evidence and not a success oracle.
PNG = bytes.fromhex('89504e470d0a1a0a') + b'synthetic-image-fixture'


def settings(**kwargs):
    return Settings(demo=True, _env_file=None, **kwargs)


def task(image=None):
    return {'task_id': '900719925474099312345', 'instruction': 'Synthetic task; do not execute.',
            'traj': [{'index': 0, 'step_id': 'original-17', 'source_index': 17, 'image': image,
                      'value': {'raw_model_output': '  original\ntext  ',
                                'tool_call': {'name': 'mobile_use', 'arguments': {'action': 'wait'}},
                                'execution_result': {'status': 'unknown'}, 'future_field': {'keep': 1}},
                      'runtime': {'dispatched_action': None}}],
            '_version_info': {'version_number': 0}, 'future_extension': [1, {'null': None}]}


def make_zip(entries):
    output = io.BytesIO()
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return output.getvalue()


def bundle(image=True, metadata=None):
    document = task('images/a.png' if image else None)
    raw = json.dumps(document, ensure_ascii=False, indent=2).encode()
    meta = json.dumps(metadata or {'schema_version': 'opencua-offline.v1', 'do_not_train': True}).encode()
    entries = [('trajectory.json', raw), ('metadata.json', meta)]
    if image:
        entries.append(('images/a.png', PNG))
    return make_zip(entries), raw, meta


@pytest.mark.parametrize('raw', [b'[]', b'null', b'1', b'{"x":NaN}', b'{"x":Infinity}',
                                 b'{"x":-Infinity}', b'{"x":1,"x":2}',
                                 b'{"x":{"a":1,"a":2}}', b'\xff', b'{'])
def test_reject_ambiguous_json(raw):
    with pytest.raises(ContractError):
        load_json(raw)


@pytest.mark.parametrize('mutation', [
    lambda x: x.update(task_id=9007199254740993),
    lambda x: x.update(task_id=True),
    lambda x: x.update(task_id=''),
    lambda x: x.pop('traj'),
    lambda x: x.update(traj='not-an-array'),
    lambda x: x['traj'][0].update(value='not-an-object'),
    lambda x: x['traj'][0].update(image=42),
])
def test_trajectory_validation_does_not_coerce(mutation):
    document = task()
    mutation(document)
    with pytest.raises(ContractError):
        Snapshot.create(encode_json(document))


def test_snapshot_retains_all_source_fields_and_does_not_infer_review():
    original = task()
    raw = json.dumps(original, indent=4).encode()
    snapshot = Snapshot.create(raw)
    assert snapshot.trajectory_json == raw
    assert snapshot.document == original
    assert snapshot.summary()['source_version'] == 0
    assert 'reviewed' not in snapshot.document
    assert 'action' not in snapshot.document['traj'][0]['value']
    assert snapshot.document['traj'][0]['source_index'] == 17
    assert Snapshot.create(encode_json(original)).id != snapshot.id  # Byte identity, not semantic equivalence.


def test_store_is_idempotent_and_copy_isolated():
    store = MemorySnapshots()
    snapshot = Snapshot.create(encode_json(task()))
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: store.put(snapshot), range(20)))
    assert len(set(results)) == 1
    assert len(store.list()) == 1
    read = store.get(snapshot.id)
    read.media['bad'] = '0' * 64
    assert not store.get(snapshot.id).media


def test_bundle_roundtrip_preserves_original_json_and_media_bytes():
    raw, trajectory, metadata = bundle()
    assets = MemoryAssets()
    snapshot = import_bundle(raw, assets, settings())
    exported = export_bundle(snapshot, assets, 1024 * 1024)
    with ZipFile(io.BytesIO(exported)) as archive:
        assert archive.read('trajectory.json') == trajectory
        assert archive.read('metadata.json') == metadata
        assert archive.read('images/a.png') == PNG
    again = import_bundle(exported, MemoryAssets(), settings())
    assert again.id == snapshot.id


@pytest.mark.parametrize('path', ['../escape', '/root', 'C:/file', 'images/../escape',
                                  'images\\escape', './trajectory.json', 'images//a.png', ''])
def test_unsafe_paths(path):
    assert not safe_path(path)


def test_symlink_and_unknown_member_are_rejected():
    info = ZipInfo('images/link.png')
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    for entry in [(info, b'/etc/passwd'), ('secret.txt', b'not accepted')]:
        with pytest.raises(ContractError):
            import_bundle(make_zip([('trajectory.json', encode_json(task())),
                                    ('metadata.json', b'{}'), entry]), MemoryAssets(), settings())


def test_duplicate_zip_member_rejected():
    with pytest.warns(UserWarning):
        raw = make_zip([('trajectory.json', encode_json(task())),
                        ('trajectory.json', encode_json(task())), ('metadata.json', b'{}')])
    with pytest.raises(ContractError):
        import_bundle(raw, MemoryAssets(), settings())


@pytest.mark.parametrize('metadata', [{'image_hashes': {'images/a.png': '0' * 64}},
                                      {'image_hashes': {'images/missing.png': '0' * 64}},
                                      {'image_hashes': []}])
def test_declared_hash_rejected_before_storage_write(metadata):
    raw, _, _ = bundle(metadata=metadata)
    assets = MemoryAssets()
    with pytest.raises(ContractError):
        import_bundle(raw, assets, settings())
    assert assets.items == {}


def test_declared_hash_verified():
    raw, _, _ = bundle(metadata={'image_hashes': {'images/a.png': sha256(PNG)}})
    snapshot = import_bundle(raw, MemoryAssets(), settings())
    assert snapshot.media['images/a.png'] == sha256(PNG)


def test_compressed_expansion_is_bounded():
    raw = make_zip([('trajectory.json', b'x' * 2000), ('metadata.json', b'{}')])
    with pytest.raises(ContractError):
        import_bundle(raw, MemoryAssets(), settings(max_file_bytes=1024, max_upload_bytes=2048))


def test_missing_media_never_fetches_url():
    snapshot = Snapshot.create(encode_json(task('https://example.invalid/private.png')))
    with pytest.raises(ContractError):
        export_bundle(snapshot, MemoryAssets(), 1024 * 1024)
    raw = make_zip([('trajectory.json', snapshot.trajectory_json), ('metadata.json', b'{}')])
    with pytest.raises(ContractError):
        import_bundle(raw, MemoryAssets(), settings())


def test_missing_metadata_is_explicit_error():
    with pytest.raises(ContractError):
        import_bundle(make_zip([('trajectory.json', encode_json(task()))]), MemoryAssets(), settings())


def test_corrupted_media_never_verifies():
    assets = MemoryAssets()
    digest = assets.put(PNG)
    assets.items[digest] = b'changed'
    with pytest.raises(ContractError):
        assets.get(digest)


def test_production_auth_required_and_legacy_collection_guard(monkeypatch):
    monkeypatch.delenv('EVONEXT_API_KEY', raising=False)
    monkeypatch.delenv('EVONEXT_DEMO', raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    with pytest.raises(ValidationError):
        settings(mongo_collection='tasks_latest')
    with pytest.raises(ValidationError):
        settings(legacy_writes=True)


def test_api_auth_and_query_errors_do_not_echo_secret_input():
    s = Settings(_env_file=None, api_key=SecretStr('test-only'))
    with TestClient(create_app(s, MemorySnapshots(), MemoryAssets())) as client:
        assert client.get('/api/v1/snapshots').status_code == 401
        assert client.get('/api/v1/snapshots', headers={'X-API-Key': 'wrong'}).status_code == 401
        response = client.get('/api/v1/snapshots?limit=private-sentinel', headers={'X-API-Key': 'test-only'})
        assert response.status_code == 422
        assert 'private-sentinel' not in response.text
        assert client.get('/health/live').status_code == 200


def test_api_import_inspect_download_full_roundtrip():
    raw, trajectory, _ = bundle()
    with TestClient(create_app(settings())) as client:
        response = client.post('/api/v1/bundles', content=raw)
        assert response.status_code == 201
        identity = response.json()['snapshot_id']
        assert client.post('/api/v1/bundles', content=raw).json()['snapshot_id'] == identity
        assert len(client.get('/api/v1/snapshots').json()['items']) == 1
        detail = client.get('/api/v1/snapshots/' + identity).json()
        assert detail['trajectory'] == load_json(trajectory)
        assert detail['missing_media'] == []
        assert client.get(f'/api/v1/snapshots/{identity}/trajectory').content == trajectory
        image = client.get(f'/api/v1/snapshots/{identity}/media?path=images/a.png')
        assert image.content == PNG
        assert image.headers['x-content-type-options'] == 'nosniff'
        assert client.get(f'/api/v1/snapshots/{identity}/media?path=../anything').status_code == 404
        export = client.get(f'/api/v1/snapshots/{identity}/bundle')
        assert export.status_code == 200
        assert client.post('/api/v1/bundles', content=export.content).json()['snapshot_id'] == identity


def test_invalid_import_never_publishes_snapshot():
    repo, assets = MemorySnapshots(), MemoryAssets()
    with TestClient(create_app(settings(), repo, assets)) as client:
        assert client.post('/api/v1/bundles', content=b'not-a-zip').status_code == 400
        assert not repo.list()
        assert not assets.items
        assert client.post('/api/v1/snapshots', json={'trajectory': task(), 'ignored': 1}).status_code == 400


def test_json_import_preserves_unknowns_but_does_not_claim_media():
    document = task('unbound.png')
    with TestClient(create_app(settings())) as client:
        result = client.post('/api/v1/snapshots', json={'trajectory': document, 'metadata': {'new': 1}})
        assert result.status_code == 201
        assert not result.json()['media_complete']
        identity = result.json()['snapshot_id']
        detail = client.get('/api/v1/snapshots/' + identity).json()
        assert detail['trajectory'] == document
        assert detail['metadata'] == {'new': 1}
        assert client.get(f'/api/v1/snapshots/{identity}/bundle').status_code == 400


def test_api_body_limit():
    s = settings(max_file_bytes=100, max_upload_bytes=200)
    with TestClient(create_app(s)) as client:
        assert client.post('/api/v1/snapshots', content=b'x' * 101).status_code == 413


def test_api_pagination_includes_every_snapshot_once():
    with TestClient(create_app(settings())) as client:
        ids = set()
        for i in range(5):
            document = task()
            document['task_id'] = str(i)
            ids.add(client.post('/api/v1/snapshots', json={'trajectory': document}).json()['snapshot_id'])
        collected, cursor = [], ''
        while True:
            page = client.get('/api/v1/snapshots', params={'limit': 2, 'after': cursor}).json()
            collected.extend(item['snapshot_id'] for item in page['items'])
            cursor = page['next_cursor']
            if not cursor:
                break
        assert set(collected) == ids and len(collected) == len(ids)


def legacy_settings(**kwargs):
    return Settings(_env_file=None, api_key=SecretStr('synthetic-key'),
                    legacy_base_url='https://legacy.example.invalid',
                    legacy_api_key=SecretStr('synthetic-legacy-key'), **kwargs)


def test_legacy_fixed_version_zero_and_identity():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=task())
    bridge = LegacyClient(legacy_settings(), httpx.MockTransport(handler))
    try:
        snapshot = bridge.fetch(task()['task_id'], 0)
        assert snapshot.summary()['source_version'] == 0
        assert seen[0].url.params['version'] == '0'
        assert seen[0].headers['X-API-Key'] == 'synthetic-legacy-key'
        assert len(seen) == 1
    finally:
        bridge.close()


@pytest.mark.parametrize('document', [dict(task(), task_id='different'),
                                       dict(task(), _version_info={'version_number': 1}),
                                       dict(task(), _version_info={})])
def test_legacy_mismatch_no_latest_fallback(document):
    bridge = LegacyClient(legacy_settings(), httpx.MockTransport(lambda _: httpx.Response(200, json=document)))
    try:
        with pytest.raises(ContractError):
            bridge.fetch(task()['task_id'], 0)
    finally:
        bridge.close()


def test_legacy_preview_no_write_and_publish_requires_two_controls():
    seen = []
    bridge = LegacyClient(legacy_settings(), httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200, json={})))
    try:
        snapshot = Snapshot.create(encode_json(task()))
        preview = bridge.publish(snapshot, MemoryAssets())
        assert preview['status'] == 'preview_only' and not preview['lossless']
        assert preview['metadata_transferred'] is False
        with pytest.raises(PermissionError):
            bridge.publish(snapshot, MemoryAssets(), dry_run=False, allow_projection_loss=True)
        assert seen == []
    finally:
        bridge.close()


def test_legacy_upload_timeout_is_uncertain_not_retried():
    seen = []
    def timeout(request):
        seen.append(request)
        raise httpx.ReadTimeout('synthetic', request=request)
    bridge = LegacyClient(legacy_settings(legacy_writes=True), httpx.MockTransport(timeout))
    try:
        with pytest.raises(BridgeUncertain):
            bridge.publish(Snapshot.create(encode_json(task())), MemoryAssets(),
                           dry_run=False, allow_projection_loss=True)
        assert len(seen) == 1
        assert b'"existing_task_mode": "skip"' in seen[0].content
        assert b'"auto_evaluate": false' in seen[0].content
    finally:
        bridge.close()


def test_legacy_action_is_not_silently_converted():
    document = task()
    document['traj'][0]['value']['code'] = 'never_execute()'
    bridge = LegacyClient(legacy_settings(), httpx.MockTransport(lambda _: pytest.fail('No HTTP expected')))
    try:
        with pytest.raises(ContractError):
            bridge.publish(Snapshot.create(encode_json(document)), MemoryAssets())
    finally:
        bridge.close()


class FakeObservation:
    def __init__(self):
        self.updates = []
    def update(self, **kwargs):
        self.updates.append(kwargs)


class FakeTracingClient:
    def __init__(self, fail_start=False):
        self.observation = FakeObservation()
        self.fail_start = fail_start
    @contextmanager
    def start_as_current_observation(self, **kwargs):
        if self.fail_start:
            raise RuntimeError('synthetic tracing outage')
        yield self.observation
    def get_current_trace_id(self):
        return 'synthetic-trace'
    def flush(self):
        return None


def test_model_call_traced_with_content_disabled_by_default():
    s = settings(model_name='synthetic-model', model_base_url='https://model.example.invalid/v1',
                 model_api_key=SecretStr('synthetic-model-key'))
    seen, trace_client = [], FakeTracingClient()
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={'model': 'observed-revision', 'choices': [],
                                          'usage': {'prompt_tokens': 5, 'completion_tokens': 2}})
    gateway = ModelGateway(s, httpx.MockTransport(handler), Tracing(s, trace_client))
    try:
        result = gateway.complete([{'role': 'user', 'content': 'private-sentinel'}], snapshot_id='source')
        assert str(seen[0].url) == 'https://model.example.invalid/v1/chat/completions'
        assert result['trace_id'] == 'synthetic-trace'
        assert result['observed_model'] == 'observed-revision'
        assert result['usage']['prompt_tokens'] == 5
        assert 'private-sentinel' not in str(trace_client.observation.updates)
    finally:
        gateway.close()


def test_tracing_outage_does_not_retry_or_swallow_model_error():
    s = settings(model_name='test', model_base_url='https://model.example.invalid/v1',
                 model_api_key=SecretStr('synthetic-model-key'))
    seen = []
    gateway = ModelGateway(s, httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(503)),
                           Tracing(s, FakeTracingClient(fail_start=True)))
    try:
        with pytest.raises(httpx.HTTPStatusError):
            gateway.complete([{'role': 'user', 'content': 'synthetic'}])
        assert len(seen) == 1
    finally:
        gateway.close()


class FakeLedger:
    def __init__(self):
        self.items = {}
    def record(self, operation_id, snapshot_id, kind, payload):
        value = (snapshot_id, kind, copy.deepcopy(payload))
        if operation_id in self.items and self.items[operation_id] != value:
            raise ContractError('conflict')
        self.items.setdefault(operation_id, value)


def test_verification_idempotent_and_not_an_outcome_judge():
    repo, assets, ledger = MemorySnapshots(), MemoryAssets(), FakeLedger()
    snapshot = Snapshot.create(encode_json(task()))
    repo.put(snapshot)
    first = verify_snapshot(snapshot.id, repo, assets, ledger)
    assert verify_snapshot(snapshot.id, repo, assets, ledger) == first
    assert len(ledger.items) == 1
    assert first['result']['agent_outcome'] == 'not_assessed'


def test_evaluation_error_and_business_failure_are_separate():
    record = EvaluationRecord(record_id='synthetic', snapshot_id='snapshot', grader_id='grader',
                              grader_version='v1', execution_status='error', outcome='not_assessed', checks=[])
    assert record.outcome != 'failure'


def test_postgres_model_is_namespaced_without_trajectory_truth():
    sqlalchemy = pytest.importorskip('sqlalchemy')
    from evonext.ledger import receipts
    from sqlalchemy.dialects import postgresql
    sql = str(sqlalchemy.schema.CreateTable(receipts).compile(dialect=postgresql.dialect()))
    assert 'evonext.operation_receipts' in sql
    assert 'JSONB' in sql
    assert 'traj' not in receipts.c


def test_sidecar_version_and_zero_survive_read_projection():
    document = task()
    document.pop('_version_info')
    snapshot = Snapshot.create(encode_json(document), encode_json({'_version_info': {'version_number': 0}}))
    assert snapshot.summary()['source_version'] == 0
    assert '_version_info' not in snapshot.document


def test_conflicting_versions_are_not_guessed():
    snapshot = Snapshot.create(encode_json(task()), encode_json({'_version_info': {'version_number': 3}}))
    assert snapshot.summary()['source_version'] is None


def test_bad_unicode_and_hash_types_are_contract_errors():
    with pytest.raises(ContractError):
        Snapshot.create(b'{"task_id":"id","instruction":"\\ud800","traj":[]}')
    raw, _, _ = bundle(metadata={'image_hashes': {'images/a.png': {'not': 'a-string'}}})
    with pytest.raises(ContractError):
        import_bundle(raw, MemoryAssets(), settings())


def test_openapi_declares_json_and_zip_request_bodies():
    with TestClient(create_app(settings())) as client:
        schema = client.get('/openapi.json').json()
        assert 'application/json' in schema['paths']['/api/v1/snapshots']['post']['requestBody']['content']
        assert 'application/zip' in schema['paths']['/api/v1/bundles']['post']['requestBody']['content']


def test_real_langfuse_sdk_shape_without_network():
    module = pytest.importorskip('langfuse')
    client = module.Langfuse(public_key='pk-lf-synthetic', secret_key='sk-lf-synthetic',
                            base_url='http://127.0.0.1:9', tracing_enabled=False)
    tracing = Tracing(settings(), client)
    with tracing.generation('synthetic', {'snapshot_id': 'synthetic'}) as observation:
        tracing.update(observation, input='synthetic', output='synthetic')
    tracing.close()


def test_celery_configuration_without_broker_connection(monkeypatch):
    pytest.importorskip('celery')
    pytest.importorskip('pymongo')
    monkeypatch.setenv('EVONEXT_API_KEY', 'synthetic-ci-key')
    monkeypatch.setenv('EVONEXT_DEMO', 'false')
    from evonext.worker import app, verify
    assert app.conf.task_serializer == 'json'
    assert app.conf.task_ignore_result is True
    assert app.conf.task_default_queue == 'evonext.bulk'
    assert verify.name == 'evonext.verify_snapshot'
