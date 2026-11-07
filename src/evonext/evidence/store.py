"""Infrastructure adapters. No production fallback to in-memory storage."""
import copy
import io
from threading import Lock
from typing import Protocol

from evonext.config import Settings, secret
from evonext.contracts.trajectory import ContractError, Snapshot, sha256
from .index import SnapshotIndex, StoredEvidenceError


class SnapshotRepository(Protocol):
    def put(self, snapshot: Snapshot) -> str: ...
    def get(self, snapshot_id: str) -> Snapshot | None: ...
    def get_index(self, snapshot_id: str) -> SnapshotIndex | None: ...
    def list(self, after: str = "", limit: int = 50) -> list[dict]: ...
    def ping(self) -> None: ...
    def close(self) -> None: ...


class AssetStore(Protocol):
    def close(self) -> None: ...
    def put(self, data: bytes) -> str: ...
    def get(self, digest: str) -> bytes: ...
    def ping(self) -> None: ...


class MemorySnapshots:
    def __init__(self):
        self.items = {}
        self.indexes = {}
        self.lock = Lock()

    def put(self, snapshot):
        with self.lock:
            self.items.setdefault(snapshot.id, copy.deepcopy(snapshot))
            self.indexes.setdefault(snapshot.id, SnapshotIndex.from_snapshot(snapshot))
        return snapshot.id

    def get(self, snapshot_id):
        with self.lock:
            return copy.deepcopy(self.items.get(snapshot_id))

    def get_index(self, snapshot_id):
        with self.lock:
            return copy.deepcopy(self.indexes.get(snapshot_id))

    def list(self, after="", limit=50):
        with self.lock:
            return [self.items[k].summary() for k in sorted(self.items) if k > after][:limit]

    def ping(self):
        return None

    def close(self):
        return None


class MemoryAssets:
    def __init__(self):
        self.items = {}

    def put(self, data):
        digest = sha256(data)
        self.items.setdefault(digest, bytes(data))
        return digest

    def get(self, digest):
        data = self.items[digest]
        if sha256(data) != digest:
            raise ContractError("Media integrity mismatch")
        return data

    def ping(self):
        return None

    def close(self):
        return None


class MongoSnapshots:
    def __init__(self, settings: Settings, client=None):
        self.owns_client = client is None
        if client is None:
            from pymongo import MongoClient
            client = MongoClient(secret(settings.mongo_uri), serverSelectionTimeoutMS=3000,
                                 connectTimeoutMS=3000, socketTimeoutMS=10000)
        self.client = client
        self.collection = self.client[settings.mongo_database][settings.mongo_collection]

    def put(self, snapshot):
        from bson import BSON
        row = {"_id": snapshot.id,
               "trajectory_json": snapshot.trajectory_json.decode("utf-8"),
               "metadata_json": snapshot.metadata_json.decode("utf-8"),
               "media": snapshot.media, "summary": snapshot.summary(),
               "index": SnapshotIndex.from_snapshot(snapshot).stored()}
        # BSON includes the complete wrapper, duplicated bindings and projection overhead.
        if len(BSON.encode(row)) > 16 * 1024 * 1024:
            raise ContractError("Snapshot BSON exceeds the 16 MiB document limit")
        result = self.collection.update_one({"_id": snapshot.id},
            {"$setOnInsert": {key: value for key, value in row.items() if key != "_id"}},
            upsert=True)
        if not result.acknowledged:
            raise RuntimeError("Snapshot write outcome is unconfirmed; reconcile before retry")
        # A confirmed insertion already contains exactly these validated bytes.
        # Existing rows still need full evidence verification, not just index comparison.
        if result.upserted_id is None:
            stored = self.get(snapshot.id)
            if stored is None or stored.manifest != snapshot.manifest:
                raise StoredEvidenceError("Snapshot persistence mismatch")
        return snapshot.id

    def get(self, snapshot_id):
        if not isinstance(snapshot_id, str) or len(snapshot_id) != 64 or any(c not in "0123456789abcdef" for c in snapshot_id):
            raise ContractError("Invalid snapshot identity")
        row = self.collection.find_one({"_id": snapshot_id})
        if row is None:
            return None
        try:
            snapshot = Snapshot.create(row["trajectory_json"].encode("utf-8"),
                                       row["metadata_json"].encode("utf-8"), row["media"])
        except (ContractError, KeyError, TypeError, AttributeError) as exc:
            raise StoredEvidenceError("Stored snapshot integrity mismatch") from exc
        if snapshot.id != snapshot_id:
            raise StoredEvidenceError("Stored snapshot integrity mismatch")
        return snapshot

    def get_index(self, snapshot_id):
        if not isinstance(snapshot_id, str) or len(snapshot_id) != 64 or any(c not in "0123456789abcdef" for c in snapshot_id):
            raise ContractError("Invalid snapshot identity")
        row = self.collection.find_one({"_id": snapshot_id}, {"index": 1})
        if row is None:
            return None
        if "index" in row:
            return SnapshotIndex.from_stored(snapshot_id, row["index"])
        # Legacy wrapper: one explicit full read, no migration or repair on GET.
        snapshot = self.get(snapshot_id)
        return SnapshotIndex.from_snapshot(snapshot) if snapshot is not None else None

    def list(self, after="", limit=50):
        rows = self.collection.find({"_id": {"$gt": after}}, {"summary": 1}).sort("_id", 1).limit(limit)
        return [row["summary"] for row in rows]

    def ping(self):
        self.client.admin.command("ping")

    def close(self):
        if self.owns_client:
            self.client.close()


class MinioAssets:
    def __init__(self, settings: Settings):
        from minio import Minio
        import urllib3
        self.bucket = settings.minio_bucket
        self.max_bytes = settings.max_file_bytes
        self.http_client = urllib3.PoolManager(timeout=urllib3.Timeout(connect=3, read=10),
                                               retries=False)
        self.client = Minio(settings.minio_endpoint, access_key=secret(settings.minio_access_key),
                            secret_key=secret(settings.minio_secret_key), secure=settings.minio_secure,
                            http_client=self.http_client)

    @staticmethod
    def key(digest):
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ContractError("Invalid media identity")
        return "evonext/media/" + digest

    def put(self, data):
        if len(data) > self.max_bytes:
            raise ContractError("Media exceeds size limit")
        digest = sha256(data)
        self.client.put_object(self.bucket, self.key(digest), io.BytesIO(data), len(data),
                               content_type="application/octet-stream")
        return digest

    def get(self, digest):
        from minio.error import S3Error
        try:
            response = self.client.get_object(self.bucket, self.key(digest))
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject"}:
                raise StoredEvidenceError("Bound media is missing") from exc
            raise
        try:
            data = response.read(self.max_bytes + 1)
        finally:
            response.close()
            response.release_conn()
        if len(data) > self.max_bytes or sha256(data) != digest:
            raise ContractError("Media integrity mismatch")
        return data

    def ping(self):
        if not self.client.bucket_exists(self.bucket):
            raise RuntimeError("Provision the configured bucket explicitly")

    def close(self):
        self.http_client.clear()


def stores(settings):
    if settings.demo:
        return MemorySnapshots(), MemoryAssets()
    return MongoSnapshots(settings), MinioAssets(settings)
