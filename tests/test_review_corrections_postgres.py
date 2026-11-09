"""Real correction CAS and frozen-review persistence on an explicit test database."""
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from evonext.config import Settings, secret
from evonext.review.contracts import StaleCase
from evonext.review.store import PostgresCases

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("EVONEXT_INTEGRATION") != "1",
    reason="Requires explicitly enabled isolated PostgreSQL with migration 0004")]


def test_correction_cas_receipt_and_frozen_review_survive_reconnection():
    dsn = secret(Settings().postgres_dsn)
    assert "test" in (make_url(dsn).database or "").lower()
    engine = create_engine(dsn, pool_size=4)
    case_id = str(uuid4())
    store = PostgresCases(engine)
    payload = {
        "case_id": case_id, "proposal_hash": "a" * 64, "snapshot_id": "b" * 64,
        "position": 6, "source_step_id": "synthetic-later-recovery", "source_version": 0,
        "issue_kind": "step_action", "summary": "Synthetic later recovery correction.",
        "evidence_refs": ["step:6"], "analysis_refs": [],
    }
    store.create(payload, actor="synthetic-operator")
    commands = [str(uuid4()) for _ in range(4)]
    body = {"note": "Synthetic frozen note", "items": []}

    def save(index):
        try:
            return store.save_draft(case_id, 0, body, command_id=commands[index],
                                    actor="synthetic-operator")
        except StaleCase:
            return None

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(save, range(4)))
        assert sum(result is not None for result in results) == 1
        winner = next(i for i, result in enumerate(results) if result is not None)
        draft = results[winner]
        assert store.save_draft(case_id, 0, body, command_id=commands[winner],
                                actor="synthetic-operator") == draft
        command = str(uuid4())
        reviewed = store.decide_frozen(
            case_id, 0, draft["draft_revision"], draft["draft_hash"], "confirmed",
            "Synthetic review confirms this step.", command_id=command,
            actor="synthetic-operator")
        store.save_draft(case_id, 1, {"note": "New synthetic draft", "items": []},
                         command_id=str(uuid4()), actor="synthetic-operator")
        engine.dispose()
        reopened = PostgresCases(engine)
        frozen = reopened.get_review(case_id, 1)
        assert frozen["frozen_draft"] == body
        assert reopened.get_draft(case_id)["draft_revision"] == 2
        assert reopened.decide_frozen(
            case_id, 0, draft["draft_revision"], draft["draft_hash"], "confirmed",
            "Synthetic review confirms this step.", command_id=command,
            actor="synthetic-operator") == reviewed
    finally:
        engine.dispose()
