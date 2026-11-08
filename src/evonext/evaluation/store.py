"""PostgreSQL owns frozen evaluation requests and append-once selected records."""
import copy
from threading import Lock

from sqlalchemy import Column, DateTime, MetaData, String, Table, func, select, update
from sqlalchemy.dialects.postgresql import JSONB, insert

from evonext.contracts.trajectory import ContractError

metadata = MetaData(schema="evonext")
runs = Table("outcome_runs", metadata,
    Column("run_id", String(36), primary_key=True),
    Column("snapshot_id", String(64), nullable=False, index=True),
    Column("input_hash", String(64), nullable=False),
    Column("frozen", JSONB, nullable=False),
    Column("status", String(32), nullable=False),
    Column("record", JSONB),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()))


class RunConflict(ContractError):
    pass


class MemoryOutcomes:
    """Explicitly volatile demo/test store."""
    def __init__(self):
        self.rows, self.lock = {}, Lock()

    def create(self, frozen):
        with self.lock:
            key = frozen["request"]["run_id"]
            if key in self.rows:
                if self.rows[key]["input_hash"] != frozen["input_hash"]:
                    raise RunConflict("Run ID already has different frozen input")
            else:
                self.rows[key] = {"run_id": key, "snapshot_id": frozen["request"]["snapshot_id"],
                    "input_hash": frozen["input_hash"], "frozen": copy.deepcopy(frozen),
                    "status": "queued", "record": None}
            return copy.deepcopy(self.rows[key])

    def get(self, key):
        with self.lock:
            return copy.deepcopy(self.rows.get(key))

    def list(self, snapshot):
        with self.lock:
            return [copy.deepcopy(row) for row in self.rows.values()
                    if row["snapshot_id"] == snapshot][-50:][::-1]

    def claim(self, key):
        with self.lock:
            row = self.rows.get(key)
            if not row or row["status"] != "queued":
                return False
            row["status"] = "running"
            return True

    def finish(self, key, record):
        with self.lock:
            row = self.rows[key]
            if row["status"] == "running":
                row.update(status="failed" if record["execution_status"] == "error" else "completed",
                           record=copy.deepcopy(record))


class PostgresOutcomes:
    def __init__(self, engine):
        self.engine = engine

    def create(self, frozen):
        key = frozen["request"]["run_id"]
        with self.engine.begin() as db:
            db.execute(insert(runs).values(run_id=key,
                snapshot_id=frozen["request"]["snapshot_id"], input_hash=frozen["input_hash"],
                frozen=frozen, status="queued").on_conflict_do_nothing())
            row = dict(db.execute(select(runs).where(runs.c.run_id == key)).mappings().one())
            if row["input_hash"] != frozen["input_hash"]:
                raise RunConflict("Run ID already has different frozen input")
            return row

    def get(self, key):
        with self.engine.connect() as db:
            row = db.execute(select(runs).where(runs.c.run_id == key)).mappings().first()
            return dict(row) if row else None

    def list(self, snapshot):
        with self.engine.connect() as db:
            return [dict(row) for row in db.execute(select(runs).where(
                runs.c.snapshot_id == snapshot).order_by(runs.c.created_at.desc(), runs.c.run_id.desc()).limit(50)).mappings()]

    def claim(self, key):
        with self.engine.begin() as db:
            return db.execute(update(runs).where(runs.c.run_id == key,
                runs.c.status == "queued").values(status="running")).rowcount == 1

    def finish(self, key, record):
        with self.engine.begin() as db:
            db.execute(update(runs).where(runs.c.run_id == key, runs.c.status == "running")
                .values(record=record, status="failed" if record["execution_status"] == "error"
                        else "completed"))
