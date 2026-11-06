"""Opt-in, isolated real-service checks. Never auto-run on a production environment."""
import os
import uuid

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv('EVONEXT_INTEGRATION') != '1', reason='Isolated live services not authorized/configured')]


def test_real_persistence_and_receipt_roundtrip():
    from evonext.config import Settings, secret
    from evonext.contracts.trajectory import Snapshot, encode_json
    from evonext.operations.ledger import Ledger
    from evonext.evidence.store import stores
    from evonext.operations.verification import verify_snapshot
    settings = Settings()
    assert not settings.demo
    assert 'test' in settings.mongo_database.lower(), 'Use an isolated test database'
    assert 'test' in settings.minio_bucket.lower(), 'Use an isolated test bucket'
    assert settings.postgres_dsn and 'test' in secret(settings.postgres_dsn).lower()
    repository, assets = stores(settings)
    ledger = Ledger(secret(settings.postgres_dsn))
    try:
        repository.ping()
        assets.ping()
        ledger.ping()
        data = b'\x89PNG\r\n\x1a\nsynthetic-integration-fixture'
        digest = assets.put(data)
        snapshot = Snapshot.create(encode_json({'task_id': 'synthetic-' + uuid.uuid4().hex,
            'instruction': 'Storage contract only', 'traj': [{'index': 0, 'image': 'images/test.png', 'value': {}}]}),
            encode_json({'do_not_train': True, 'source_kind': 'synthetic'}), {'images/test.png': digest})
        repository.put(snapshot)
        assert repository.get(snapshot.id).trajectory_json == snapshot.trajectory_json
        result = verify_snapshot(snapshot.id, repository, assets, ledger)
        assert ledger.get(result['operation_id'])['payload']['agent_outcome'] == 'not_assessed'
        assert verify_snapshot(snapshot.id, repository, assets, ledger) == result
    finally:
        repository.close()
        ledger.close()
