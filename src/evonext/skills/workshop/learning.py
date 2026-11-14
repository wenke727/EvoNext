"""Bounded retrieval over registered workspace evidence; no source writes or model calls."""
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evonext.contracts.trajectory import ContractError, encode_json, sha256
from .service import AuthorRequest, SourceWindow, keys, preview, status, submit


class LearningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation_id: str = Field(min_length=1, max_length=100)
    topic: str = Field(default="", max_length=1000)
    seed_snapshot_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    skill_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]{0,63}$")
    source_limit: int = Field(default=4, ge=1, le=8)

    @model_validator(mode="after")
    def has_query(self):
        if not self.topic.strip() and not self.seed_snapshot_id:
            raise ValueError("Supply a topic or a registered seed snapshot")
        return self


def terms(text):
    text = text.casefold()
    words = set(re.findall(r"[a-z0-9][a-z0-9_-]+", text))
    for part in re.findall(r"[\u3400-\u9fff]+", text):
        words.update(part[i:i + 2] for i in range(len(part) - 1))
    return words


def relevance(query, value):
    a, b = terms(query), terms(value)
    return len(a & b) / max(1, len(a))


def step_text(step):
    """A derived search index, not an observation or replacement for the source."""
    value = step.get("value", {})
    raw = value.get("raw_model_output", "") if isinstance(value, dict) else ""
    actions = re.findall(r"<action>(.*?)</action>", str(raw), re.S)
    if actions:
        return " ".join(actions)
    facts = {k: step[k] for k in ("action", "tool_call", "dispatch", "observation") if k in step}
    if isinstance(value, dict):
        facts["value"] = {k: v for k, v in value.items() if k not in
                          {"think", "thought", "raw_model_output", "evaluation", "human_gold"}}
    return encode_json(facts).decode()


def eligible(snapshot):
    meta = snapshot.metadata
    if str(meta.get("split", "")).casefold() in {"test", "holdout", "heldout", "confirmation"}:
        return "held_out_source"
    if meta.get("revoked") is True or meta.get("restricted") is True:
        return "source_restricted"
    if not snapshot.document["traj"]:
        return "empty_trajectory"
    return None


def source_label(snapshot):
    evaluation = snapshot.document.get("evaluation")
    prediction = evaluation.get("prediction", {}) if isinstance(evaluation, dict) else {}
    if not isinstance(prediction, dict):
        return "unknown"
    label = prediction.get("task_status")
    if not isinstance(label, str):
        return "unknown"
    return "success" if label in {"perfect", "success", "passed"} else "failure" if label in {
        "failed", "failure"} else "unknown"


def lineage(snapshot):
    meta, doc = snapshot.metadata, snapshot.document
    source_meta = doc.get("metadata")
    parent = source_meta.get("reroll_of_task_id") if isinstance(source_meta, dict) else None
    # Source revisions and repeated imports of one Task are one support unit.
    return str(meta.get("family_id") or parent or doc["task_id"])


