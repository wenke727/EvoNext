"""EvoLoop Mongo read profile. No legacy DAL imports, indexes or legacy writes."""
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from evonext.contracts.trajectory import ContractError, Snapshot, encode_json
from evonext.evidence.index import EvidenceNotFound
from evonext.evidence.packages import media_type


def safe_numbers(value):
    if isinstance(value, dict):
        return {key: safe_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [safe_numbers(item) for item in value]
    from bson.int64 import Int64
    if isinstance(value, Int64) or (type(value) is int and abs(value) > 9007199254740991):
        return {"$numberLong": str(value)}
    return value


class SourceUnavailable(RuntimeError):
    pass


class LegacyMongoSource:
    profile = "evoloop.mongo-read.v1"

    def __init__(self, settings, mongo=None, media=None):
        try:
            from dotenv import dotenv_values
            from pymongo import MongoClient
            import urllib3
            from minio import Minio
        except ImportError as exc:
            raise SourceUnavailable("旧数据源需要安装 infra 依赖") from exc
        path = Path(settings.legacy_env_file).expanduser()
        if not path.is_file():
            raise SourceUnavailable("旧数据源配置文件不可用")
        config = dotenv_values(path)
        if not config.get("MONGO_URI"):
            raise SourceUnavailable("旧数据源缺少 Mongo 连接配置")
        if not config.get("REVIEWER_MONGO_COLLECTION", "dataset").strip():
            raise SourceUnavailable("旧数据源集合配置不可为空")
        self.settings = settings
        self.mongo = mongo or MongoClient(config["MONGO_URI"], serverSelectionTimeoutMS=4000,
            connectTimeoutMS=4000, socketTimeoutMS=10000, connect=False, appname="EvoNext-readonly")
        database = self.mongo[config.get("REVIEWER_MONGO_DB") or "tasks"]
        collection = config.get("REVIEWER_MONGO_COLLECTION") or "dataset"
        self.latest, self.history = database[collection + "_latest"], database[collection + "_history"]
        endpoint = config.get("MINIO_ENDPOINT") or ""
        parsed = urlsplit(endpoint if "://" in endpoint else "http://" + endpoint)
        self.media_origin = parsed.netloc
        self.bucket = config.get("IMAGE_MINIO_BUCKET") or ""
        self.buckets = {self.bucket, config.get("VLM_MINIO_BUCKET") or "vlm-api"} - {""}
        self.pool = urllib3.PoolManager(timeout=urllib3.Timeout(connect=3, read=10), retries=False)
        secure = (config.get("MINIO_SECURE") or "false").lower() in {"true", "1", "yes"}
        self.media = media or (Minio(parsed.netloc, access_key=config.get("MINIO_ACCESS_KEY"),
            secret_key=config.get("MINIO_SECRET_KEY"), secure=secure, http_client=self.pool)
            if parsed.netloc and self.bucket else None)

    def close(self):
        self.mongo.close()
        self.pool.clear()

    @staticmethod
    def summary(row):
        version = (row.get("_version_info") or {}).get("version_number")
        return {"task_id": row["task_id"], "instruction": str(row.get("instruction", ""))[:600],
            "source_version": int(version) if isinstance(version, int) and not isinstance(version, bool) else None,
            "step_count": row.get("step_count", 0)}

    def list(self, after="", limit=30):
        match = {"task_id": {"$type": "string"}}
        if after:
            match["task_id"]["$lt"] = after
        rows = self.latest.aggregate([
            {"$match": match}, {"$sort": {"task_id": -1}}, {"$limit": limit},
            {"$project": {"_id": 0, "task_id": 1, "instruction": 1, "_version_info": 1,
                "step_count": {"$cond": [{"$isArray": "$traj"}, {"$size": "$traj"}, 0]}}},
        ], maxTimeMS=5000)
        return [self.summary(row) for row in rows]

    def fetch(self, task_id, version=None):
        from bson.json_util import RELAXED_JSON_OPTIONS, dumps
        from minio.error import S3Error
        if not task_id or len(task_id) > 256:
            raise ContractError("Task ID 必须为非空字符串")
        if version is not None and (type(version) is not int or not 0 <= version <= 9007199254740991):
            raise ContractError("来源版本必须为非负整数，0 有效")
        query = {"task_id": task_id}
        if version is not None:
            query["_version_info.version_number"] = version
        document = (self.history.find_one(query, max_time_ms=5000) if version is not None else None)
        if document is None:
            document = self.latest.find_one(query, max_time_ms=5000)
        if document is None:
            raise EvidenceNotFound("旧库中未找到该 Task ID 或指定版本")
        actual = (document.get("_version_info") or {}).get("version_number")
        if not isinstance(actual, int) or isinstance(actual, bool) or not 0 <= actual <= 9007199254740991:
            raise ContractError("来源没有明确版本，无法固定读取")
        if version is not None and actual != version:
            raise ContractError("来源版本不匹配；不回退到其他版本")
        # Mongo has no original JSON file bytes. Extended JSON retains BSON-only fields.
        raw = encode_json(json.loads(dumps(safe_numbers(document), json_options=RELAXED_JSON_OPTIONS)))
        if len(raw) > self.settings.max_file_bytes:
            raise ContractError("旧任务超过当前读取大小上限")
        metadata = {"source_kind": "legacy_mongo", "do_not_train": True,
            "origin": {"system": self.profile, "task_id": task_id, "version_number": int(actual)},
            "encoding": "bson-relaxed-extended-json+safe-integers", "portable_bundle": False,
            "transformations": ["Mongo document encoded as Extended JSON; original media locators retained", "BSON Int64 and unsafe integers represented as $numberLong"]}
        Snapshot.create(raw, encode_json(metadata), max_steps=self.settings.max_steps)
        bindings, unresolved, total = {}, [], len(raw)
        for step in document["traj"]:
            locator = step.get("image")
            if not locator or locator in bindings or locator in unresolved:
                continue
            target = urlsplit(locator)
            parts = unquote(target.path).lstrip("/").split("/", 1)
            if (self.media is None or target.scheme not in {"http", "https"}
                    or target.netloc != self.media_origin or target.username or target.password
                    or target.query or target.fragment
                    or len(parts) != 2 or parts[0] not in self.buckets):
                unresolved.append(locator)
                continue
            try:
                response = self.media.get_object(parts[0], parts[1])
            except S3Error as exc:
                if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                    unresolved.append(locator)
                    continue
                raise
            try:
                data = response.read(self.settings.max_file_bytes + 1)
            finally:
                response.close()
                response.release_conn()
            if len(data) > self.settings.max_file_bytes:
                raise ContractError("来源截图超过当前大小上限")
            total += len(data)
            if total > self.settings.max_upload_bytes:
                raise ContractError("来源轨迹与截图超过当前读取总量上限")
            media_type(data)
            bindings[locator] = data
        metadata["unresolved_media"] = unresolved
        return raw, metadata, bindings

    def capture(self, task_id, version, service):
        raw, metadata, media = self.fetch(task_id, version)
        # Only the new Evidence owner accepts captured bytes; legacy clients expose no writes.
        bindings = {locator: service.assets.put(data) for locator, data in media.items()}
        snapshot = Snapshot.create(raw, encode_json(metadata), bindings, max_steps=self.settings.max_steps)
        return service.accept(snapshot)
