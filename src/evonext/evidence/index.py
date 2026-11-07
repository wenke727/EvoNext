"""Small, rebuildable snapshot wrapper. It is never exported as source evidence."""
import copy
from dataclasses import dataclass, field

from evonext.contracts.trajectory import Snapshot, encode_json, sha256


class StoredEvidenceError(RuntimeError):
    """Stored evidence or its projection is inconsistent; never substitute another version."""


class EvidenceNotFound(LookupError):
    pass


@dataclass(frozen=True)
class SnapshotIndex:
    snapshot_id: str
    _manifest: dict = field(repr=False)
    _header: dict = field(repr=False)
    raw_json_verified: bool = False

    @classmethod
    def from_snapshot(cls, snapshot: Snapshot):
        document, media = snapshot.document, snapshot.media
        header = {**snapshot.summary(), "instruction": document["instruction"],
                  "missing_media": sorted({step["image"] for step in document["traj"]
                      if step.get("image") and step["image"] not in media})}
        return cls(snapshot.id, snapshot.manifest, header, raw_json_verified=True)

    @classmethod
    def from_stored(cls, snapshot_id, value):
        try:
            if value["profile"] != "evonext.snapshot-index.v1":
                raise ValueError("Unsupported index profile")
            manifest, header = value["manifest"], value["header"]
            if manifest["profile"] != "evonext.snapshot-bytes.v1":
                raise ValueError("Unsupported manifest profile")
            digests = [manifest["trajectory_sha256"], manifest["metadata_sha256"],
                       *manifest["media"].values()]
            if not all(isinstance(d, str) and len(d) == 64
                       and all(c in "0123456789abcdef" for c in d) for d in digests):
                raise ValueError("Invalid digest")
            if sha256(encode_json(manifest)) != snapshot_id or header["snapshot_id"] != snapshot_id:
                raise ValueError("Index identity mismatch")
            if not isinstance(header["task_id"], str) or not isinstance(header["instruction"], str):
                raise ValueError("Invalid header")
            if (type(header["step_count"]) is not int or header["step_count"] < 0
                    or type(header["media_count"]) is not int
                    or header["media_count"] != len(manifest["media"])
                    or (header["source_version"] is not None
                        and type(header["source_version"]) is not int)
                    or not isinstance(header["missing_media"], list)
                    or not all(isinstance(path, str) and path not in manifest["media"]
                               for path in header["missing_media"])):
                raise ValueError("Invalid header")
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            raise StoredEvidenceError("Stored snapshot index integrity mismatch") from exc
        return cls(snapshot_id, copy.deepcopy(manifest), copy.deepcopy(header))

    @property
    def manifest(self):
        return copy.deepcopy(self._manifest)

    @property
    def header(self):
        return copy.deepcopy(self._header)

    def stored(self):
        return {"profile": "evonext.snapshot-index.v1",
                "manifest": self.manifest, "header": self.header}
