from evonext.contracts.trajectory import ContractError, Snapshot, sha256


def verify_snapshot(snapshot_id, repository, assets, ledger):
    snapshot = repository.get(snapshot_id)
    if snapshot is None:
        raise ContractError("Snapshot not found")
    checked = Snapshot.create(snapshot.trajectory_json, snapshot.metadata_json, snapshot.media)
    if checked.id != snapshot_id:
        raise ContractError("Snapshot integrity mismatch")
    for digest in snapshot.media.values():
        if sha256(assets.get(digest)) != digest:
            raise ContractError("Media integrity mismatch")
    operation_id = "integrity-v1-" + snapshot_id
    result = {"snapshot_integrity": "verified", "bound_media": len(snapshot.media),
              "unbound_media": sum(1 for step in snapshot.document["traj"]
                                   if step.get("image") and step["image"] not in snapshot.media),
              "agent_outcome": "not_assessed"}
    ledger.record(operation_id, snapshot_id, "storage_integrity.v1", result)
    return {"operation_id": operation_id, "result": result}
