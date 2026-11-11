"""Single Case aggregate with append-only reviews and one CAS-governed shared draft.

PostgreSQL is the production owner. The memory implementation is explicitly
test/demo-only; neither touches OpenCUA JSON, legacy Case data nor Eval records.
"""
import copy
from datetime import datetime, timezone
from threading import RLock

from sqlalchemy import (Column, DateTime, ForeignKey, Integer, MetaData, String,
                        Table, Text, and_, select, update, func)
from sqlalchemy.dialects.postgresql import JSONB, insert

from evonext.contracts.trajectory import encode_json, sha256
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
    Column("draft_revision", Integer),
    Column("draft_hash", String(64)),
    Column("frozen_draft", JSONB),
    Column("review_input_hash", String(64)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
case_drafts = Table("case_drafts", metadata,
    Column("case_id", String(36), ForeignKey("evonext.case_heads.case_id"), primary_key=True),
    Column("revision", Integer, nullable=False),
    Column("draft_hash", String(64), nullable=False),
    Column("body", JSONB, nullable=False),
    Column("updated_by", String(128), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
case_commands = Table("case_commands", metadata,
    Column("case_id", String(36), ForeignKey("evonext.case_heads.case_id"), primary_key=True),
    Column("command_id", String(36), primary_key=True),
    Column("kind", String(32), nullable=False),
    Column("payload_hash", String(64), nullable=False),
    Column("actor", String(128), nullable=False),
    Column("receipt", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

EMPTY_DRAFT = {"note": "", "items": []}
EMPTY_HASH = sha256(encode_json(EMPTY_DRAFT))
STATUS = {"confirmed": "operator_confirmed", "rejected": "rejected",
          "needs_evidence": "needs_evidence"}


def _utc_now():
    return datetime.now(timezone.utc)


def _review_dict(event):
    return {
        "revision": event["revision"], "decision": event["decision"],
        "reason": event["reason"], "actor": event["actor"],
        "created_at": event["created_at"].isoformat(),
        "draft_revision": event.get("draft_revision"),
        "draft_hash": event.get("draft_hash"),
        "review_input_hash": event.get("review_input_hash"),
    }


def _public(row, history=()):
    result = {key: copy.deepcopy(row[key]) for key in
        ("case_id", "snapshot_id", "position", "source_step_id", "source_version",
         "issue_kind", "summary", "evidence_refs", "analysis_refs", "created_by",
         "review_revision", "review_status")}
    result["created_at"] = row["created_at"].isoformat()
    result["history"] = [_review_dict(event) for event in history]
    # Configured operator ≠ authenticated human Gold.
    result["authority"] = ("configured_operator" if result["review_status"] != "pending"
                           else "none")
    return result


def _draft_public(case_id, row=None):
    if row is None:
        return {
            "case_id": case_id, "draft_revision": 0, "draft_hash": EMPTY_HASH,
            "draft": copy.deepcopy(EMPTY_DRAFT), "updated_by": None, "updated_at": None,
        }
    return {
        "case_id": case_id, "draft_revision": row["revision"], "draft_hash": row["draft_hash"],
        "draft": copy.deepcopy(row["body"]), "updated_by": row["updated_by"],
        "updated_at": row["updated_at"].isoformat(),
    }


def _command_hash(kind, expected, data, actor):
    return sha256(encode_json({
        "kind": kind, "expected_revision": expected, "data": data, "actor": actor,
    }))


def _review_input_hash(case, draft_revision, draft_hash, decision, reason):
    return sha256(encode_json({
        "profile": "evonext.frozen-case-review.v1",
        "proposal_hash": case["proposal_hash"],
        "snapshot_id": case["snapshot_id"],
        "draft_revision": draft_revision,
        "draft_hash": draft_hash,
        "decision": decision,
        "reason": reason,
    }))


def _freeze_review(case, rev, decision, reason, actor, draft=None):
    new = {
        "case_id": case["case_id"], "revision": rev,
        "decision": decision, "reason": reason, "actor": actor,
        "created_at": _utc_now(),
        "draft_revision": draft["revision"] if draft else None,
        "draft_hash": draft["draft_hash"] if draft else None,
        "frozen_draft": copy.deepcopy(draft["body"]) if draft else None,
    }
    new["review_input_hash"] = _review_input_hash(
        case, new["draft_revision"], new["draft_hash"], decision, reason)
    return new


def _complete_receipt(previous, kind, digest, actor):
    if previous is None:
        return None
    if (previous["kind"], previous["payload_hash"], previous["actor"]) != (
            kind, digest, actor):
        raise CaseConflict("Command ID already has a different request or operator")
    return copy.deepcopy(previous["receipt"])


class MemoryCases:
    """Explicitly volatile demo store, never a fallback for production."""
    def __init__(self):
        self.lock = RLock()
        self.rows = {}
        self.events = {}
        self.drafts = {}
        self.commands = {}

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

    def list_queue(self, status=None, after="", limit=50):
        with self.lock:
            rows = (r for k, r in sorted(self.rows.items()) if k > after and
                    (status is None or r["review_status"] == status))
            return [_public(r) for r in rows][:limit]

    def get_draft(self, case_id):
        with self.lock:
            if case_id not in self.rows:
                raise CaseNotFound("Case not found")
            return _draft_public(case_id, self.drafts.get(case_id))

    def save_draft(self, case_id, expected, body, *, command_id, actor):
        with self.lock:
            if case_id not in self.rows:
                raise CaseNotFound("Case not found")
            digest = _command_hash("save_draft", expected, body, actor)
            receipt = _complete_receipt(self.commands.get((case_id, command_id)),
                                        "save_draft", digest, actor)
            if receipt is not None:
                return receipt
            current = self.drafts.get(case_id)
            revision = current["revision"] if current else 0
            if revision != expected:
                raise StaleCase("Shared draft changed; reload and compare local edits")
            row = {"revision": revision + 1, "draft_hash": sha256(encode_json(body)),
                   "body": copy.deepcopy(body), "updated_by": actor, "updated_at": _utc_now()}
            self.drafts[case_id] = row
            receipt = _draft_public(case_id, row)
            self.commands[(case_id, command_id)] = {
                "kind": "save_draft", "payload_hash": digest, "actor": actor,
                "receipt": copy.deepcopy(receipt),
            }
            return receipt

    def _apply_review(self, row, case_id, expected, decision, reason, *, actor, draft=None):
        events = self.events[case_id]
        if row["review_revision"] != expected:
            raise StaleCase("Review revision changed; refresh before deciding")
        # PR #3's simple review is allowed only when no correction draft exists.
        if draft is None and self.drafts.get(case_id):
            raise CaseConflict("A saved correction draft requires frozen review command")
        if draft is None and row["review_status"] not in {"pending", "needs_evidence"}:
            raise CaseConflict("Re-review needs a frozen draft and a new command")
        event = _freeze_review(row, expected + 1, decision, reason, actor, draft)
        events.append(event)
        row["review_revision"] += 1
        row["review_status"] = STATUS[decision]
        return _public(row, events)

    def decide(self, case_id, expected, decision, reason, *, actor):
        with self.lock:
            row = self.rows.get(case_id)
            if row is None:
                raise CaseNotFound("Case not found")
            events = self.events[case_id]
            if row["review_revision"] == expected + 1 and events:
                previous = events[-1]
                if (previous["decision"], previous["reason"], previous["actor"]) == (
                        decision, reason, actor) and previous["draft_revision"] is None:
                    return _public(row, events)
            return self._apply_review(row, case_id, expected, decision, reason, actor=actor)

    def decide_frozen(self, case_id, expected, draft_revision, draft_hash,
                      decision, reason, *, command_id, actor):
        with self.lock:
            row = self.rows.get(case_id)
            if row is None:
                raise CaseNotFound("Case not found")
            data = {"draft_revision": draft_revision, "draft_hash": draft_hash,
                    "decision": decision, "reason": reason}
            digest = _command_hash("review_frozen", expected, data, actor)
            receipt = _complete_receipt(self.commands.get((case_id, command_id)),
                                        "review_frozen", digest, actor)
            if receipt is not None:
                return receipt
            current = self.drafts.get(case_id)
            if not current or (current["revision"], current["draft_hash"]) != (
                    draft_revision, draft_hash):
                raise StaleCase("Visible correction draft has changed; review not submitted")
            result = self._apply_review(row, case_id, expected, decision, reason,
                                        actor=actor, draft=current)
            self.commands[(case_id, command_id)] = {
                "kind": "review_frozen", "payload_hash": digest,
                "actor": actor, "receipt": copy.deepcopy(result),
            }
            return result

    def get_review(self, case_id, revision):
        with self.lock:
            if case_id not in self.rows:
                raise CaseNotFound("Case not found")
            for event in self.events[case_id]:
                if event["revision"] == revision:
                    return {**_review_dict(event),
                            "case_id": case_id, "frozen_draft": copy.deepcopy(event["frozen_draft"]),
                            "source_snapshot_id": self.rows[case_id]["snapshot_id"]}
            raise CaseNotFound("Review revision not found")

    def close(self):
        return None


class PostgresCases:
    def __init__(self, engine):
        self.engine = engine  # Borrowed app Engine; no new pool per request.

    def _get_command(self, db, case_id, command_id, kind, digest, actor):
        row = db.execute(select(case_commands).where(and_(
            case_commands.c.case_id == case_id,
            case_commands.c.command_id == command_id))).mappings().first()
        return _complete_receipt(row, kind, digest, actor)

    def _history(self, db, case_id):
        return db.execute(select(case_reviews).where(
            case_reviews.c.case_id == case_id).order_by(case_reviews.c.revision)).mappings().all()

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
            return _public(row, self._history(db, case_id))

    def for_snapshot(self, snapshot_id, limit=50):
        with self.engine.connect() as db:
            rows = db.execute(select(case_heads).where(
                case_heads.c.snapshot_id == snapshot_id).order_by(
                case_heads.c.created_at.desc(), case_heads.c.case_id.desc()).limit(limit)).mappings().all()
            return [_public(row) for row in rows]

    def list_queue(self, status=None, after="", limit=50):
        query = select(case_heads).where(case_heads.c.case_id > after)
        if status is not None:
            query = query.where(case_heads.c.review_status == status)
        with self.engine.connect() as db:
            rows = db.execute(query.order_by(case_heads.c.case_id).limit(limit)).mappings().all()
            return [_public(row) for row in rows]

    def get_draft(self, case_id):
        with self.engine.connect() as db:
            if db.execute(select(case_heads.c.case_id).where(
                    case_heads.c.case_id == case_id)).scalar_one_or_none() is None:
                raise CaseNotFound("Case not found")
            row = db.execute(select(case_drafts).where(
                case_drafts.c.case_id == case_id)).mappings().first()
            return _draft_public(case_id, row)

    def save_draft(self, case_id, expected, body, *, command_id, actor):
        digest = _command_hash("save_draft", expected, body, actor)
        with self.engine.begin() as db:
            receipt = self._get_command(db, case_id, command_id, "save_draft", digest, actor)
            if receipt is not None:
                return receipt
            case = db.execute(select(case_heads.c.case_id).where(
                case_heads.c.case_id == case_id).with_for_update()).scalar_one_or_none()
            if case is None:
                raise CaseNotFound("Case not found")
            current = db.execute(select(case_drafts).where(
                case_drafts.c.case_id == case_id).with_for_update()).mappings().first()
            revision = current["revision"] if current else 0
            if revision != expected:
                raise StaleCase("Shared draft changed; reload and compare local edits")
            draft_hash = sha256(encode_json(body))
            if current:
                db.execute(update(case_drafts).where(case_drafts.c.case_id == case_id).values(
                    revision=revision + 1, draft_hash=draft_hash, body=body,
                    updated_by=actor, updated_at=func.now()))
            else:
                db.execute(insert(case_drafts).values(case_id=case_id, revision=1,
                    draft_hash=draft_hash, body=body, updated_by=actor))
            saved = db.execute(select(case_drafts).where(
                case_drafts.c.case_id == case_id)).mappings().one()
            receipt = _draft_public(case_id, saved)
            db.execute(insert(case_commands).values(
                case_id=case_id, command_id=command_id, kind="save_draft",
                payload_hash=digest, actor=actor, receipt=receipt))
            return receipt

    def _apply_review(self, db, row, case_id, expected, decision, reason,
                      *, actor, draft=None):
        if row["review_revision"] != expected:
            raise StaleCase("Review revision changed; refresh before deciding")
        if draft is None:
            exists = db.execute(select(case_drafts.c.case_id).where(
                case_drafts.c.case_id == case_id)).scalar_one_or_none()
            if exists:
                raise CaseConflict("A saved correction draft requires frozen review command")
            if row["review_status"] not in {"pending", "needs_evidence"}:
                raise CaseConflict("Re-review needs a frozen draft and a new command")
        event = _freeze_review(row, expected + 1, decision, reason, actor, draft)
        db.execute(insert(case_reviews).values(**event))
        db.execute(update(case_heads).where(case_heads.c.case_id == case_id).values(
            review_revision=expected + 1, review_status=STATUS[decision]))
        new = db.execute(select(case_heads).where(
            case_heads.c.case_id == case_id)).mappings().one()
        return _public(new, self._history(db, case_id))

    def decide(self, case_id, expected, decision, reason, *, actor):
        with self.engine.begin() as db:
            row = db.execute(select(case_heads).where(
                case_heads.c.case_id == case_id).with_for_update()).mappings().first()
            if row is None:
                raise CaseNotFound("Case not found")
            if row["review_revision"] == expected + 1:
                prev = db.execute(select(case_reviews).where(and_(
                    case_reviews.c.case_id == case_id,
                    case_reviews.c.revision == expected + 1))).mappings().first()
                if prev and (prev["decision"], prev["reason"], prev["actor"]) == (
                        decision, reason, actor) and prev["draft_revision"] is None:
                    return _public(row, self._history(db, case_id))
            return self._apply_review(db, row, case_id, expected, decision, reason, actor=actor)

    def decide_frozen(self, case_id, expected, draft_revision, draft_hash,
                      decision, reason, *, command_id, actor):
        data = {"draft_revision": draft_revision, "draft_hash": draft_hash,
                "decision": decision, "reason": reason}
        digest = _command_hash("review_frozen", expected, data, actor)
        with self.engine.begin() as db:
            receipt = self._get_command(db, case_id, command_id,
                                        "review_frozen", digest, actor)
            if receipt is not None:
                return receipt
            row = db.execute(select(case_heads).where(
                case_heads.c.case_id == case_id).with_for_update()).mappings().first()
            if row is None:
                raise CaseNotFound("Case not found")
            draft = db.execute(select(case_drafts).where(
                case_drafts.c.case_id == case_id).with_for_update()).mappings().first()
            if not draft or (draft["revision"], draft["draft_hash"]) != (
                    draft_revision, draft_hash):
                raise StaleCase("Visible correction draft has changed; review not submitted")
            receipt = self._apply_review(db, row, case_id, expected, decision, reason,
                                         actor=actor, draft=draft)
            db.execute(insert(case_commands).values(
                case_id=case_id, command_id=command_id, kind="review_frozen",
                payload_hash=digest, actor=actor, receipt=receipt))
            return receipt

    def get_review(self, case_id, revision):
        with self.engine.connect() as db:
            row = db.execute(select(case_reviews).where(and_(
                case_reviews.c.case_id == case_id,
                case_reviews.c.revision == revision))).mappings().first()
            if row is None:
                raise CaseNotFound("Review revision not found")
            case = db.execute(select(case_heads.c.snapshot_id).where(
                case_heads.c.case_id == case_id)).scalar_one()
            return {**_review_dict(row), "case_id": case_id,
                    "frozen_draft": copy.deepcopy(row["frozen_draft"]),
                    "source_snapshot_id": case}

    def close(self):
        return None
