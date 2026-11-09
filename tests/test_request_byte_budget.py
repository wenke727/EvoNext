import httpx
import pytest
from pydantic import ValidationError

from evonext.config import Settings
from evonext.contracts.trajectory import ContractError, Snapshot, encode_json
from evonext.evaluation.core import evaluate
from evonext.evaluation.inputs import InputOptions
from evonext.evaluation.replay import ReplayGateway
from evonext.evaluation.service import EvalRequest
from evonext.providers.gateway import ModelGateway
from evonext.providers.receipts import MemoryCallReceipts


def test_default_byte_limits_and_upper_bound_are_preserved():
    assert Settings(demo=True).model_max_request_bytes == 1024 * 1024
    assert EvalRequest(operation_id="synthetic").max_request_bytes == 950 * 1024
    with pytest.raises(ValidationError):
        EvalRequest(operation_id="synthetic", max_request_bytes=17 * 1024 * 1024)
    with pytest.raises(ValidationError):
        Settings(demo=True, model_max_request_bytes=17 * 1024 * 1024)


def test_gateway_large_request_requires_explicit_byte_budget():
    received = []
    settings = Settings(demo=True, model_name="synthetic", model_api_key="synthetic",
                        model_base_url="https://synthetic.invalid/v1", model_calls_enabled=True)
    messages = [{"role": "user", "content": "x" * (1100 * 1024)}]
    ledger = MemoryCallReceipts()

    def handler(request):
        received.append(len(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    gateway = ModelGateway(settings, transport=httpx.MockTransport(handler), receipts=ledger)
    with pytest.raises(ContractError, match="byte budget"):
        gateway.complete(messages, operation_id="synthetic-default")
    assert received == []
    assert ledger.rows == {}
    gateway.close()
    settings.model_max_request_bytes = 2 * 1024 * 1024
    gateway = ModelGateway(settings, transport=httpx.MockTransport(handler),
                           receipts=MemoryCallReceipts())
    gateway.complete(messages, operation_id="synthetic-wider")
    assert received[0] > 1024 * 1024
    gateway.close()


def test_core_large_text_request_uses_the_frozen_explicit_budget():
    snapshot = Snapshot.create(encode_json({
        "task_id": "synthetic-large-text", "instruction": "x" * 600000, "traj": [],
    }))
    raw = snapshot.trajectory_json
    options = InputOptions(max_text_bytes=1024 * 1024)
    request = EvalRequest(operation_id="synthetic-large", options=options, investigation="off")
    gateway = ReplayGateway([{"checks": [{
        "check_id": "task_goal", "judgment": "unknown", "evidence_refs": [], "reason": "Synthetic",
    }], "findings": []}])
    with pytest.raises(ContractError, match="gateway budget"):
        evaluate(snapshot, request, None, gateway, "Synthetic policy", "synthetic")
    assert gateway.count == 0
    request.max_request_bytes = 2 * 1024 * 1024
    record = evaluate(snapshot, request, None, gateway, "Synthetic policy", "synthetic")
    assert record["outcome"] == "unknown"
    assert gateway.count == 1
    assert snapshot.trajectory_json == raw
