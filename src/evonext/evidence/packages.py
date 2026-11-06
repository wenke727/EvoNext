"""Portable OpenCUA bundles. Never fetch URLs or execute recorded actions."""
import io
import stat
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from evonext.contracts.trajectory import ContractError, Snapshot, load_json, sha256


def safe_path(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and "\\" not in name and ":" not in name and "\x00" not in name and str(path) == name


def media_type(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    raise ContractError("Only JPEG, PNG and WebP assets are served")


def import_bundle(raw: bytes, assets, settings) -> Snapshot:
    if len(raw) > settings.max_upload_bytes:
        raise ContractError("Archive exceeds upload limit")
    files = {}
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > settings.max_steps + 100:
                raise ContractError("Too many archive entries")
            total = 0
            for entry in entries:
                if entry.is_dir():
                    continue
                name = entry.filename
                if not safe_path(name) or stat.S_ISLNK(entry.external_attr >> 16):
                    raise ContractError("Unsafe archive path or symlink")
                if name in files:
                    raise ContractError("Duplicate archive path")
                if name not in {"trajectory.json", "metadata.json"} and not name.startswith("images/"):
                    raise ContractError("Unrecognized bundle member; no silent dropping")
                if entry.file_size > settings.max_file_bytes:
                    raise ContractError("Archive member exceeds size limit")
                total += entry.file_size
                if total > settings.max_upload_bytes:
                    raise ContractError("Expanded archive exceeds size limit")
                with archive.open(entry) as stream:
                    content = stream.read(settings.max_file_bytes + 1)
                if len(content) > settings.max_file_bytes:
                    raise ContractError("Expanded member exceeds size limit")
                files[name] = content
    except (BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise ContractError("Unreadable ZIP archive") from exc
    if not {"trajectory.json", "metadata.json"}.issubset(files):
        raise ContractError("Bundle requires trajectory.json and metadata.json")
    snapshot = Snapshot.create(files["trajectory.json"], files["metadata.json"],
                               max_steps=settings.max_steps)
    for step in snapshot.document["traj"]:
        image = step.get("image")
        if image is not None and (not safe_path(image) or image not in files):
            raise ContractError("Portable bundle has an unresolved screenshot")
    hashes = load_json(files["metadata.json"]).get("image_hashes", {})
    if not isinstance(hashes, dict):
        raise ContractError("image_hashes must be an object")
    media = {}
    for name, data in files.items():
        if name.startswith("images/"):
            media_type(data)
            digest = sha256(data)
            expected = hashes.get(name)
            if expected is not None and (not isinstance(expected, str) or expected not in {digest, "sha256:" + digest}):
                raise ContractError("Declared image hash mismatch")
            media[name] = digest
    if set(hashes) - set(media):
        raise ContractError("Declared image hash references an absent file")
    # Validate the complete bundle before any storage write. Object uploads precede the atomic
    # snapshot insert. A failed import may leave unreferenced blobs, never a false complete snapshot.
    for name in media:
        assets.put(files[name])
    return Snapshot.create(files["trajectory.json"], files["metadata.json"], media,
                           max_steps=settings.max_steps)


def export_bundle(snapshot: Snapshot, assets, max_bytes: int) -> bytes:
    out = io.BytesIO()
    total = len(snapshot.trajectory_json) + len(snapshot.metadata_json)
    if total > max_bytes:
        raise ContractError("Export exceeds size limit")
    for step in snapshot.document["traj"]:
        image = step.get("image")
        if image is not None and image not in snapshot.media:
            raise ContractError("Cannot export a portable bundle with unresolved media")
    with ZipFile(out, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("trajectory.json", snapshot.trajectory_json)
        archive.writestr("metadata.json", snapshot.metadata_json)
        for name, digest in sorted(snapshot.media.items()):
            if not safe_path(name) or not name.startswith("images/"):
                raise ContractError("Unsafe stored media binding")
            data = assets.get(digest)
            total += len(data)
            if total > max_bytes:
                raise ContractError("Export exceeds size limit")
            archive.writestr(name, data)
    return out.getvalue()
