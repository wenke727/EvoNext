"""Case is a single aggregate with append-only operator review revisions.

No writes to Mongo Task/latest, original OpenCUA JSON or Eval records. Postgres
persistence is the only non-demo store; in-memory is explicit demo/test only.
"""
import copy
from datetime import datetime, timezone
from threading import RLock

from sqlalchemy import (Column, DateTime, ForeignKey, Integer, MetaData, String,
                        Table, Text, and_, select, update, func)
from sqlalchemy.dialects.postgresql import JSONB, insert

from .contracts import CaseConflict, CaseNotFound, StaleCase

metadata = MetaData(schema="evonext")
case_heads = Table("case_heads", metadata,
    Column("case_id", String(36), primary_key=True),
    Column("proposal_hash", String(64), nullable=False),
    Column("snapshot_id", String(64), nullable=False, index=True),
    Column("position", Integer, nullable=False),
    Column("source_step_id", String(256)),
    Column("source_version", Integer),
    Column("issue_kind", String(40), nullable=False),
    Column("summary", Text, nullable=False),
    Column("evidence_refs", JSONB, nullable=False),
    Column("analysis_refs", JSONB, nullable=False),
    Column("created_by", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("review_revision", Integer, nullable=False),
    Column("review_status", String(32), nullable=False),
)
case_reviews = Table("case_reviews", metadata,
    Column("case_id", String(36), ForeignKey("evonext.case_heads.case_id"), primary_key=True),
    Column("revision", Integer, primary_key=True),
    Column("decision", String(32), nullable=False),
    Column("reason", Text, nullable=False),
    Column("actor", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


def _utc_now():
    return datetime.now(timezone.utc)


def _public(row, history=()):
    result = {key: copy.deepcopy(row[key]) for key in
        ("case_id", "snapshot_id", "position", "source_step_id", "source_version",
         "issue_kind", "summary", "evidence_refs", "analysis_refs", "created_by",
         "review_revision", "review_status")}
    result["created_at"] = row["created_at"].isoformat()
    result["history"] = [{
        "revision": item["revision"], "decision": item["decision"],
        "reason": item["reason"], "actor": item["actor"],
        "created_at": item["created_at"].isoformat()
    } for item in history]
    # No 'reviewed': a single API Key is operator authority, not individual human proof.
    result["authority"] = "configured_operator" if result["review_status"] != "pending" else "none"
    return result


class MemoryCases:
    def __init__(self):
        self.lock = RLock()
        self.rows = {}
        self.events = {}

    def create(self, proposal, *, actor):
        with self.lock:
            key = proposal["case_id"]
            row = self.rows.get(key)
            if row:
                if row["proposal_hash"] != proposal["proposal_hash"]:
                    raise CaseConflict("Case ID already refers to different evidence")
                return _public(row, self.events[key])
            row = {**copy.deepcopy(proposal), "created_by": actor, "created_at": _utc_now(),
                   "review_revision": 0, "review_status": "pending"}
            self.rows[key] = row
            self.events[key] = []
            return _public(row)

    def get(self, case_id):
        with self.lock:
            row = self.rows.get(case_id)
            if row is None:
                raise CaseNotFound("Case not found")
            return _public(row, self.events[case_id])

    def for_snapshot(self, snapshot_id, limit=50):
        with self.lock:
            rows = [r for r in self.rows.values() if r["snapshot_id"] == snapshot_id]
            rows.sort(key=lambda r: (r["created_at"], r["case_id"]), reverse=True)
            return [_public(r) for r in rows[:limit]]

    def decide(self, case_id, expected, decision, reason, *, actor):
        with self.lock:
            row = self.rows.get(case_id)
            if row is None:
                raise CaseNotFound("Case not found")
            events = self.events[case_id]
            # After a response loss, an identical repeat is a read, not a new revision.
            if row["review_revision"] == expected + 1 and events:
                previous = events[-1]
                if (previous["decision"], previous["reason"], previous["actor"]) == (
                        decision, reason, actor):
                    return _public(row, events)
            if row["review_revision"] != expected:
                raise StaleCase("Review revision changed; refresh before deciding")
            if row["review_status"] not in {"pending", "needs_evidence"}:
                raise CaseConflict("Case review already decided; create a new revision workflow")
            event = {"revision": expected + 1, "decision": decision, "reason": reason,
                     "actor": actor, "created_at": _utc_now()}
            events.append(event)
            row["review_revision"] += 1
            row["review_status"] = "operator_confirmed" if decision == "confirmed" else decision
            return _public(row, events)

    def close(self):
        return None


class PostgresCases:
    def __init__(self, engine):
        # Engine is shared with the app's existing Ledger. This store does not own it.
        self.engine = engine

    def create(self, proposal, *, actor):
        row = {**proposal, "created_by": actor,
               "review_revision": 0, "review_status": "pending"}
        with self.engine.begin() as db:
            db.execute(insert(case_heads).values(**row)
                       .on_conflict_do_nothing(index_elements=[case_heads.c.case_id]))
            selected = db.execute(select(case_heads).where(
                case_heads.c.case_id == row["case_id"])).mappings().one()
            if selected["proposal_hash"] != proposal["proposal_hash"]:
                raise CaseConflict("Case ID already refers to different evidence")
        return self.get(row["case_id"])

    def get(self, case_id):
        with self.engine.connect() as db:
            row = db.execute(select(case_heads).where(
                case_heads.c.case_id == case_id)).mappings().first()
            if row is None:
                raise CaseNotFound("Case not found")
            events = db.execute(select(case_reviews).where(
                case_reviews.c.case_id == case_id).order_by(
                case_reviews.c.revision)).mappings().all()
            return _public(row, events)

    def for_snapshot(self, snapshot_id, limit=50):
        with self.engine.connect() as db:
            rows = db.execute(select(case_heads).where(
                case_heads.c.snapshot_id == snapshot_id).order_by(
                case_heads.c.created_at.desc(), case_heads.c.case_id.desc()).limit(limit)).mappings().all()
            return [_public(row) for row in rows]

    def decide(self, case_id, expected, decision, reason, *, actor):
        with self.engine.begin() as db:
            row = db.execute(select(case_heads).where(
                case_heads.c.case_id == case_id).with_for_update()).mappings().first()
            if row is None:
                raise CaseNotFound("Case not found")
            if row["review_revision"] == expected + 1:
                previous = db.execute(select(case_reviews).where(and_(
                    case_reviews.c.case_id == case_id,
                    case_reviews.c.revision == expected + 1))).mappings().first()
                if previous and (previous["decision"], previous["reason"], previous["actor"]) == (
                        decision, reason, actor):
                    # The return occurs after transaction release, outside the DB lock.
                    replay = True
                else:
                    replay = False
            else:
                replay = False
            if not replay:
                if row["review_revision"] != expected:
                    raise StaleCase("Review revision changed; refresh before deciding")
                if row["review_status"] not in {"pending", "needs_evidence"}:
                    raise CaseConflict("Case review already decided; create a new revision workflow")
                db.execute(insert(case_reviews).values(
                    case_id=case_id, revision=expected + 1, decision=decision,
                    reason=reason, actor=actor))
                db.execute(update(case_heads).where(case_heads.c.case_id == case_id).values(
                    review_revision=expected + 1,
                    review_status="operator_confirmed" if decision == "confirmed" else decision))
        return self.get(case_id)

    def close(self):
        return None
