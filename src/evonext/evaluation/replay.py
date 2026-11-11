"""Explicit offline replay of supplied synthetic judge responses."""
from evonext.contracts.trajectory import ContractError, encode_json


class ReplayGateway:
    def __init__(self, responses):
        if not isinstance(responses, list) or not responses or len(responses) > 11:
            raise ContractError("Replay requires 1–11 explicit synthetic response objects")
        self.responses = iter(responses)
        self.count = 0

    def complete(self, messages, **identity):
        try:
            reply = next(self.responses)
        except StopIteration as exc:
            raise ContractError("Synthetic replay has no response for the next call") from exc
        self.count += 1
        return {"response": {"choices": [{"message": {"content": encode_json(reply).decode()}}]},
                "trace_id": None, "call_key": f"synthetic-replay-{self.count}",
                "declared_model": "synthetic_replay", "observed_model": "synthetic_replay", "usage": None}
