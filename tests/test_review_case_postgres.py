"""Explicit, isolated PostgreSQL contract exercise.

Run only after applying Alembic migration 0003 against a TEST database.
No production data or long-lived fixtures are modified.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import create_engine

from evonext.config import Settings, secret
from evonext.review.contracts import StaleCase
from evonext.review.store import PostgresCases

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("EVONEXT_INTEGRATION") != "1",
    reason="Live isolated PostgreSQL review test requires explicit authorization")]


def test_real_postgres_case_identity_and_concurrent_review():
    settings = Settings()
    assert settings.postgres_dsn
    dsn = secret(settings.postgres_dsn)
    assert "test" in dsn.lower(), "Never run case tests against production PostgreSQL"
    engine = create_engine(dsn, pool_size=4, max_overflow=2)
    store = PostgresCases(engine)
    case_id = str(uuid4())
    payload = {
        "case_id": case_id,
        "proposal_hash": "a" * 64,
        "snapshot_id": "b" * 64,
        "position": 0,
        "source_step_id": None,
        "source_version": 0,
        "issue_kind": "unknown",
        "summary": "Synthetic PG reviewer concurrency case.",
        "evidence_refs": ["step:0"],
        "analysis_refs": [],
    }
    try:
        created = store.create(payload, actor="synthetic-author")
        assert created["review_revision"] == 0
        assert store.create(payload, actor="synthetic-author")["case_id"] == case_id

        def decide(i):
            try:
                store.decide(case_id, 0, "confirmed", f"Independent reason {i}.",
                             actor="synthetic-reviewer")
                return True
            except StaleCase:
                return False

        with ThreadPoolExecutor(max_workers=4) as pool:
            assert sum(pool.map(decide, range(4))) == 1
        reviewed = store.get(case_id)
        assert reviewed["review_status"] == "operator_confirmed"
        assert reviewed["review_revision"] == 1
        assert len(reviewed["history"]) == 1
    finally:
        engine.dispose()
