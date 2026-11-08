"""Frozen Outcome requests on an explicitly configured isolated PostgreSQL database."""
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from evonext.config import Settings, secret
from evonext.evaluation.store import PostgresOutcomes, RunConflict

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("EVONEXT_INTEGRATION") != "1",
    reason="Explicit isolated PostgreSQL with migration 0005 required")]


def test_real_pg_concurrent_claim_append_once_and_reconnect():
    dsn = secret(Settings().postgres_dsn)
    assert "test" in (make_url(dsn).database or "").lower()
    engine = create_engine(dsn, pool_size=4)
    store = PostgresOutcomes(engine)
    key = str(uuid4())
    frozen = {"request": {"run_id": key, "snapshot_id": "b" * 64}, "input_hash": "a" * 64}
    try:
        assert store.create(frozen) == store.create(frozen)
        with pytest.raises(RunConflict):
            store.create(frozen | {"input_hash": "c" * 64})
        with ThreadPoolExecutor(max_workers=4) as pool:
            assert sum(pool.map(lambda _: store.claim(key), range(4))) == 1
        record = {"execution_status": "completed", "outcome": "unknown", "checks": []}
        store.finish(key, record)
        store.finish(key, {"execution_status": "error", "outcome": "not_assessed"})
        engine.dispose()
        reopened = PostgresOutcomes(engine)
        assert reopened.get(key)["record"] == record
        assert reopened.get(key)["status"] == "completed"
        assert not reopened.claim(key)
    finally:
        engine.dispose()
