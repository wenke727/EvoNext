"""Synthetic-only read adapter tests; doubles never prove real-service isolation."""
import io
import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

pytest.importorskip("pymongo", reason="Official Mongo SDK is not installed")
pytest.importorskip("minio", reason="Official MinIO SDK is not installed")
from bson import ObjectId
from bson.int64 import Int64

from evonext.app.api import create_app
from evonext.compat.mongo_source import LegacyMongoSource
from evonext.config import Settings
from evonext.contracts.trajectory import ContractError
from evonext.evidence.index import EvidenceNotFound
from evonext.evidence.service import EvidenceService
from evonext.evidence.store import MemoryAssets, MemorySnapshots

PNG = b"\x89PNG\r\n\x1a\nsynthetic-source-only"
TASK = "900719925474099312345"


class Collection:
    def __init__(self, row):
        self.row, self.queries = row, []

    def find_one(self, query, **kwargs):
        self.queries.append(deepcopy(query))
        if query.get("task_id") != self.row["task_id"]:
            return None
        expected = query.get("_version_info.version_number")
        if expected is not None and expected != self.row["_version_info"]["version_number"]:
            return None
        return deepcopy(self.row)

    def aggregate(self, pipeline, **kwargs):
        return [{"task_id": TASK, "instruction": "synthetic", "step_count": 1,
                 "_version_info": {"version_number": 0}}]


class Mongo:
    def __init__(self, latest, history):
        self.latest, self.history, self.closed = latest, history, False

    def __getitem__(self, key):
        if key.endswith("_latest"):
            return self.latest
        if key.endswith("_history"):
            return self.history
        return self

    def close(self):
        self.closed = True


class Media:
    def __init__(self):
        self.reads = []

    def get_object(self, bucket, key):
        self.reads.append((bucket, key))
        response = io.BytesIO(PNG)
        response.release_conn = lambda: None
        return response


def source(tmp_path):
    env = tmp_path / "synthetic.env"
    env.write_text("MONGO_URI=mongodb://synthetic.invalid\nREVIEWER_MONGO_DB=synthetic\n"
                   "REVIEWER_MONGO_COLLECTION=tasks\nMINIO_ENDPOINT=synthetic.invalid:9000\n"
                   "IMAGE_MINIO_BUCKET=synthetic\n")
    settings = Settings(demo=True, legacy_env_file=str(env), _env_file=None)
    document = {"_id": ObjectId(), "task_id": TASK, "instruction": "synthetic",
        "_version_info": {"version_number": 0}, "unknown_long": 9007199254740993123,
        "traj": [{"image": "http://synthetic.invalid:9000/synthetic/frame.png",
                  "step_id": TASK, "value": {"raw_model_output": "  literal \\n ", "unknown": False}}]}
    mongo = Mongo(Collection(document), Collection(document))
    media = Media()
    return LegacyMongoSource(settings, mongo=mongo, media=media), settings, mongo, media


def test_source_reads_v0_and_binds_media_without_changing_legacy(tmp_path):
    reader, settings, mongo, media = source(tmp_path)
    original = deepcopy(mongo.latest.row)
    service = EvidenceService(MemorySnapshots(), MemoryAssets(), settings)
    snapshot = reader.capture(TASK, 0, service)
    assert snapshot.summary()["source_version"] == 0
    assert snapshot.document["task_id"] == TASK
    assert snapshot.document["unknown_long"] == {"$numberLong": "9007199254740993123"}
    assert snapshot.document["_id"]["$oid"] == str(original["_id"])
    assert snapshot.document["traj"][0]["value"]["raw_model_output"] == "  literal \\n "
    assert mongo.latest.row == original
    assert media.reads == [("synthetic", "frame.png")]
    assert len(snapshot.media) == 1
    reader.close()
    assert mongo.closed


def test_specific_missing_version_never_falls_back_to_latest(tmp_path):
    reader, _, mongo, _ = source(tmp_path)
    with pytest.raises(EvidenceNotFound):
        reader.fetch(TASK, 1)
    assert mongo.latest.queries[-1]["_version_info.version_number"] == 1
    with pytest.raises(ContractError):
        reader.fetch(TASK, -1)
    reader.close()


def test_untrusted_image_origin_is_not_fetched(tmp_path):
    reader, _, mongo, media = source(tmp_path)
    mongo.latest.row["traj"][0]["image"] = "http://other.invalid/private"
    _, metadata, bindings = reader.fetch(TASK)
    assert not bindings and not media.reads
    assert metadata["unresolved_media"] == ["http://other.invalid/private"]
    reader.close()


def test_source_api_uses_existing_snapshot_paths(tmp_path):
    reader, settings, _, _ = source(tmp_path)
    with TestClient(create_app(settings, MemorySnapshots(), MemoryAssets(), source=reader)) as client:
        listing = client.get("/api/v1/source/tasks").json()
        assert listing["items"][0]["task_id"] == TASK
        assert client.get("/health/ready").json()["source_mode"] == "legacy_mongo"
        response = client.post(f"/api/v1/source/open/{TASK}?version=0")
        assert response.status_code == 201
        identity = response.json()["snapshot_id"]
        detail = client.get(f"/api/v1/snapshots/{identity}").json()
        assert not detail["missing_media"]
        assert detail["source_version"] == 0
        assert client.get(f"/api/v1/snapshots/{identity}/media", params={"path": detail["trajectory"]["traj"][0]["image"]}).content == PNG
        assert client.post(f"/api/v1/source/open/{TASK}?version=1").status_code == 404
        assert json.loads(client.get(f"/api/v1/snapshots/{identity}/trajectory").content)["task_id"] == TASK
    reader.close()


def test_source_endpoints_require_workspace_auth_outside_demo(tmp_path):
    reader, settings, _, media = source(tmp_path)
    settings = settings.model_copy(update={"demo": False, "api_key": SecretStr("synthetic-key")})
    with TestClient(create_app(settings, MemorySnapshots(), MemoryAssets(), source=reader)) as client:
        assert client.get("/api/v1/source/tasks").status_code == 401
        assert client.post(f"/api/v1/source/open/{TASK}").status_code == 401
        assert not media.reads
        assert client.get("/api/v1/source/tasks", headers={"X-API-Key": "synthetic-key"}).status_code == 200
    reader.close()


def test_media_with_inline_credentials_or_query_is_not_requested(tmp_path):
    reader, _, mongo, media = source(tmp_path)
    mongo.latest.row["traj"][0]["image"] = "http://synthetic.invalid:9000/synthetic/frame.png?secret=synthetic"
    _, _, bindings = reader.fetch(TASK)
    assert not bindings and not media.reads
    reader.close()


def test_old_vlm_bucket_is_read_without_unrestricted_bucket_access(tmp_path):
    reader, _, mongo, media = source(tmp_path)
    mongo.latest.row["traj"][0]["image"] = "http://synthetic.invalid:9000/vlm-api/frame.png"
    _, _, bindings = reader.fetch(TASK)
    assert bindings and media.reads == [("vlm-api", "frame.png")]
    media.reads.clear()
    mongo.latest.row["traj"][0]["image"] = "http://synthetic.invalid:9000/unrelated/frame.png"
    _, _, bindings = reader.fetch(TASK)
    assert not bindings and not media.reads
    reader.close()


def test_bson_small_int64_retains_type_information(tmp_path):
    reader, _, mongo, _ = source(tmp_path)
    mongo.latest.row["unknown_small_long"] = Int64(7)
    raw, _, _ = reader.fetch(TASK)
    assert json.loads(raw)["unknown_small_long"] == {"$numberLong": "7"}
    reader.close()
