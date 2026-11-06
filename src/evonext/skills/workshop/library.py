"""Small local candidate owner: immutable revisions, CAS, diff and reversible edits.

No model calls, tool execution, implicit activation, or independent grading.
One trusted operator owns this local directory. FileLock is not a distributed lock.
"""
import difflib
import os
from pathlib import Path
import re
import tempfile

from filelock import FileLock
import yaml

from evonext.contracts.skills import SkillBundle, SkillRef
from evonext.contracts.trajectory import ContractError, encode_json, load_json, sha256

_SLUG = re.compile(r"[a-z][a-z0-9-]{0,63}")
_HASH = re.compile(r"[0-9a-f]{64}")


class UniqueLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader, node, deep=False):
    value = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in value:
            raise ContractError("Skill metadata requires unique string keys")
        value[key] = loader.construct_object(value_node, deep=deep)
    return value


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def validate_document(skill_id, document):
    if not _SLUG.fullmatch(skill_id) or not isinstance(document, str):
        raise ContractError("Invalid skill identity")
    if len(document.encode("utf-8")) > 64 * 1024:
        raise ContractError("Skill exceeds the 64 KiB document limit")
    parts = document.split("---", 2)
    if len(parts) != 3 or parts[0].strip() or not parts[2].strip():
        raise ContractError("SKILL.md requires YAML frontmatter and a Markdown body")
    try:
        header = yaml.load(parts[1], Loader=UniqueLoader)
    except yaml.YAMLError as exc:
        raise ContractError("Invalid Skill frontmatter") from exc
    if not isinstance(header, dict) or header.get("name") != skill_id:
        raise ContractError("Skill frontmatter name must match its identity")
    if not isinstance(header.get("description"), str) or not header["description"].strip():
        raise ContractError("Skill description is required")
    return header


