"""Thin HTTP assembly; local candidate storage is explicitly configured."""
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from evonext.config import secret
from evonext.skills.workshop import Workshop
from evonext.skills.workshop.drafts import Drafts
from evonext.skills.workshop.service import AuthorRequest, preview as preview_authoring, status, submit


class ManualDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    skill_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    base_revision: str | None = None
    files: dict[str, str] = Field(max_length=51)
    source_snapshots: list[str] = Field(min_length=1, max_length=4)
    reason: str = Field(min_length=1, max_length=4000)


class HumanReview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    verdict: Literal["approved", "rejected", "needs_evidence"]
    notes: str = Field(min_length=1, max_length=8000)


def configured_workshop(settings):
    if not settings.workshop_root or not settings.workshop_owner:
        raise HTTPException(503, "Configure an explicit local Workshop root and owner")
    if not Path(settings.workshop_root).is_absolute():
        raise HTTPException(503, "Workshop root must be an absolute local path")
    return Workshop(settings.workshop_root, settings.workshop_owner)


def attach_workshop_routes(app, *, evidence, get_ledger, get_cases, settings, auth):
    def drafts():
        return Drafts(configured_workshop(settings))

    def actor():
        if not settings.review_operator_id:
            raise HTTPException(503, "Review operator is not configured")
        return settings.review_operator_id

    @app.get("/api/v1/workshop", dependencies=auth)
    def inventory():
        library = configured_workshop(settings)
        return {"skills": library.list(), "drafts": Drafts(library).list(),
                "owner": library.owner, "model_enabled": settings.model_calls_enabled}

    @app.get("/api/v1/workshop/skills/{skill_id}", dependencies=auth)
    def skill(skill_id: str, revision: str | None = None):
        library = configured_workshop(settings)
        with library.lock:
            record, _ = library.read(skill_id, revision)
            return {"record": record, "files": library.files(skill_id, revision),
                    "head": library.current(skill_id), "history": library.history(skill_id)}

    @app.get("/api/v1/workshop/skills/{skill_id}/export/{revision}", dependencies=auth)
    def export(skill_id: str, revision: str):
        return configured_workshop(settings).export(skill_id, revision).model_dump(mode="json")

    @app.post("/api/v1/workshop/drafts", dependencies=auth, status_code=201)
    def propose(body: ManualDraft):
        actor()
        for snapshot_id in body.source_snapshots:
            if evidence.get(snapshot_id) is None:
                raise HTTPException(404, "Source snapshot not found")
        return drafts().create(skill_id=body.skill_id, base_revision=body.base_revision,
            files=body.files, sources=body.source_snapshots, reason=body.reason)

    @app.get("/api/v1/workshop/drafts/{draft_id}", dependencies=auth)
    def read_draft(draft_id: str):
        return drafts().get(draft_id)

    @app.post("/api/v1/workshop/drafts/{draft_id}/review", dependencies=auth)
    def review(draft_id: str, body: HumanReview):
        return drafts().review(draft_id, verdict=body.verdict, notes=body.notes, actor=actor())

    @app.post("/api/v1/workshop/drafts/{draft_id}/commit", dependencies=auth)
    def commit(draft_id: str):
        return drafts().commit(draft_id, actor())

    @app.post("/api/v1/workshop/drafts/{draft_id}/discard", dependencies=auth)
    def discard(draft_id: str):
        actor()
        return drafts().discard(draft_id)

    @app.post("/api/v1/workshop/preview", dependencies=auth)
    def preview(body: AuthorRequest):
        return preview_authoring(body, configured_workshop(settings), evidence, settings, get_cases())

    @app.post("/api/v1/workshop/operations", dependencies=auth, status_code=202)
    def author(body: AuthorRequest):
        actor()
        if not settings.model_calls_enabled:
            raise PermissionError("Model calls are explicitly disabled")
        ledger = get_ledger()
        if ledger is None:
            raise HTTPException(503, "Workshop authoring requires PostgreSQL and migrations")
        result = submit(body, configured_workshop(settings), evidence, ledger, get_cases(), settings=settings)
        if result["status"] == "pending":
            from celery import Celery
            sender = Celery("evonext", broker=secret(settings.broker_url))
            try:
                sender.send_task("evonext.workshop", args=[body.operation_id],
                                 queue="evonext.bulk", retry=False)
            except Exception as exc:
                raise HTTPException(503, "Request saved; reuse operation_id to reconcile delivery") from exc
            finally:
                sender.close()
        return result

    @app.get("/api/v1/workshop/operations/{operation_id}", dependencies=auth)
    def operation(operation_id: str):
        ledger = get_ledger()
        if ledger is None:
            raise HTTPException(503, "Workshop authoring requires PostgreSQL")
        result = status(operation_id, ledger, configured_workshop(settings).owner)
        if result is None:
            raise HTTPException(404, "Workshop operation not found")
        return result
