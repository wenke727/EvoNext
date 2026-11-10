"""Local owner-bound proposals and review receipts; publication is explicit CAS."""
import difflib

from evonext.contracts.trajectory import ContractError, encode_json, load_json, sha256
from evonext.skills.workshop.authoring import lint, validate_files
from evonext.skills.workshop.library import _atomic, _HASH


class Drafts:
    def __init__(self, library):
        self.library = library

    def _path(self, draft_id):
        if not isinstance(draft_id, str) or not _HASH.fullmatch(draft_id):
            raise ContractError("Invalid draft identity")
        path = self.library.root / ".drafts"
        if path.is_symlink():
            raise ContractError("Symlinked draft storage is not allowed")
        path.mkdir(exist_ok=True)
        path = path / (draft_id + ".json")
        if path.is_symlink():
            raise ContractError("Symlinked draft storage is not allowed")
        return path

    def create(self, *, skill_id, base_revision, files, sources, reason, mode="manual",
               provenance=None):
        validate_files(skill_id, files)
        if mode not in {"manual", "learn", "diet"} or not reason.strip():
            raise ContractError("Draft needs an authoring mode and reason")
        if not sources or any(not _HASH.fullmatch(s) for s in sources):
            raise ContractError("Draft needs pinned source snapshots")
        with self.library.lock:
            head = self.library.current(skill_id)
            original = self.library.files(skill_id, base_revision) if base_revision else {}
            if base_revision:
                previous, _ = self.library.read(skill_id, base_revision)
                sources = sorted(set(sources) | set(previous["source_snapshots"]))
            proposal = {"skill_id": skill_id, "owner": self.library.owner, "base_revision": base_revision,
                        "files": files, "sources": sorted(set(sources)), "reason": reason, "mode": mode,
                        "provenance": provenance or {}}
            draft_id = sha256(encode_json(proposal))
            path = self._path(draft_id)
            if path.exists():
                return self.get(draft_id)
            if (head["revision"] if head else None) != base_revision:
                raise ContractError("Skill changed before draft creation")
            old_warnings = lint(original) if original else []
            record = {"draft_id": draft_id, "proposal": proposal, "state": "pending",
                      "review": None, "commit": None,
                      "warnings": [w for w in lint(files) if w not in old_warnings],
                      "diff": "".join("".join(difflib.unified_diff(original.get(p, "").splitlines(True),
                           files.get(p, "").splitlines(True), "before/" + p, "after/" + p))
                           for p in sorted(original.keys() | files.keys()))}
            _atomic(path, encode_json(record))
            return record

    def get(self, draft_id):
        with self.library.lock:
            path = self._path(draft_id)
            if not path.exists():
                raise ContractError("Draft not found")
            record = load_json(path.read_bytes())
            if (record["draft_id"] != draft_id
                    or sha256(encode_json(record["proposal"])) != draft_id
                    or record["proposal"]["owner"] != self.library.owner):
                raise ContractError("Draft identity mismatch")
            return record

    def list(self):
        with self.library.lock:
            directory = self._path("0" * 64).parent
            return [self.get(p.stem) for p in sorted(directory.glob("*.json"))]

    def review(self, draft_id, *, verdict, notes, actor, kind="human", policy_hash=None,
               evidence_refs=()):
        if verdict not in {"approved", "needs_evidence", "rejected"} or not notes.strip() or not actor:
            raise ContractError("Review requires a verdict, rationale and actor")
        if kind not in {"human", "model"}:
            raise ContractError("Invalid review kind")
        review = {"draft_id": draft_id, "verdict": verdict, "notes": notes,
                  "actor": actor, "kind": kind, "policy_hash": policy_hash,
                  "evidence_refs": list(evidence_refs)}
        with self.library.lock:
            record = self.get(draft_id)
            if record["state"] != "pending":
                if record["review"] == review:
                    return record
                raise ContractError("Draft is already reviewed or closed; create a revised proposal")
            record.update(review=review, state=verdict)
            _atomic(self._path(draft_id), encode_json(record))
            return record

    def discard(self, draft_id):
        with self.library.lock:
            record = self.get(draft_id)
            if record["commit"]:
                raise ContractError("Committed draft requires revision restore, not discard")
            record["state"] = "discarded"
            _atomic(self._path(draft_id), encode_json(record))
            return record

    def commit(self, draft_id, actor):
        with self.library.lock:
            record = self.get(draft_id)
            if record["commit"]:
                return record
            if record["state"] != "approved" or record["review"]["draft_id"] != draft_id:
                raise ContractError("Only the exact approved draft may be committed")
            proposal = record["proposal"]
            validate_files(proposal["skill_id"], proposal["files"])
            # Reconcile a crash after HEAD changed but before the draft receipt was saved.
            reason = f"draft:{draft_id} {proposal['reason']}"
            result = None
            for revision in self.library.history(proposal["skill_id"]):
                if revision["reason"] == reason and revision["parent"] == proposal["base_revision"]:
                    if (self.library.files(proposal["skill_id"], revision["revision"]) != proposal["files"]
                            or revision["source_snapshots"] != proposal["sources"]
                            or revision["archived"]):
                        raise ContractError("Draft commit recovery found conflicting content")
                    result = {"revision": revision["revision"], "changed": True,
                              "archived": revision["archived"]}
                    break
            if result is None:
                result = self.library.save(proposal["skill_id"], proposal["files"]["SKILL.md"],
                    assets={p: c for p, c in proposal["files"].items() if p != "SKILL.md"},
                    expected_revision=proposal["base_revision"], source_snapshots=proposal["sources"],
                    reason=reason, actor=actor)
            record.update(state="committed", commit=result)
            _atomic(self._path(draft_id), encode_json(record))
            return record