def _atomic(path, data):
    # Caller holds the library lock. Immutable files are never rewritten.
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Workshop:
    def __init__(self, root, owner):
        root = Path(root).expanduser()
        if not owner or len(owner) > 128 or root.is_symlink():
            raise ContractError("Workshop requires an owner and a non-symlink root")
        root.mkdir(parents=True, exist_ok=True)
        self.root, self.owner = root.resolve(), owner
        self.lock = FileLock(str(self.root / ".workshop.lock"), timeout=10)
        with self.lock:
            scope = self.root / "owner.json"
            if scope.exists():
                if scope.is_symlink() or load_json(scope.read_bytes()) != {"owner": owner}:
                    raise ContractError("Workshop belongs to a different owner")
            else:
                _atomic(scope, encode_json({"owner": owner}))

    def _path(self, skill_id, *parts):
        if not _SLUG.fullmatch(skill_id):
            raise ContractError("Invalid skill identity")
        path = self.root / skill_id
        for part in (None, *parts):
            if part is not None:
                path /= part
            if path.is_symlink():
                raise ContractError("Symlinked skill storage is not allowed")
        if not path.resolve().is_relative_to(self.root):
            raise ContractError("Skill path escapes its owner")
        return path

    def _head(self, skill_id):
        path = self._path(skill_id, "HEAD.json")
        if not path.exists():
            return None
        head = load_json(path.read_bytes())
        if not isinstance(head.get("revision"), str) or not _HASH.fullmatch(head["revision"]):
            raise ContractError("Invalid Skill head")
        return head

    def current(self, skill_id):
        with self.lock:
            head = self._head(skill_id)
            return dict(head) if head else None

    def _read(self, skill_id, revision):
        if not _HASH.fullmatch(revision):
            raise ContractError("Invalid skill revision")
        directory = self._path(skill_id, "revisions", revision)
        record = load_json(self._path(skill_id, "revisions", revision, "record.json").read_bytes())
        if sha256(encode_json(record)) != revision or record["owner"] != self.owner or record["skill_id"] != skill_id:
            raise ContractError("Skill revision identity mismatch")
        document = self._path(skill_id, "revisions", revision, "SKILL.md").read_bytes().decode("utf-8")
        if sha256(document.encode()) != record["content_hash"] or not directory.is_dir():
            raise ContractError("Skill content hash mismatch")
        validate_document(skill_id, document)
        return record, document

    def read(self, skill_id, revision=None):
        with self.lock:
            head = self._head(skill_id)
            if not head:
                raise ContractError("Skill does not exist")
            return self._read(skill_id, revision or head["revision"])

    def save(self, skill_id, document, *, expected_revision, source_snapshots, reason, actor,
             archived=False, restored_from=None):
        validate_document(skill_id, document)
        if not reason or not actor or not source_snapshots:
            raise ContractError("Candidate needs reason, actor and pinned source snapshot identities")
        if any(not isinstance(s, str) or not _HASH.fullmatch(s) for s in source_snapshots):
            raise ContractError("Invalid source snapshot identity")
        with self.lock:
            head = self._head(skill_id)
            parent = head["revision"] if head else None
            if parent != expected_revision:
                raise ContractError("Skill changed since it was read; refresh before saving")
            record = {"schema_version": "evonext.skill-revision.v1", "skill_id": skill_id,
                "owner": self.owner, "parent": parent, "content_hash": sha256(document.encode()),
                "source_snapshots": sorted(set(source_snapshots)), "reason": reason, "actor": actor,
                "archived": bool(archived), "restored_from": restored_from, "stage": "candidate"}
            if head:
                old, _ = self._read(skill_id, parent)
                if all(old[k] == record[k] for k in ("content_hash", "source_snapshots", "archived")):
                    return {**head, "changed": False}
            revision = sha256(encode_json(record))
            directory = self._path(skill_id, "revisions", revision)
            directory.mkdir(parents=True, exist_ok=True)
            for name, data in (("SKILL.md", document.encode()), ("record.json", encode_json(record))):
                target = self._path(skill_id, "revisions", revision, name)
                if target.exists():
                    if target.read_bytes() != data:
                        raise ContractError("Immutable Skill revision conflict")
                else:
                    _atomic(target, data)
            result = {"revision": revision, "archived": bool(archived)}
            _atomic(self._path(skill_id, "HEAD.json"), encode_json(result))
            return {**result, "changed": True}

    def restore(self, skill_id, revision, *, expected_revision, actor):
        record, document = self.read(skill_id, revision)
        return self.save(skill_id, document, expected_revision=expected_revision,
            source_snapshots=record["source_snapshots"], reason="restore saved revision", actor=actor,
            archived=False, restored_from=revision)

    def archive(self, skill_id, *, expected_revision, actor):
        record, document = self.read(skill_id)
        return self.save(skill_id, document, expected_revision=expected_revision,
            source_snapshots=record["source_snapshots"], reason="archive candidate", actor=actor, archived=True)

    def history(self, skill_id):
        with self.lock:
            head = self._head(skill_id)
            revision, result, seen = head["revision"] if head else None, [], set()
            while revision:
                if revision in seen:
                    raise ContractError("Skill history cycle")
                seen.add(revision)
                record, _ = self._read(skill_id, revision)
                result.append({"revision": revision, **record})
                revision = record["parent"]
            return result

    def export(self, skill_id, revision):
        with self.lock:
            head = self._head(skill_id)
            if not head or head["archived"]:
                raise ContractError("Archived or absent Skill cannot start a new trial")
            record, document = self._read(skill_id, revision)
            if record["archived"]:
                raise ContractError("Archived revision cannot be exported for use")
            return SkillBundle(ref=SkillRef(skill_id=skill_id, owner=self.owner, revision=revision,
                content_hash=record["content_hash"], source_snapshots=tuple(record["source_snapshots"])),
                document=document)

    def diff(self, skill_id, before, after):
        _, a = self.read(skill_id, before)
        _, b = self.read(skill_id, after)
        return "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), before, after))
