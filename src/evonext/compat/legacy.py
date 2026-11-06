"""Documented HTTP boundary only. No imports from the previous implementation."""
import copy
import json
from urllib.parse import quote, urlsplit

import httpx

from evonext.config import secret
from evonext.contracts.trajectory import ContractError, Snapshot, encode_json
from evonext.evidence.packages import media_type


class BridgeUncertain(RuntimeError):
    pass


class LegacyClient:
    def __init__(self, settings, transport=None):
        parsed = urlsplit(settings.legacy_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username:
            raise ContractError("Configure a trusted legacy HTTP endpoint")
        if parsed.query or parsed.fragment:
            raise ContractError("Legacy endpoint cannot contain query credentials")
        self.settings = settings
        self.client = httpx.Client(base_url=settings.legacy_base_url.rstrip("/"),
            headers={"X-API-Key": secret(settings.legacy_api_key), "Accept": "application/json"},
            timeout=30, follow_redirects=False, transport=transport)

    def close(self):
        self.client.close()

    def fetch(self, task_id, version=None):
        if task_id in {".", ".."} or any(c in task_id for c in "/\\?#"):
            raise ContractError("Unsupported legacy task identifier")
        if version is not None and (type(version) is not int or version < 0):
            raise ContractError("Version must be a non-negative integer")
        params = {"format": "json"}
        if version is not None:
            params["version"] = str(version)
        with self.client.stream("GET", "/api/task/" + quote(task_id, safe=""), params=params) as response:
            response.raise_for_status()
            chunks = bytearray()
            for chunk in response.iter_bytes():
                chunks.extend(chunk)
                if len(chunks) > self.settings.max_file_bytes:
                    raise ContractError("Legacy task exceeds input limit")
        from evonext.contracts.trajectory import load_json
        document = load_json(bytes(chunks))
        if document.get("task_id") != task_id:
            raise ContractError("Legacy response task identity mismatch")
        info = document.get("_version_info")
        actual = info.get("version_number") if isinstance(info, dict) else None
        if version is not None and (type(actual) is not int or actual != version):
            raise ContractError("Legacy fixed-version response is unverified; no latest fallback")
        metadata = {"origin": {"system": "legacy_api", "task_id": task_id,
                                "version_number": actual}, "do_not_train": True}
        return Snapshot.create(bytes(chunks), encode_json(metadata),
                               max_steps=self.settings.max_steps)

    def prepare_publish(self, snapshot, assets):
        doc = snapshot.document
        steps, files = [], {}
        for index, original in enumerate(doc["traj"]):
            step = copy.deepcopy(original)
            value = step.get("value", {})
            if any(k in value for k in ("code", "code_norm", "normalized_tool_call", "action_2_tool_call")):
                raise ContractError("Legacy action fields require explicit migration, not online guessing")
            image = step.get("image")
            if image is not None:
                digest = snapshot.media.get(image)
                if digest is None:
                    raise ContractError("Legacy publish requires bound media; external URLs are not fetched")
                data = assets.get(digest)
                key = f"image_{index}"
                files[key] = (f"{key}.bin", data, media_type(data))
                step["image"] = key
            steps.append(step)
        payload = {"task_id": doc["task_id"], "instruction": doc["instruction"],
                   "steps": steps, "source": "EvoNext", "existing_task_mode": "skip",
                   "auto_evaluate": False}
        # A legacy upload is a projection, not a claim that legacy ingestion preserves every field.
        # Raw JSON/package export is the lossless interchange path.
        preview = {"snapshot_id": snapshot.id, "task_id": doc["task_id"],
                   "mode": "create_or_skip", "step_count": len(steps), "image_count": len(files),
                   "lossless": False, "omitted_top_level_fields": sorted(set(doc) - {"task_id", "instruction", "traj"}),
                   "metadata_transferred": False, "readback_verified": False,
                   "warning": "Legacy ingest may transform fields; original snapshot remains unchanged"}
        return payload, files, preview

    def publish(self, snapshot, assets, *, dry_run=True, allow_projection_loss=False):
        payload, files, preview = self.prepare_publish(snapshot, assets)
        if dry_run:
            return {**preview, "status": "preview_only"}
        if not self.settings.legacy_writes or not allow_projection_loss:
            raise PermissionError("Legacy writes require configuration and explicit projection consent")
        # Multipart is retained even for a trajectory without images.
        parts = {"payload": (None, json.dumps(payload, ensure_ascii=False), "application/json"), **files}
        try:
            response = self.client.post("/api/rollout/upload", files=parts)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise BridgeUncertain("Legacy acknowledgement unavailable; reconcile before retry") from exc
        return {**preview, "status": "submitted_not_verified", "legacy_receipt": response.json()}
