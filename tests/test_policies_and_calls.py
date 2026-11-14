import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from evonext.config import Settings
from evonext.contracts.trajectory import ContractError
from evonext.providers.gateway import ModelGateway
from evonext.providers.policies import freeze_policy
from evonext.providers.receipts import BudgetExceeded, CallHeld, MemoryCallReceipts

ROOT = Path(__file__).resolve().parents[1]


def options(**overrides):
    return Settings(_env_file=None, demo=True, model_calls_enabled=True,
        model_name="synthetic", model_base_url="https://model.example.invalid/v1",
        model_api_key=SecretStr("synthetic"), **overrides)


def gateway(handler, **overrides):
    return ModelGateway(options(**overrides), transport=httpx.MockTransport(handler),
                        receipts=MemoryCallReceipts())


def test_policy_is_frozen_and_missing_variable_fails():
    with pytest.raises(ContractError):
        freeze_policy(ROOT / "policies/gui", "outcome", {})
    a = freeze_policy(ROOT / "policies/gui", "outcome", {"obligations": "a", "evidence": "b"})
    b = freeze_policy(ROOT / "policies/gui", "outcome", {"obligations": "c", "evidence": "b"})
    assert a.version == b.version and a.prompt != b.prompt
    config = a.config
    config["max_tokens"] = 9
    assert a.config["max_tokens"] == 1024


def test_policy_dependency_changes_version(tmp_path):
    for p in (ROOT / "policies/gui").iterdir():
        (tmp_path / p.name).write_bytes(p.read_bytes())
    a = freeze_policy(tmp_path, "outcome", {"obligations": "a", "evidence": "b"})
    (tmp_path / "shared.md").write_text("Changed shared rule")
    b = freeze_policy(tmp_path, "outcome", {"obligations": "a", "evidence": "b"})
    assert a.version != b.version
    assert "Changed shared rule" not in a.prompt


@pytest.mark.parametrize("template", ["{% include 'outcome.md' %}", "{% include '../outside.md' %}",
                                      "{% include other %}"])
def test_policy_invalid_include_is_rejected(tmp_path, template):
    (tmp_path / "outcome.md").write_text(template)
    (tmp_path / "outcome.json").write_bytes((ROOT / "policies/gui/outcome.json").read_bytes())
    with pytest.raises(ContractError):
        freeze_policy(tmp_path, "outcome", {})


def test_disabled_calls_do_not_send_or_reserve():
    calls = []
    settings = options()
    settings.model_calls_enabled = False
    store = MemoryCallReceipts()
    model = ModelGateway(settings, httpx.MockTransport(lambda r: calls.append(r)), receipts=store)
    with pytest.raises(PermissionError):
        model.complete([], operation_id="op")
    assert not calls and not store.rows
    model.close()


def test_gateway_configuration_frozen_after_creation():
    settings = options()
    model = ModelGateway(settings, httpx.MockTransport(lambda _: httpx.Response(200, json={})),
                         receipts=MemoryCallReceipts())
    settings.model_name = "changed"
    assert model.complete([], operation_id="op")["declared_model"] == "synthetic"
    model.close()


def test_received_response_reused_and_repeats_distinct():
    calls = []
    model = gateway(lambda r: calls.append(r) or httpx.Response(200, json={"model": "v1"}))
    a = model.complete([], operation_id="op")
    b = model.complete([], operation_id="op")
    c = model.complete([], operation_id="op", repetition_id="1")
    assert not a["reused"] and b["reused"] and not c["reused"]
    assert a["call_key"] == b["call_key"] != c["call_key"]
    assert len(calls) == 2
    model.close()


def test_generation_options_are_explicit_bounded_and_part_of_receipt_identity():
    calls = []
    model = gateway(lambda r: calls.append(json.loads(r.content)) or httpx.Response(200, json={}))
    with pytest.raises(ContractError):
        model.complete([], operation_id="large", max_tokens=16384)
    assert not calls and not model.receipts.rows
    model.close()
    model = gateway(lambda r: calls.append(json.loads(r.content)) or httpx.Response(200, json={}),
                    model_max_output_tokens=16384)
    a = model.complete([], operation_id="same")
    b = model.complete([], operation_id="same", max_tokens=16384, temperature=1, reasoning_effort="high")
    assert a["call_key"] != b["call_key"]
    assert "temperature" not in calls[0] and "reasoning_effort" not in calls[0]
    assert calls[1]["max_tokens"] == 16384 and calls[1]["reasoning_effort"] == "high"
    with pytest.raises(ContractError):
        model.complete([], operation_id="invalid", temperature=float("nan"))
    model.close()