def select_window(snapshot, topic):
    steps = snapshot.document["traj"]
    action_terms = [terms(step_text(s)) for s in steps]
    query_terms = terms(topic)
    weights = {term: 1.0 for term in query_terms}
    # A multi-character Chinese name is one query chunk, not several votes.
    for chunk in re.findall(r"[\u3400-\u9fff]+", topic):
        chunks = terms(chunk)
        for term in chunks:
            weights[term] = min(weights[term], 1 / len(chunks))
    # Repeated account names must not swamp the less frequent operation words.
    frequencies = {term: sum(term in row for row in action_terms) for term in query_terms}
    scores = [sum(weights[term] / frequencies[term] for term in sorted(query_terms & row))
              for row in action_terms]
    width = min(12, len(steps))
    # Rank a contiguous span, not twelve disconnected "good" actions.
    sums = [sum(scores[max(0, i - 1):min(len(steps), i + 2)]) for i in range(len(steps))]
    anchor = max(range(len(steps)), key=lambda i: (sums[i], -abs(i - len(steps) // 2)))
    start = max(0, min(anchor - width // 2, len(steps) - width))
    positions = list(range(start, start + width))
    return SourceWindow(snapshot_id=snapshot.id, positions=positions, image_positions=[])


def plan(request, library, evidence, settings):
    topic = request.topic.strip()
    seed = evidence.get(request.seed_snapshot_id) if request.seed_snapshot_id else None
    if request.seed_snapshot_id and seed is None:
        raise ContractError("Seed snapshot is unavailable")
    if seed is not None:
        reason = eligible(seed)
        if reason:
            raise ContractError("Seed cannot be used for development: " + reason)
        topic = topic or seed.document["instruction"]
    # Explicit cap and cursor: no unbounded scan or implicit full-corpus claim.
    summaries = evidence.list(limit=201)
    scanned = summaries[:200]
    candidates, excluded = [], []
    for summary in scanned:
        sid = summary["snapshot_id"]
        header = evidence.get_header(sid)
        score = relevance(topic, header["instruction"])
        if score < .15 and sid != request.seed_snapshot_id:
            excluded.append({"snapshot_id": sid, "reason": "low_lexical_relevance"})
            continue
        snapshot = evidence.get(sid)
        if snapshot is None:
            raise ContractError("Retrieved snapshot disappeared")
        reason = eligible(snapshot)
        if reason:
            excluded.append({"snapshot_id": sid, "reason": reason})
            continue
        candidates.append((snapshot, 1.0 if sid == request.seed_snapshot_id else score))
    if seed is not None and not any(s.id == seed.id for s, _ in candidates):
        candidates.append((seed, 1.0))
    candidates.sort(key=lambda row: (-row[1], row[0].id))
    # Prefer a diverse label mix among relevant independent sources. Labels remain hints.
    selected, seen_tasks, families, labels = [], set(), {}, set()
    while candidates and len(selected) < request.source_limit:
        index = next((i for i, (s, _) in enumerate(candidates) if source_label(s) not in labels), 0)
        snapshot, score = candidates.pop(index)
        family = lineage(snapshot)
        label = source_label(snapshot)
        if snapshot.document["task_id"] in seen_tasks:
            excluded.append({"snapshot_id": snapshot.id, "reason": "same_task_revision"})
            continue
        if family in families and (label in families[family] or len(families[family]) >= 2):
            excluded.append({"snapshot_id": snapshot.id, "reason": "same_lineage_redundant"})
            continue
        seen_tasks.add(snapshot.document["task_id"])
        families.setdefault(family, set()).add(label)
        labels.add(label)
        selected.append((snapshot, score))
    if not selected:
        raise ContractError("No eligible related evidence in the registered workspace")
    skill_id, base, matches = request.skill_id, None, []
    for row in library.list():
        if row["archived"]:
            continue
        record, document = library.read(row["skill_id"], row["revision"])
        # Discovery only; the author must still check applicability against evidence.
        score = relevance(topic, row["skill_id"] + " " + document.split("---", 2)[1])
        if score >= .35:
            matches.append({"skill_id": row["skill_id"], "revision": row["revision"], "score": score})
    matches.sort(key=lambda r: (-r["score"], r["skill_id"]))
    if skill_id is None and matches:
        if len(matches) > 1 and abs(matches[0]["score"] - matches[1]["score"]) < .1:
            raise ContractError("Ambiguous related Skills; select an explicit skill_id from the inventory")
        skill_id = matches[0]["skill_id"]
    skill_id = skill_id or "learned-" + sha256(topic.encode())[:16]
    head = library.current(skill_id)
    if head:
        if head["archived"]:
            raise ContractError("Selected Skill is archived")
        base = head["revision"]
    windows = [select_window(s, topic) for s, _ in selected]
    report = {"topic": topic, "method": "lexical-overlap.v1; relevance is not applicability",
              "scope": "registered workspace snapshots only", "scanned": len(scanned),
              "scan_truncated": len(summaries) > 200,
              "next_cursor": scanned[-1]["snapshot_id"] if len(summaries) > 200 else None,
              "requested": request.source_limit, "selected_count": len(windows),
              "independent_family_count": len(families),
              "shortfall": max(0, request.source_limit - len(windows)), "excluded": excluded,
              "unselected_related_count": len(candidates), "skill_matches": matches,
              "sources": [{"snapshot_id": s.id, "task_id": s.document["task_id"],
                  "source_label_hint": source_label(s), "label_authority": "unverified_source",
                  "score": score, "step_count": len(s.document["traj"]),
                  "window": w.positions, "omitted_positions": [i for i in range(len(s.document["traj"]))
                                                               if i not in w.positions]}
                  for (s, score), w in zip(selected, windows)]}
    author = AuthorRequest(operation_id=request.operation_id, skill_id=skill_id, base_revision=base,
        sources=windows, evidence_mode="on_demand", instruction=(
            "Learn one reusable subprocedure for: " + topic +
            ". Inspect applicability of the existing Skill first; patch it if appropriate. "
            "Contrast source actions and observed results; source success/failure labels are hints, "
            "not independent proof. Do not infer omitted transitions or turn a proxy metric into the goal. "
            "Read necessary images from the inventory; no_change and needs_evidence are valid. "
            "Keep a short operational core (about 300-800 Chinese characters or 1000 tokens); "
            "put cases and uncommon branches in linked references without hiding pre-action checks."))
    view = preview(author, library, evidence, settings, retrieval=report)
    return {"author_request": author.model_dump(), "retrieval": report,
            "budget": {k: v for k, v in view.items() if k != "steps"}, "steps": view["steps"]}


def submit_learning(request, library, evidence, ledger, settings):
    previous = ledger.get(keys(request.operation_id))
    if previous:
        payload = previous["payload"]
        if payload.get("learning_request") != request.model_dump() or payload["owner"] != library.owner:
            raise ContractError("Operation ID already binds another learning request")
        return status(request.operation_id, ledger, library.owner)
    planned = plan(request, library, evidence, settings)
    author = AuthorRequest.model_validate(planned["author_request"])
    # Freeze discovery with the existing authoring receipt, not a second Run store.
    return submit(author, library, evidence, ledger, settings=settings,
                  learning={"learning_request": request.model_dump(), "retrieval": planned["retrieval"]})
