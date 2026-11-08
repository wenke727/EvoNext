"""Case, shared correction draft, immutable review and preview HTTP adapter."""
import re
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query

from evonext.review.contracts import (CaseConflict, CaseNotFound, CaseProposal,
                                      ReviewDecision, StaleCase)
from evonext.review.corrections import DraftCommand, FrozenReviewCommand
from evonext.review.service import CaseService


def attach_case_routes(app, *, evidence, get_store, auth, settings):
    router = APIRouter(prefix="/api/v1", dependencies=auth)

    def service():
        store = get_store()
        if store is None:
            raise HTTPException(503, "Review/Case storage not configured")
        return CaseService(evidence, store)

    def actor(for_decision=False):
        if settings.demo:
            return "demo-operator"
        if for_decision and not settings.review_operator_id:
            raise HTTPException(403, "Review decisions require an explicitly configured operator")
        return settings.review_operator_id or "api-key-service"

    def expected(if_match):
        if if_match is None:
            raise HTTPException(428, "If-Match revision is required")
        if not re.fullmatch(r'"(0|[1-9][0-9]*)"', if_match):
            raise HTTPException(400, 'If-Match must be a quoted non-negative revision')
        return int(if_match[1:-1])

    @router.post("/cases", status_code=201)
    def create_case(body: CaseProposal):
        try:
            return service().propose(body, actor=actor())
        except CaseConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except CaseNotFound as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/cases")
    def case_queue(
        status: Literal["pending", "needs_evidence", "operator_confirmed", "rejected"] | None = None,
        after: str = "", limit: int = Query(50, ge=1, le=100),
    ):
        if after and not re.fullmatch(r"[0-9a-f-]{36}", after):
            raise HTTPException(400, "Invalid Case cursor")
        items = service().queue(status=status, after=after, limit=limit)
        return {"items": items, "next_cursor": items[-1]["case_id"] if len(items) == limit else None}

    @router.get("/cases/{case_id}")
    def get_case(case_id: UUID):
        try:
            return service().get(str(case_id))
        except CaseNotFound as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/snapshots/{snapshot_id}/cases")
    def list_cases(snapshot_id: str, limit: int = Query(50, ge=1, le=100)):
        if not re.fullmatch("[0-9a-f]{64}", snapshot_id):
            raise HTTPException(404, "Frozen snapshot not found")
        try:
            return {"items": service().for_snapshot(snapshot_id, limit)}
        except CaseNotFound as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/cases/{case_id}/draft")
    def get_draft(case_id: UUID):
        try:
            return service().draft(str(case_id))
        except CaseNotFound as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.put("/cases/{case_id}/draft")
    def save_draft(case_id: UUID, body: DraftCommand, if_match: str | None = Header(None)):
        if expected(if_match) != body.expected_draft_revision:
            raise HTTPException(400, "If-Match and expected_draft_revision differ")
        try:
            return service().save_draft(str(case_id), body, actor=actor())
        except CaseNotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except StaleCase as exc:
            raise HTTPException(412, str(exc)) from exc
        except CaseConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/cases/{case_id}/review")
    def decide_case(case_id: UUID, body: ReviewDecision | FrozenReviewCommand,
                    if_match: str | None = Header(None)):
        revision = expected(if_match)
        try:
            if isinstance(body, FrozenReviewCommand):
                if revision != body.expected_review_revision:
                    raise HTTPException(400, "Review version does not match If-Match")
                return service().decide_frozen(str(case_id), body, actor=actor(for_decision=True))
            return service().decide(str(case_id), revision, body,
                                    actor=actor(for_decision=True))
        except CaseNotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except StaleCase as exc:
            raise HTTPException(412, str(exc)) from exc
        except CaseConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/cases/{case_id}/reviews/{revision}")
    def get_review(case_id: UUID, revision: int):
        if revision < 1:
            raise HTTPException(404, "Review revision not found")
        try:
            return service().review(str(case_id), revision)
        except CaseNotFound as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/cases/{case_id}/reviews/{revision}/previews/{purpose}")
    def preview(case_id: UUID, revision: int,
                purpose: Literal["diagnosis", "localization", "sft", "dpo"]):
        if revision < 1:
            raise HTTPException(404, "Review revision not found")
        try:
            return service().preview(str(case_id), revision, purpose)
        except CaseNotFound as exc:
            raise HTTPException(404, str(exc)) from exc

    app.include_router(router)
