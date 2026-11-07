"""A narrow Case review API. No task mutation, grading or device side effects."""
import re
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from evonext.review.contracts import (CaseConflict, CaseNotFound, CaseProposal,
                                      ReviewDecision, StaleCase)
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

    @router.post("/cases", status_code=201)
    def create_case(body: CaseProposal):
        try:
            return service().propose(body, actor=actor())
        except CaseConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except CaseNotFound as exc:
            raise HTTPException(404, str(exc)) from exc

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

    @router.post("/cases/{case_id}/review")
    def decide_case(case_id: UUID, body: ReviewDecision, if_match: str | None = Header(None)):
        if if_match is None:
            raise HTTPException(428, "If-Match revision is required")
        if not re.fullmatch(r'"(0|[1-9][0-9]*)"', if_match):
            raise HTTPException(400, 'If-Match must be a quoted non-negative revision')
        expected = int(if_match[1:-1])
        try:
            return service().decide(str(case_id), expected, body,
                                    actor=actor(for_decision=True))
        except CaseNotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except StaleCase as exc:
            raise HTTPException(412, str(exc)) from exc
        except CaseConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    app.include_router(router)
