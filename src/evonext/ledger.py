"""PostgreSQL owns operation receipts, not a second trajectory database."""
from sqlalchemy import Column, DateTime, MetaData, String, Table, create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import make_url

from .domain import ContractError, encode_json, sha256

metadata = MetaData(schema="evonext")
receipts = Table("operation_receipts", metadata,
    Column("operation_id", String(128), primary_key=True),
    Column("snapshot_id", String(64), nullable=False, index=True),
    Column("kind", String(64), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("payload_hash", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()))


class Ledger:
    def __init__(self, dsn):
        if make_url(dsn).get_backend_name() != "postgresql":
            raise ValueError("The production receipt ledger requires PostgreSQL")
        self.engine = create_engine(dsn, pool_pre_ping=True, connect_args={
            "connect_timeout": 3, "options": "-c statement_timeout=5000"})

    def record(self, operation_id, snapshot_id, kind, payload):
        digest = sha256(encode_json({"snapshot_id": snapshot_id, "kind": kind, "payload": payload}))
        with self.engine.begin() as connection:
            connection.execute(insert(receipts).values(operation_id=operation_id,
                snapshot_id=snapshot_id, kind=kind, payload=payload, payload_hash=digest)
                .on_conflict_do_nothing(index_elements=[receipts.c.operation_id]))
            row = connection.execute(select(receipts).where(receipts.c.operation_id == operation_id)).mappings().one()
            if row["payload_hash"] != digest:
                raise ContractError("Operation ID already has a different result")
        return operation_id

    def get(self, operation_id):
        with self.engine.connect() as connection:
            row = connection.execute(select(receipts).where(receipts.c.operation_id == operation_id)).mappings().first()
            return dict(row) if row else None

    def ping(self):
        with self.engine.connect() as connection:
            connection.execute(select(receipts.c.operation_id).limit(0))

    def close(self):
        self.engine.dispose()
