"""Case/Review use-case boundary; Evidence remains the only source of facts."""
from .contracts import (CaseNotFound, CaseProposal, ReviewDecision, verify_proposal)
from .corrections import DraftCommand, FrozenReviewCommand, verify_draft
from .previews import preview_case_use


class CaseService:
    def __init__(self, evidence_service, store):
        self.evidence = evidence_service
        self.store = store

    def propose(self, proposal: CaseProposal, *, actor: str):
        source = self.evidence.get(proposal.snapshot_id)
        payload = verify_proposal(proposal, source)
        return self.store.create(payload, actor=actor)

    def get(self, case_id: str):
        return self.store.get(case_id)

    def for_snapshot(self, snapshot_id: str, limit=50):
        if self.evidence.get_header(snapshot_id) is None:
            raise CaseNotFound("Frozen snapshot not found")
        return self.store.for_snapshot(snapshot_id, limit)

    def queue(self, status=None, after="", limit=50):
        return self.store.list_queue(status=status, after=after, limit=limit)

    def draft(self, case_id):
        return self.store.get_draft(case_id)

    def save_draft(self, case_id: str, command: DraftCommand, *, actor: str):
        case = self.get(case_id)
        snapshot = self.evidence.get(case["snapshot_id"])
        if snapshot is None:
            raise CaseNotFound("Source snapshot not found")
        verify_draft(command.draft, snapshot, self.evidence.assets)
        return self.store.save_draft(case_id, command.expected_draft_revision,
            command.draft.model_dump(mode="json"),
            command_id=command.command_id, actor=actor)

    def decide(self, case_id: str, expected: int, decision: ReviewDecision, *, actor: str):
        return self.store.decide(case_id, expected,
                                 decision.decision, decision.reason, actor=actor)

    def decide_frozen(self, case_id: str, command: FrozenReviewCommand, *, actor: str):
        return self.store.decide_frozen(
            case_id, command.expected_review_revision, command.draft_revision,
            command.draft_hash, command.decision, command.reason,
            command_id=command.command_id, actor=actor)

    def review(self, case_id: str, revision: int):
        return self.store.get_review(case_id, revision)

    def preview(self, case_id: str, revision: int, purpose: str):
        case = self.get(case_id)
        reviewed = self.review(case_id, revision)
        snapshot = self.evidence.get(case["snapshot_id"])
        if snapshot is None:
            raise CaseNotFound("Frozen source snapshot not found")
        return preview_case_use(case, reviewed, snapshot, purpose)
