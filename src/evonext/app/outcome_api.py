"""Explicit Outcome admission and dispatch, with no model calls in HTTP handlers."""
from uuid import UUID
from fastapi import APIRouter, HTTPException

from evonext.evaluation.outcome import OutcomeRequest
from evonext.evaluation.service import OutcomeService
from evonext.evaluation.store import RunConflict


def public_run(row):
    frozen = row["frozen"]
    return {key: row[key] for key in ("run_id", "snapshot_id", "status", "record")} | {
        "input_hash": row["input_hash"], "policy_version": frozen["policy_version"],
        "request": frozen["request"], "context": frozen["context"], "model": frozen["model"],
        "recovery": "running_after_worker_loss_requires_manual_reconciliation",
    }


def attach_outcome_routes(app, *, evidence, get_store, settings, auth, dispatch=None):
    router = APIRouter(prefix="/api/v1", dependencies=auth)

    def store():
        value = get_store()
        if value is None:
            raise HTTPException(503, "Outcome PostgreSQL storage is not configured")
        return value

    def require(key):
        row = store().get(str(key))
        if row is None:
            raise HTTPException(404, "Outcome run not found")
        return row

    @router.get("/outcome-capabilities")
    def capabilities():
        return {"dispatch_enabled": bool(settings.model_calls_enabled and not settings.demo
                    and settings.model_name and settings.model_api_key and settings.model_base_url),
                "profile": "outcome.instruction-and-before-images.v1"}

    @router.post("/outcome-runs", status_code=202)
    def create(body: OutcomeRequest):
        try:
            return public_run(OutcomeService(evidence, store(), settings).create(body))
        except RunConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/outcome-runs/{run_id}")
    def get(run_id: UUID):
        return public_run(require(run_id))

    @router.get("/snapshots/{snapshot_id}/outcome-runs")
    def list_runs(snapshot_id: str):
        evidence.get_header(snapshot_id)
        return {"items": [public_run(row) for row in store().list(snapshot_id)]}

    @router.post("/outcome-runs/{run_id}/dispatch", status_code=202)
    def submit(run_id: UUID):
        row = require(run_id)
        if not capabilities()["dispatch_enabled"]:
            raise HTTPException(403, "Model dispatch is disabled or unconfigured")
        if row["status"] == "queued":
            try:
                if dispatch:
                    dispatch(str(run_id))
                else:
                    from celery import Celery
                    from evonext.config import secret
                    with Celery("evonext-outcome-api", broker=secret(settings.broker_url)) as queue:
                        queue.send_task("evonext.outcome", args=[str(run_id)], queue="evonext.bulk",
                                        retry=False)
            except Exception as exc:
                raise HTTPException(503, "Queue delivery unconfirmed; read the same run and dispatch again") from exc
        return public_run(require(run_id))

    app.include_router(router)
