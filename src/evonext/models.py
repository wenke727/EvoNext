"""An explicit, bounded model call, not an automatic judge or an agent framework."""
from urllib.parse import urlsplit

import httpx

from .config import secret
from .domain import ContractError
from .telemetry import Tracing


class ModelGateway:
    def __init__(self, settings, transport=None, tracing=None):
        if not settings.model_name or not secret(settings.model_api_key):
            raise ContractError("Configure a model and credentials before making a paid call")
        url = urlsplit(settings.model_base_url)
        if url.scheme not in {"http", "https"} or not url.netloc or url.username or url.query:
            raise ContractError("Configure a trusted model endpoint")
        self.settings = settings
        self.tracing = tracing or Tracing(settings)
        self.client = httpx.Client(base_url=settings.model_base_url.rstrip("/") + "/",
            headers={"Authorization": "Bearer " + secret(settings.model_api_key)},
            timeout=60, follow_redirects=False, transport=transport)

    def complete(self, messages, *, snapshot_id=None, operation_id=None, max_tokens=256):
        if not 1 <= max_tokens <= 4096:
            raise ContractError("Model output token budget must be between 1 and 4096")
        metadata = {"snapshot_id": snapshot_id or "", "operation_id": operation_id or "",
                    "content_capture": str(self.settings.trace_content).lower()}
        with self.tracing.generation(self.settings.model_name, metadata) as observation:
            self.tracing.update(observation, input=messages if self.settings.trace_content else "[not captured]")
            # No automatic HTTP retry: a timeout may already have incurred a charge.
            response = self.client.post("chat/completions", json={"model": self.settings.model_name,
                "messages": messages, "max_tokens": max_tokens})
            response.raise_for_status()
            output = response.json()
            usage = output.get("usage")
            values = {"output": output if self.settings.trace_content else "[not captured]"}
            if usage:
                values["usage_details"] = {k: usage[s] for k, s in
                    (("input", "prompt_tokens"), ("output", "completion_tokens"), ("total", "total_tokens"))
                    if s in usage}
            self.tracing.update(observation, **values)
            return {"response": output, "declared_model": self.settings.model_name,
                    "observed_model": output.get("model"), "usage": usage,
                    "trace_id": self.tracing.trace_id()}

    def close(self):
        self.client.close()
        self.tracing.close()
