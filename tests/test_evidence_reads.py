"""Synthetic access-path regressions; collection doubles do not prove real Mongo behavior."""
import copy
import hashlib
import io
import json
import sys
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from evonext.app.api import create_app
from evonext.config import Settings
from evonext.contracts import trajectory as contract
from evonext.contracts.trajectory import ContractError, Snapshot, encode_json, sha256
from evonext.evidence.index import SnapshotIndex, StoredEvidenceError
from evonext.evidence.service import EvidenceService
from evonext.evidence.store import MemoryAssets, MongoSnapshots

PNG = b'\x89PNG\r\n\x1a\nsynthetic-read-path'


def settings(**kwargs):
    return Settings(demo=True, _env_file=None, **kwargs)


def synthetic_snapshot():
    document = {'task_id': '900719925474099312345', 'instruction': 'synthetic ' * 100,
                '_version_info': {'version_number': 0}, 'unknown': {'retain': True},
                'traj': [{'step_id': 'step-17', 'image': 'images/a.png',
                          'value': {'raw_model_output': '  raw\n', 'unknown': [1]},
                          'runtime': {'dispatched_action': {'action': 'wait'},
                                      'execution_result': {'status': 'unknown'}}}]}
    return Snapshot.create(json.dumps(document, indent=2).encode(),
                           b'{ "synthetic": true }', {'images/a.png': sha256(PNG)})


class ProjectedCollection:
    """Apply field projection and refuse full reads on the modern path."""
    def __init__(self, snapshot, legacy=False):
        self.row = {'_id': snapshot.id, 'trajectory_json': snapshot.trajectory_json.decode(),
                    'metadata_json': snapshot.metadata_json.decode(), 'media': snapshot.media,
                    'summary': snapshot.summary()}
        if not legacy:
            self.row['index'] = SnapshotIndex.from_snapshot(snapshot).stored()
        self.reads = []
        self.legacy = legacy

    def find_one(self, query, projection=None):
        self.reads.append(projection)
        if query['_id'] != self.row['_id']:
            return None
        if projection is None:
            assert self.legacy, 'modern lightweight path attempted a full read'
            return copy.deepcopy(self.row)
        return copy.deepcopy({k: v for k, v in self.row.items() if k == '_id' or projection.get(k)})

    def update_one(self, *args, **kwargs):
        pytest.fail('a read must not persist or migrate a wrapper')


class BorrowedClient:
    def __init__(self, collection):
        self.collection = collection
        self.closed = False

    def __getitem__(self, key):
        return self

    def find_one(self, *args, **kwargs):
        return self.collection.find_one(*args, **kwargs)

    def update_one(self, *args, **kwargs):
        return self.collection.update_one(*args, **kwargs)

    def close(self):
        self.closed = True


def repository(snapshot, legacy=False):
    collection = ProjectedCollection(snapshot, legacy)
    client = BorrowedClient(collection)
    return MongoSnapshots(settings(), client=client), collection


