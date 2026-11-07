"""Narrow application boundary for a reviewed issue on immutable evidence."""
from .contracts import (CaseNotFound, CaseProposal, ReviewDecision, verify_proposal)


class CaseService:
    def __init__(self, evidence_service, store):
        self.evidence = evidence_service
        self.store = store

    def propose(self, proposal: CaseProposal, *, actor: str):
        # Full source verification on writes is intentional. Browsing uses bounded reads.
        source = self.evidence.get(proposal.snapshot_id)
        payload = verify_proposal(proposal, source)
        return self.store.create(payload, actor=actor)

    def get(self, case_id: str):
        return self.store.get(case_id)

    def for_snapshot(self, snapshot_id: str, limit=50):
        # Only report anchored issues for an existing immutable source.
        if self.evidence.get_header(snapshot_id) is None:
            raise CaseNotFound("Frozen snapshot not found")
        return self.store.for_snapshot(snapshot_id, limit)

    def decide(self, case_id: str, expected: int, decision: ReviewDecision, *, actor: str):
        return self.store.decide(case_id, expected, decision.decision, decision.reason, actor=actor)
