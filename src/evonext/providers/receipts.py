"""Paid-call admission and response recovery; separate from delivery and tracing.

A sending/unknown call is never automatically resent. Retained raw responses
are replayed for parsing. This is not an exactly-once claim for the provider.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Protocol

from evonext.contracts.trajectory import ContractError


class CallHeld(ContractError):
    pass


class BudgetExceeded(ContractError):
    pass


@dataclass(frozen=True)
class ResponseReceipt:
    status_code: int
    body: str
    trace_id: str | None


class CallReceipts(Protocol):
    def begin(self, key: str, scope: str, limits: dict[int, int]) -> ResponseReceipt | None: ...
    def receive(self, key: str, response: ResponseReceipt) -> None: ...
    def unknown(self, key: str) -> None: ...
    def close(self) -> None: ...


class MemoryCallReceipts:
    """Test-only store. Never selected automatically by a production gateway."""
    def __init__(self, clock=None):
        self.rows = {}
        self.lock = Lock()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def begin(self, key, scope, limits):
        with self.lock:
            row = self.rows.get(key)
            if row:
                if row["scope"] != scope:
                    raise ContractError("Call receipt scope conflict")
                if row["status"] == "received":
                    return row["response"]
                raise CallHeld("Call is sending or outcome unknown; reconcile before a new attempt")
            now = self.clock()
            for seconds, maximum in limits.items():
                count = sum(r["scope"] == scope and r["at"] > now - timedelta(seconds=seconds)
                            for r in self.rows.values())
                if count >= maximum:
                    raise BudgetExceeded("Model request budget exhausted")
            self.rows[key] = {"scope": scope, "status": "sending", "at": now}
            return None

    def receive(self, key, response):
        with self.lock:
            row = self.rows[key]
            if row["status"] == "received" and row["response"] != response:
                raise ContractError("Conflicting model response")
            row.update(status="received", response=response)

    def unknown(self, key):
        with self.lock:
            if self.rows[key]["status"] != "received":
                self.rows[key]["status"] = "unknown"

    def close(self):
        return None


class PostgresCallReceipts:
    def __init__(self, dsn):
        from sqlalchemy import create_engine
        from sqlalchemy.engine import make_url
        if make_url(dsn).get_backend_name() != "postgresql":
            raise ValueError("Paid-call recovery requires PostgreSQL")
        self.engine = create_engine(dsn, pool_pre_ping=True, connect_args={
            "connect_timeout": 3, "options": "-c statement_timeout=5000"})

    def begin(self, key, scope, limits):
        from sqlalchemy import text
        from evonext.contracts.trajectory import sha256
        # The transaction ends BEFORE network I/O. A per-scope advisory lock makes
        # count + reservation atomic across API/worker processes, not per instance.
        lock_id = int(sha256(scope.encode())[:16], 16) - (1 << 63)
        with self.engine.begin() as db:
            db.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": lock_id})
            row = db.execute(text("SELECT * FROM evonext.model_call_receipts WHERE call_key=:key"),
                             {"key": key}).mappings().first()
            if row:
                if row["budget_scope"] != scope:
                    raise ContractError("Call receipt scope conflict")
                if row["status"] == "received":
                    return ResponseReceipt(row["status_code"], row["response_body"], row["trace_id"])
                raise CallHeld("Call is sending or outcome unknown; reconcile before a new attempt")
            for seconds, maximum in limits.items():
                count = db.execute(text("SELECT count(*) FROM evonext.model_call_receipts "
                    "WHERE budget_scope=:scope AND created_at > now() - (:seconds * interval '1 second')"),
                    {"scope": scope, "seconds": seconds}).scalar_one()
                if count >= maximum:
                    raise BudgetExceeded("Model request budget exhausted")
            db.execute(text("INSERT INTO evonext.model_call_receipts "
                "(call_key, budget_scope, status) VALUES (:key,:scope,'sending')"),
                {"key": key, "scope": scope})
        return None

    def receive(self, key, response):
        from sqlalchemy import text
        with self.engine.begin() as db:
            row = db.execute(text("SELECT * FROM evonext.model_call_receipts "
                                  "WHERE call_key=:key FOR UPDATE"), {"key": key}).mappings().one()
            if row["status"] == "received":
                if (row["status_code"], row["response_body"], row["trace_id"]) != (
                        response.status_code, response.body, response.trace_id):
                    raise ContractError("Conflicting model response")
                return
            db.execute(text("UPDATE evonext.model_call_receipts SET status='received', "
                "status_code=:status, response_body=:body, trace_id=:trace, updated_at=now() "
                "WHERE call_key=:key"), {"key": key, "status": response.status_code,
                                       "body": response.body, "trace": response.trace_id})

    def unknown(self, key):
        from sqlalchemy import text
        with self.engine.begin() as db:
            db.execute(text("UPDATE evonext.model_call_receipts SET status='unknown', updated_at=now() "
                            "WHERE call_key=:key AND status <> 'received'"), {"key": key})

    def close(self):
        self.engine.dispose()