def test_unknown_response_never_automatically_resent():
    calls = []
    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout("synthetic", request=request)
    model = gateway(timeout)
    with pytest.raises(httpx.ReadTimeout):
        model.complete([], operation_id="op")
    with pytest.raises(CallHeld):
        model.complete([], operation_id="op")
    assert len(calls) == 1
    model.close()


@pytest.mark.parametrize("response", [httpx.Response(200, text="invalid-json"), httpx.Response(503)])
def test_unusable_received_response_is_not_rebilled(response):
    calls = []
    model = gateway(lambda r: calls.append(r) or response)
    for _ in range(2):
        with pytest.raises((ContractError, httpx.HTTPStatusError)):
            model.complete([], operation_id="op")
    assert len(calls) == 1
    assert next(iter(model.receipts.rows.values()))["status"] == "received"
    model.close()


def test_budget_counts_failed_attempts_and_allows_free_replay():
    calls = []
    model = gateway(lambda r: calls.append(r) or httpx.Response(200, json={}), model_calls_per_minute=1)
    model.complete([], operation_id="a")
    assert model.complete([], operation_id="a")["reused"]
    with pytest.raises(BudgetExceeded):
        model.complete([], operation_id="b")
    assert len(calls) == 1
    model.close()


def test_no_process_local_production_receipt_fallback():
    model = ModelGateway(options(), httpx.MockTransport(lambda _: pytest.fail("no network")))
    with pytest.raises(ContractError, match="PostgreSQL"):
        model.complete([], operation_id="op")
    model.close()


def test_budget_reservation_atomic_under_concurrency():
    store = MemoryCallReceipts()
    def reserve(i):
        try:
            store.begin(str(i), "scope", {60: 3})
            return True
        except BudgetExceeded:
            return False
    with ThreadPoolExecutor(10) as pool:
        assert sum(pool.map(reserve, range(30))) == 3


def test_stable_identity_binds_policy_input_and_scope():
    calls = []
    model = gateway(lambda r: calls.append(r) or httpx.Response(200, json={}))
    a = model.complete([], operation_id="op", policy_version="a")
    b = model.complete([], operation_id="op", policy_version="b")
    c = model.complete([{"role": "user", "content": "different"}], operation_id="op", policy_version="b")
    assert len({a["call_key"], b["call_key"], c["call_key"]}) == 3
    assert len(calls) == 3
    model.close()


def test_policy_route_mismatch_blocks_network():
    model = gateway(lambda _: pytest.fail("no network"))
    policy = freeze_policy(ROOT / "policies/gui", "outcome", {"obligations": "a", "evidence": "b"})
    with pytest.raises(ContractError, match="profile"):
        model.complete_policy(policy, snapshot_id="a", operation_id="op")
    model.close()


def test_policy_config_does_not_accept_secrets(tmp_path):
    config = json.loads((ROOT / "policies/gui/outcome.json").read_text())
    config["api_key"] = "not-permitted"
    (tmp_path / "outcome.json").write_text(json.dumps(config))
    with pytest.raises(ContractError):
        freeze_policy(tmp_path, "outcome", {})


@pytest.mark.parametrize("name, token_key", [("gpt-6.1-sol", "max_completion_tokens"),
    ("gpt-6.1-sol-2026-11-14", "max_completion_tokens"), ("synthetic", "max_tokens")])
def test_model_specific_output_budget_is_part_of_durable_request(name, token_key):
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    settings = options().model_copy(update={"model_name": name})
    store = MemoryCallReceipts()
    model = ModelGateway(settings, transport=httpx.MockTransport(handler), receipts=store)
    try:
        first = model.complete([], operation_id="synthetic-token-profile", max_tokens=1024)
        assert seen[0][token_key] == 1024
        assert ("max_tokens" if token_key == "max_completion_tokens" else "max_completion_tokens") not in seen[0]
        assert model.complete([], operation_id="synthetic-token-profile", max_tokens=1024)["reused"]
        assert len(seen) == 1 and first["call_key"] in store.rows
    finally:
        model.close()
