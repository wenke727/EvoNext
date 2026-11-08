import json
import sys
from time import time

import pytest

from evonext.app.cli import main
from evonext.runtime.resources import (
    CloudBatchPool, Inventory, LocalDevicePool, ResourceRequirements, get_resource_pool,
)


def device(alias, **changes):
    return dict({"resource_id": alias, "unit": "device", "drivers": ["external_agent"],
                 "state": "available", "available_slots": 1}, **changes)


def observation(kind, *rows, start=100):
    return Inventory.model_validate_json(json.dumps({
        "kind": kind, "observed_at_epoch": start, "expires_at_epoch": start + 60,
        "resources": rows,
    }))


def test_local_availability_uses_latest_observation_and_shared_device_identity():
    dual = device("synthetic-a", drivers=["external_agent", "builtin_agent"],
                  capabilities=["maintained_account"])
    other = device("synthetic-b")
    snapshot = observation("local_device", dual, other)
    pool = get_resource_pool("local_device", lambda: snapshot)
    assert isinstance(pool, LocalDevicePool)
    all_devices = ResourceRequirements()
    assert len(pool.list_available(all_devices, now=100).resources) == 2
    assistant = ResourceRequirements(driver="builtin_agent", capabilities=frozenset(["maintained_account"]))
    assert [r.resource_id for r in pool.list_available(assistant, now=100).resources] == ["synthetic-a"]
    snapshot = observation("local_device", dict(dual, state="busy", available_slots=0), other)
    assert pool.list_available(assistant, now=101).resources == ()
    assert [r.resource_id for r in pool.list_available(all_devices, now=101).resources] == ["synthetic-b"]
    for now in (99, 160):
        with pytest.raises(ValueError, match="validity"):
            pool.list_available(all_devices, now=now)


def test_cloud_queue_only_and_capacity_are_distinct():
    unknown = device("synthetic-queue", unit="pool", drivers=["cloud_query"],
                     state="unknown", available_slots=None, accepts_queue=True)
    ready = dict(unknown, resource_id="synthetic-ready", state="available", available_slots=8)
    snapshot = observation("cloud_batch", unknown, ready)
    pool = get_resource_pool("cloud_batch", lambda: snapshot)
    assert isinstance(pool, CloudBatchPool)
    assert pool.inventory().resources[0].accepts_queue
    assert [r.available_slots for r in pool.list_available(ResourceRequirements(), now=100).resources] == [8]


def test_invalid_inventories_fail_closed():
    row = device("synthetic-a")
    with pytest.raises(ValueError, match="Duplicate"):
        observation("local_device", row, row)
    with pytest.raises(ValueError, match="at most one"):
        observation("local_device", dict(row, available_slots=2))
    cloud = observation("cloud_batch", row, device("synthetic-pool", unit="pool"))
    with pytest.raises(ValueError, match="granularity"):
        get_resource_pool("cloud_batch", lambda: cloud).inventory()
    with pytest.raises(ValueError, match="another resource pool"):
        get_resource_pool("local_device", lambda: cloud).inventory()


def test_cli_filters_inventory(tmp_path, monkeypatch, capsys):
    path = tmp_path / "synthetic-inventory.json"
    inventory = observation("local_device", device("synthetic-a"), device("synthetic-b"),
                            start=int(time()))
    path.write_text(inventory.model_dump_json())
    monkeypatch.setattr(sys, "argv", ["evonext", "list-available", "--inventory", str(path),
                                     "--driver", "external_agent", "--resource-id", "synthetic-b"])
    main()
    result = json.loads(capsys.readouterr().out)
    assert [row["resource_id"] for row in result["resources"]] == ["synthetic-b"]