def test_snapshot_parses_and_hashes_once_and_public_views_cannot_change_identity(monkeypatch):
    calls = {'parse': 0, 'hash': 0}
    original_load, original_hash = contract.load_json, contract.sha256

    def counted_load(raw):
        calls['parse'] += 1
        return original_load(raw)

    def counted_hash(raw):
        calls['hash'] += 1
        return original_hash(raw)

    monkeypatch.setattr(contract, 'load_json', counted_load)
    monkeypatch.setattr(contract, 'sha256', counted_hash)
    snapshot = synthetic_snapshot()
    initial = dict(calls)
    assert initial == {'parse': 2, 'hash': 3}
    identity, raw = snapshot.id, snapshot.trajectory_json
    for _ in range(3):
        snapshot.document['traj'][0]['value']['unknown'].append('changed')
        snapshot.metadata['synthetic'] = False
        snapshot.media['images/a.png'] = '0' * 64
        snapshot.manifest['media'].clear()
        snapshot.summary()['task_id'] = 'changed'
        assert snapshot.id == identity
    assert calls == initial
    assert snapshot.trajectory_json == raw
    assert snapshot.document['traj'][0]['value']['unknown'] == [1]
    assert snapshot.metadata == {'synthetic': True}
    expected_manifest = {'profile': 'evonext.snapshot-bytes.v1',
                         'trajectory_sha256': hashlib.sha256(raw).hexdigest(),
                         'metadata_sha256': hashlib.sha256(snapshot.metadata_json).hexdigest(),
                         'media': {'images/a.png': hashlib.sha256(PNG).hexdigest()}}
    assert identity == hashlib.sha256(json.dumps(expected_manifest, sort_keys=True,
        separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


@pytest.mark.parametrize('legacy', [False, True])
def test_header_and_media_access_have_explicit_modern_and_legacy_paths(monkeypatch, legacy):
    snapshot = synthetic_snapshot()
    repo, collection = repository(snapshot, legacy)
    assets = MemoryAssets()
    assets.put(PNG)
    if not legacy:
        monkeypatch.setattr(contract, 'load_json', lambda *_: pytest.fail('raw JSON was parsed'))
    with TestClient(create_app(settings(), repo, assets)) as client:
        header = client.get(f'/api/v1/snapshots/{snapshot.id}/header')
        assert header.status_code == 200
        assert header.json()['instruction'] == 'synthetic ' * 100
        assert header.json()['source_version'] == 0
        assert 'trajectory' not in header.json()
        assert 'metadata' not in header.json()
        image = client.get(f'/api/v1/snapshots/{snapshot.id}/media', params={'path': 'images/a.png'})
        assert image.status_code == 200
        assert image.content == PNG
        assert client.get(f'/api/v1/snapshots/{snapshot.id}/media',
                          params={'path': sha256(PNG)}).status_code == 404
        assert client.get(f'/api/v1/snapshots/{"f" * 64}/header').status_code == 404
        assert client.get('/api/v1/snapshots/invalid/header').status_code == 404
    if legacy:
        assert collection.reads[:4] == [{'index': 1}, None, {'index': 1}, None]
    else:
        assert all(projection == {'index': 1} for projection in collection.reads)


@pytest.mark.parametrize('mutation', [
    lambda row: row['index']['manifest']['media'].update({'images/a.png': '0' * 64}),
    lambda row: row['index'].update(profile='unknown'),
    lambda row: row['index'].update(header=None),
    lambda row: row.update(index=None),
])
def test_corrupt_index_never_falls_back_to_other_evidence(mutation):
    snapshot = synthetic_snapshot()
    repo, collection = repository(snapshot)
    mutation(collection.row)
    with pytest.raises(StoredEvidenceError):
        repo.get_index(snapshot.id)
    assert collection.reads == [{'index': 1}]
    with TestClient(create_app(settings(), repo, MemoryAssets())) as client:
        assert client.get(f'/api/v1/snapshots/{snapshot.id}/header').status_code == 500


def test_raw_verification_is_separate_from_manifest_and_bound_media_verification():
    snapshot = synthetic_snapshot()
    repo, collection = repository(snapshot)
    index = repo.get_index(snapshot.id)
    assert index.raw_json_verified is False
    assets = MemoryAssets()
    assets.put(PNG)
    assets.items[sha256(PNG)] = b'corrupt'
    service = EvidenceService(repo, assets, settings())
    with pytest.raises(StoredEvidenceError):
        service.read_media(snapshot.id, 'images/a.png')
    collection.legacy = True
    collection.row['trajectory_json'] = collection.row['trajectory_json'].replace('step-17', 'step-18')
    with pytest.raises(StoredEvidenceError):
        repo.get(snapshot.id)


def test_legacy_fallback_verifies_raw_json_and_does_not_repair():
    snapshot = synthetic_snapshot()
    repo, collection = repository(snapshot, legacy=True)
    assert repo.get_index(snapshot.id).raw_json_verified is True
    assert 'index' not in collection.row
    collection.row['metadata_json'] = '{}'
    with pytest.raises(StoredEvidenceError):
        repo.get_index(snapshot.id)
    repo.close()
    assert not repo.client.closed


def test_json_input_is_semantic_while_zip_members_keep_original_bytes():
    from evonext.evidence.store import MemorySnapshots
    snapshot = synthetic_snapshot()
    service = EvidenceService(MemorySnapshots(), MemoryAssets(), settings())
    envelope = b'{ "trajectory": ' + snapshot.trajectory_json + b', "metadata": { "synthetic": true }}'
    normalized = service.import_json(envelope)
    assert normalized.document == snapshot.document
    assert normalized.trajectory_json == encode_json(snapshot.document)
    assert normalized.trajectory_json != snapshot.trajectory_json
    archive_bytes = io.BytesIO()
    with ZipFile(archive_bytes, 'w') as archive:
        archive.writestr('trajectory.json', snapshot.trajectory_json)
        archive.writestr('metadata.json', snapshot.metadata_json)
        archive.writestr('images/a.png', PNG)
    imported = service.import_zip(archive_bytes.getvalue())
    assert imported.id == snapshot.id
    with ZipFile(io.BytesIO(service.export(imported))) as archive:
        assert archive.read('trajectory.json') == snapshot.trajectory_json
        assert archive.read('metadata.json') == snapshot.metadata_json
        assert archive.read('images/a.png') == PNG


def test_ready_reuses_one_ledger_and_shutdown_closes_only_owned_resources(monkeypatch):
    from evonext.evidence.store import MemorySnapshots
    counts = {'created': 0, 'ping': 0, 'closed': 0}

    class Ledger:
        def __init__(self, dsn):
            counts['created'] += 1

        def ping(self):
            counts['ping'] += 1

        def close(self):
            counts['closed'] += 1

    # This checks host lifecycle only; it does not replace the optional SQL SDK/real-PG checks.
    monkeypatch.setitem(sys.modules, 'evonext.operations.ledger', SimpleNamespace(Ledger=Ledger))
    config = Settings(demo=False, api_key='synthetic', postgres_dsn='postgresql://synthetic',
                      _env_file=None)
    repo, assets = MemorySnapshots(), MemoryAssets()
    monkeypatch.setattr(repo, 'close', lambda: pytest.fail('borrowed repository closed'))
    monkeypatch.setattr(assets, 'close', lambda: pytest.fail('borrowed assets closed'))
    with TestClient(create_app(config, repo, assets)) as client:
        for _ in range(2):
            result = client.get('/health/ready', headers={'X-API-Key': 'synthetic'})
            assert result.status_code == 200
        assert counts == {'created': 1, 'ping': 2, 'closed': 0}
    assert counts == {'created': 1, 'ping': 2, 'closed': 1}


def test_mongo_write_result_and_bson_limit_with_official_sdk():
    pytest.importorskip('bson', reason='Official PyMongo BSON encoder is not installed')
    snapshot = synthetic_snapshot()
    repo, collection = repository(snapshot)
    from pymongo.results import UpdateResult
    results = iter([UpdateResult({'n': 1, 'upserted': snapshot.id}, acknowledged=True),
                    UpdateResult({'n': 1, 'nModified': 0}, acknowledged=True)])
    collection.update_one = lambda *args, **kwargs: next(results)
    assert repo.put(snapshot) == snapshot.id
    assert collection.reads == []  # Confirmed new insertion avoids readback.
    collection.legacy = True
    assert repo.put(snapshot) == snapshot.id
    assert collection.reads == [None]  # Existing evidence still gets full verification.
    attempts = []

    def timeout(*args, **kwargs):
        attempts.append(args)
        raise TimeoutError('unknown write result')

    collection.update_one = timeout
    with pytest.raises(TimeoutError):
        repo.put(snapshot)
    assert len(attempts) == 1  # No blind retry or synthetic success.
    huge = Snapshot.create(b'{"task_id":"synthetic","instruction":"","traj":[]}',
                          media={f'images/{i}/' + 'x' * 90: '0' * 64 for i in range(60000)})
    collection.update_one = lambda *args, **kwargs: pytest.fail('oversized BSON was sent')
    with pytest.raises(ContractError, match='BSON'):
        repo.put(huge)


def test_list_keeps_summary_projection_and_hash_order_without_raw_reads():
    snapshot = synthetic_snapshot()
    repo, collection = repository(snapshot)
    query_log = []

    class Cursor:
        def sort(self, field, order):
            assert (field, order) == ('_id', 1)
            return self

        def limit(self, count):
            assert count == 50
            return [{'summary': snapshot.summary()}]

    def find(query, projection):
        query_log.append((query, projection))
        return Cursor()

    collection.find = find
    repo.collection = collection
    assert repo.list() == [snapshot.summary()]
    assert query_log == [({'_id': {'$gt': ''}}, {'summary': 1})]
    assert collection.reads == []


def test_media_authentication_happens_before_index_or_asset_read():
    snapshot = synthetic_snapshot()
    repo, collection = repository(snapshot)
    config = Settings(demo=False, api_key='synthetic', _env_file=None)
    with TestClient(create_app(config, repo, MemoryAssets())) as client:
        assert client.get(f'/api/v1/snapshots/{snapshot.id}/media',
                          params={'path': 'images/a.png'}).status_code == 401
        assert client.get(f'/api/v1/snapshots/{snapshot.id}/header').status_code == 401
    assert collection.reads == []
