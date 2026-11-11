"""A small working vertical slice: import -> inspect -> lossless export."""
import hmac
from threading import Lock
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from evonext.config import Settings, secret
from evonext.contracts.trajectory import ContractError
from evonext.compat.legacy import BridgeUncertain, LegacyClient
from evonext.compat.mongo_source import LegacyMongoSource, SourceUnavailable
from evonext.evidence.packages import media_type
from evonext.evidence.service import EvidenceService
from evonext.evidence.index import EvidenceNotFound, StoredEvidenceError
from evonext.evidence.store import stores
from evonext.evaluation.inputs import InputOptions, prepare_input
from evonext.evaluation.service import (EvalRequest, submit, status as evaluation_status,
                                        FindingConfirmation, finding_proposal)
from evonext.review.store import MemoryCases, PostgresCases
from evonext.app.case_api import attach_case_routes


async def limited_body(request, maximum):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > maximum:
            raise HTTPException(413, "Request exceeds configured size limit")
    return bytes(body)


def create_app(settings=None, repository=None, assets=None, case_store=None, *, source=None):
    settings = settings or Settings()
    if (repository is None) != (assets is None):
        raise ValueError("Inject both repository and assets, or neither")
    owns_stores = repository is None
    repository, assets = (repository, assets) if repository is not None else stores(settings)

    service = EvidenceService(repository, assets, settings)

    owns_source = source is None
    source_lock = Lock()

    def source_reader():
        nonlocal source
        with source_lock:
            if source is None:
                if not settings.legacy_env_file:
                    raise HTTPException(503, "旧数据源尚未配置")
                source = LegacyMongoSource(settings)
        return source

    ledger = None
    ledger_error = "NotInitialized"
    active_case_store = case_store if case_store is not None else (MemoryCases() if settings.demo else None)

    @asynccontextmanager
    async def lifespan(app):
        nonlocal ledger, ledger_error, active_case_store
        if settings.postgres_dsn and not settings.demo:
            try:
                from evonext.operations.ledger import Ledger
                ledger = Ledger(secret(settings.postgres_dsn))
                if active_case_store is None and hasattr(ledger, "engine"):
                    active_case_store = PostgresCases(ledger.engine)
            except Exception as exc:
                ledger_error = type(exc).__name__
        try:
            yield
        finally:
            try:
                if owns_source and source is not None:
                    source.close()
                if ledger is not None:
                    ledger.close()
            finally:
                if owns_stores:
                    try:
                        repository.close()
                    finally:
                        assets.close()

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

    @app.exception_handler(EvidenceNotFound)
    async def missing_evidence(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=404)

    @app.exception_handler(StoredEvidenceError)
    async def corrupt_evidence(request, exc):
        return JSONResponse({"error": "Stored evidence integrity check failed"}, status_code=500)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse({"error": "Invalid request", "fields": [list(e["loc"]) for e in exc.errors()]}, status_code=422)

    @app.exception_handler(PermissionError)
    async def denied(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=403)

    @app.exception_handler(BridgeUncertain)
    async def uncertain(request, exc):
        return JSONResponse({"error": str(exc), "retry_safe": False}, status_code=502)

    @app.exception_handler(SourceUnavailable)
    async def unavailable_source(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=503)

    @app.exception_handler(httpx.HTTPError)
    async def upstream_failed(request, exc):
        return JSONResponse({"error": "Legacy service read failed"}, status_code=502)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    def check_snapshot_id(snapshot_id):
        if len(snapshot_id) != 64 or any(c not in "0123456789abcdef" for c in snapshot_id):
            raise HTTPException(404, "Snapshot not found")

    def snapshot_or_404(snapshot_id):
        check_snapshot_id(snapshot_id)
        snapshot = service.get(snapshot_id)
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
            if ledger is None:
                checks["postgres"] = "unavailable:" + ledger_error
            else:
                try:
                    ledger.ping()
                    checks["postgres"] = "ready"
                except Exception as exc:
                    checks["postgres"] = "unavailable:" + type(exc).__name__
        else:
            checks["postgres"] = "not_configured"
        ok = not any(v.startswith("unavailable") for v in checks.values())
        return JSONResponse({"ready": ok, "demo": settings.demo, "checks": checks,
                             "source_mode": "legacy_mongo" if settings.legacy_env_file else "snapshots",
                             "production_accepted": False}, status_code=200 if ok else 503)

    @app.get("/api/v1/source/tasks", dependencies=auth)
    def source_tasks(after: str = "", limit: int = Query(30, ge=1, le=100)):
        try:
            items = source_reader().list(after, limit)
            return {"items": items, "next_cursor": items[-1]["task_id"] if len(items) == limit else None}
        except (ContractError, EvidenceNotFound, SourceUnavailable, HTTPException):
            raise
        except Exception as exc:
            raise HTTPException(502, "旧数据源读取失败，请检查连接配置") from exc

    @app.post("/api/v1/source/open/{task_id}", dependencies=auth, status_code=201)
    def open_source_task(task_id: str, version: int | None = Query(None, ge=0)):
        try:
            snapshot = source_reader().capture(task_id, version, service)
            return {**snapshot.summary(), "profile": LegacyMongoSource.profile,
                    "portable_bundle": False}
        except (ContractError, EvidenceNotFound, SourceUnavailable, HTTPException):
            raise
        except Exception as exc:
            raise HTTPException(502, "旧数据源读取失败；未修改旧库") from exc

    @app.get("/api/v1/snapshots", dependencies=auth)
    def list_snapshots(after: str = "", limit: int = Query(50, ge=1, le=100)):
        items = service.list(after, limit)
        return {"items": items, "next_cursor": items[-1]["snapshot_id"] if len(items) == limit else None}

    @app.post("/api/v1/snapshots", dependencies=auth, status_code=201, openapi_extra={
        "requestBody": {"required": True, "content": {"application/json": {"schema": {
            "type": "object", "required": ["trajectory"], "additionalProperties": False,
            "properties": {"trajectory": {"type": "object"}, "metadata": {"type": "object"}}}}}}})
    async def import_json(request: Request):
        raw = await limited_body(request, settings.max_file_bytes)
        snapshot = await run_in_threadpool(service.import_json, raw)
        return {**snapshot.summary(), "media_complete": all(s.get("image") is None for s in snapshot.document["traj"])}

    @app.post("/api/v1/bundles", dependencies=auth, status_code=201, openapi_extra={
        "requestBody": {"required": True, "content": {"application/zip": {"schema": {
            "type": "string", "format": "binary"}}}}})
    async def import_zip(request: Request):
        raw = await limited_body(request, settings.max_upload_bytes)
        snapshot = await run_in_threadpool(service.import_zip, raw)
        return {**snapshot.summary(), "media_complete": True}

    @app.get("/api/v1/snapshots/{snapshot_id}", dependencies=auth)
    def detail(snapshot_id: str):
        snapshot = snapshot_or_404(snapshot_id)
        document, media = snapshot.document, snapshot.media
        return {**snapshot.summary(), "instruction": document["instruction"], "trajectory": document, "metadata": snapshot.metadata,
                "manifest": snapshot.manifest,
                "missing_media": sorted({s["image"] for s in document["traj"] if s.get("image") and s["image"] not in media})}

    @app.get("/api/v1/snapshots/{snapshot_id}/header", dependencies=auth)
    def header(snapshot_id: str):
        check_snapshot_id(snapshot_id)
        return service.get_header(snapshot_id)

    @app.post("/api/v1/snapshots/{snapshot_id}/evaluation-input", dependencies=auth)
    def evaluation_input(snapshot_id: str, options: InputOptions):
        return prepare_input(snapshot_or_404(snapshot_id), options)

    @app.post("/api/v1/snapshots/{snapshot_id}/evaluations", dependencies=auth, status_code=202)
    def start_evaluation(snapshot_id: str, request: EvalRequest):
        if not settings.model_calls_enabled:
            raise PermissionError("Model calls are explicitly disabled")
        if ledger is None:
            raise HTTPException(503, "Evaluation requires PostgreSQL and migrations")
        result = submit(snapshot_or_404(snapshot_id), request, ledger)
        if result["status"] == "pending":
            from celery import Celery
            sender = Celery("evonext", broker=secret(settings.broker_url))
            try:
                sender.send_task("evonext.evaluate", args=[request.operation_id], queue="evonext.bulk",
                                 retry=False)
            except Exception as exc:
                raise HTTPException(503, "Request saved; queue delivery unverified. Reuse operation_id to reconcile.") from exc
            finally:
                sender.close()
        return result

    @app.get("/api/v1/evaluations/{operation_id}", dependencies=auth)
    def read_evaluation(operation_id: str):
        if ledger is None:
            raise HTTPException(503, "Evaluation store unavailable")
        result = evaluation_status(operation_id, ledger)
        if result is None:
            raise HTTPException(404, "Evaluation not found")
        return result

    @app.get("/api/v1/snapshots/{snapshot_id}/trajectory", dependencies=auth)
    def download_trajectory(snapshot_id: str):
        return Response(snapshot_or_404(snapshot_id).trajectory_json, media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="trajectory.json"'})

    @app.get("/api/v1/snapshots/{snapshot_id}/bundle", dependencies=auth)
    def download_bundle(snapshot_id: str):
        raw = service.export(snapshot_or_404(snapshot_id))
        return Response(raw, media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="opencua-bundle.zip"'})

    @app.get("/api/v1/snapshots/{snapshot_id}/media", dependencies=auth)
    def image(snapshot_id: str, path: str):
        check_snapshot_id(snapshot_id)
        data = service.read_media(snapshot_id, path)
        return Response(data, media_type=media_type(data),
                        headers={"Content-Security-Policy": "default-src 'none'; sandbox"})

    @app.post("/api/v1/bridge/import/{task_id}", dependencies=auth, status_code=201)
    def import_legacy(task_id: str, version: int | None = Query(None, ge=0)):
        bridge = LegacyClient(settings)
        try:
            snapshot = bridge.fetch(task_id, version)
            service.accept(snapshot)
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

    @app.post("/api/v1/evaluations/{operation_id}/findings/{index}/cases",
              dependencies=auth, status_code=201)
    def confirm_finding(operation_id: str, index: int, body: FindingConfirmation):
        if ledger is None or active_case_store is None:
            raise HTTPException(503, "Evaluation and Case storage are required")
        if not settings.review_operator_id:
            raise HTTPException(503, "Review operator is not configured")
        saved = evaluation_status(operation_id, ledger)
        if saved is None or saved["result"] is None:
            raise HTTPException(404, "Completed evaluation not found")
        from evonext.review.service import CaseService
        from evonext.review.contracts import CaseConflict
        try:
            proposal = finding_proposal(saved["result"], index, body)
            return CaseService(service, active_case_store).propose(
                proposal, actor=settings.review_operator_id)
        except CaseConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    attach_case_routes(app, evidence=service, get_store=lambda: active_case_store,
                       auth=auth, settings=settings)
    return app
