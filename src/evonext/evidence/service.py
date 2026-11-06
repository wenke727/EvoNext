"""One evidence use-case owner for HTTP, CLI and later automation clients."""
from evonext.contracts.trajectory import ContractError, Snapshot, encode_json, load_json
from .packages import export_bundle, import_bundle


class EvidenceService:
    def __init__(self, repository, assets, settings):
        self.repository, self.assets, self.settings = repository, assets, settings

    def accept(self, snapshot):
        self.repository.put(snapshot)
        return snapshot

    def import_json(self, raw):
        if len(raw) > self.settings.max_file_bytes:
            raise ContractError("JSON exceeds configured input limit")
        value = load_json(raw)
        if set(value) - {"trajectory", "metadata"} or "trajectory" not in value:
            raise ContractError("Use an envelope with trajectory and optional metadata")
        snapshot = Snapshot.create(encode_json(value["trajectory"]),
            encode_json(value.get("metadata", {})), max_steps=self.settings.max_steps)
        return self.accept(snapshot)

    def import_zip(self, raw):
        return self.accept(import_bundle(raw, self.assets, self.settings))

    def get(self, identity):
        return self.repository.get(identity)

    def list(self, after="", limit=50):
        return self.repository.list(after, limit)

    def export(self, snapshot):
        return export_bundle(snapshot, self.assets, self.settings.max_upload_bytes)
