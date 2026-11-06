"""A small working vertical slice: import -> inspect -> lossless export."""
import hmac
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from .config import Settings, secret
from .domain import ContractError, Snapshot, encode_json, load_json
from .legacy import BridgeUncertain, LegacyClient
from .packages import export_bundle, import_bundle, media_type
from .storage import stores


async def limited_body(request, maximum):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > maximum:
            raise HTTPException(413, "Request exceeds configured size limit")
    return bytes(body)


def create_app(settings=None, repository=None, assets=None):
    settings = settings or Settings()
    if (repository is None) != (assets is None):
        raise ValueError("Inject both repository and assets, or neither")
    repository, assets = (repository, assets) if repository is not None else stores(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        repository.close()

    app = FastAPI(title="EvoNext", version="0.1.0", lifespan=lifespan)

    async def authenticate(request: Request):
        if settings.demo:
            return
        provided = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(provided, secret(settings.api_key)):
            raise HTTPException(401, "Authentication required")

    auth = [Depends(authenticate)]

    @app.exception_handler(ContractError)
    async def invalid_contract(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=400)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse({"error": "Invalid request", "fields": [list(e["loc"]) for e in exc.errors()]}, status_code=422)

    @app.exception_handler(PermissionError)
    async def denied(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=403)

    @app.exception_handler(BridgeUncertain)
    async def uncertain(request, exc):
        return JSONResponse({"error": str(exc), "retry_safe": False}, status_code=502)

    @app.exception_handler(httpx.HTTPError)
    async def upstream_failed(request, exc):
        return JSONResponse({"error": "Legacy service read failed"}, status_code=502)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    def snapshot_or_404(snapshot_id):
        if len(snapshot_id) != 64 or any(c not in "0123456789abcdef" for c in snapshot_id):
            raise HTTPException(404, "Snapshot not found")
        snapshot = repository.get(snapshot_id)
        if snapshot is None:
            raise HTTPException(404, "Snapshot not found")
        return snapshot

    @app.get("/health/live")
    def live():
        return {"status": "alive", "version": "0.1.0"}

    @app.get("/health/ready", dependencies=auth)
    def ready():
        checks = {}
        for name, resource in (("mongo", repository), ("minio", assets)):
            try:
                resource.ping()
                checks[name] = "demo_memory" if settings.demo else "ready"
            except Exception as exc:
                checks[name] = "unavailable:" + type(exc).__name__
        if settings.postgres_dsn and not settings.demo:
            try:
                from .ledger import Ledger
                ledger = Ledger(secret(settings.postgres_dsn))
                try:
                    ledger.ping()
                    checks["postgres"] = "ready"
                finally:
                    ledger.close()
            except Exception as exc:
                checks["postgres"] = "unavailable:" + type(exc).__name__
        else:
            checks["postgres"] = "not_configured"
        ok = not any(v.startswith("unavailable") for v in checks.values())
        return JSONResponse({"ready": ok, "demo": settings.demo, "checks": checks,
                             "production_accepted": False}, status_code=200 if ok else 503)

    @app.get("/api/v1/snapshots", dependencies=auth)
    def list_snapshots(after: str = "", limit: int = Query(50, ge=1, le=100)):
        items = repository.list(after, limit)
        return {"items": items, "next_cursor": items[-1]["snapshot_id"] if len(items) == limit else None}

    @app.post("/api/v1/snapshots", dependencies=auth, status_code=201, openapi_extra={
        "requestBody": {"required": True, "content": {"application/json": {"schema": {
            "type": "object", "required": ["trajectory"], "additionalProperties": False,
            "properties": {"trajectory": {"type": "object"}, "metadata": {"type": "object"}}}}}}})
    async def import_json(request: Request):
        value = load_json(await limited_body(request, settings.max_file_bytes))
        if set(value) - {"trajectory", "metadata"} or "trajectory" not in value:
            raise ContractError("Use an envelope with trajectory and optional metadata")
        snapshot = Snapshot.create(encode_json(value["trajectory"]), encode_json(value.get("metadata", {})),
                                   max_steps=settings.max_steps)
        await run_in_threadpool(repository.put, snapshot)
        return {**snapshot.summary(), "media_complete": all(s.get("image") is None for s in snapshot.document["traj"])}

    @app.post("/api/v1/bundles", dependencies=auth, status_code=201, openapi_extra={
        "requestBody": {"required": True, "content": {"application/zip": {"schema": {
            "type": "string", "format": "binary"}}}}})
    async def import_zip(request: Request):
        raw = await limited_body(request, settings.max_upload_bytes)
        snapshot = await run_in_threadpool(import_bundle, raw, assets, settings)
        await run_in_threadpool(repository.put, snapshot)
        return {**snapshot.summary(), "media_complete": True}

    @app.get("/api/v1/snapshots/{snapshot_id}", dependencies=auth)
    def detail(snapshot_id: str):
        snapshot = snapshot_or_404(snapshot_id)
        return {**snapshot.summary(), "instruction": snapshot.document["instruction"], "trajectory": snapshot.document, "metadata": snapshot.metadata,
                "manifest": snapshot.manifest,
                "missing_media": sorted({s["image"] for s in snapshot.document["traj"] if s.get("image") and s["image"] not in snapshot.media})}

    @app.get("/api/v1/snapshots/{snapshot_id}/trajectory", dependencies=auth)
    def download_trajectory(snapshot_id: str):
        return Response(snapshot_or_404(snapshot_id).trajectory_json, media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="trajectory.json"'})

    @app.get("/api/v1/snapshots/{snapshot_id}/bundle", dependencies=auth)
    def download_bundle(snapshot_id: str):
        raw = export_bundle(snapshot_or_404(snapshot_id), assets, settings.max_upload_bytes)
        return Response(raw, media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="opencua-bundle.zip"'})

    @app.get("/api/v1/snapshots/{snapshot_id}/media", dependencies=auth)
    def image(snapshot_id: str, path: str):
        digest = snapshot_or_404(snapshot_id).media.get(path)
        if digest is None:
            raise HTTPException(404, "Media is not bound to this snapshot")
        data = assets.get(digest)
        return Response(data, media_type=media_type(data),
                        headers={"Content-Security-Policy": "default-src 'none'; sandbox"})

    @app.post("/api/v1/bridge/import/{task_id}", dependencies=auth, status_code=201)
    def import_legacy(task_id: str, version: int | None = Query(None, ge=0)):
        bridge = LegacyClient(settings)
        try:
            snapshot = bridge.fetch(task_id, version)
            repository.put(snapshot)
            return {**snapshot.summary(), "media_complete": False,
                    "warning": "External screenshots are preserved as locators, not downloaded"}
        finally:
            bridge.close()

    @app.post("/api/v1/bridge/publish/{snapshot_id}", dependencies=auth)
    def publish_legacy(snapshot_id: str, dry_run: bool = True, allow_projection_loss: bool = False):
        bridge = LegacyClient(settings)
        try:
            return bridge.publish(snapshot_or_404(snapshot_id), assets,
                                  dry_run=dry_run, allow_projection_loss=allow_projection_loss)
        finally:
            bridge.close()

    return app
