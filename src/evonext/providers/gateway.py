"""A bounded model call with durable admission; not a judge or agent framework."""
import logging
from urllib.parse import urlsplit

import httpx

from evonext.config import secret
from evonext.contracts.trajectory import ContractError, encode_json, load_json, sha256
from evonext.providers.receipts import PostgresCallReceipts, ResponseReceipt
from evonext.providers.telemetry import Tracing

log = logging.getLogger(__name__)


class ModelGateway:
    def __init__(self, settings, transport=None, tracing=None, receipts=None):
        if not settings.model_name or not secret(settings.model_api_key):
            raise ContractError("Configure a model and credentials before making a paid call")
        url = urlsplit(settings.model_base_url)
        if url.scheme not in {"http", "https"} or not url.netloc or url.username or url.query or url.fragment:
            raise ContractError("Configure a trusted model endpoint")
        self.settings = settings.model_copy(deep=True)
        self.receipts = receipts
        self.tracing = tracing or Tracing(self.settings)
        self.client = httpx.Client(base_url=settings.model_base_url.rstrip("/") + "/",
            headers={"Authorization": "Bearer " + secret(settings.model_api_key)},
            timeout=60, follow_redirects=False, transport=transport)

    def complete(self, messages, *, snapshot_id=None, operation_id=None, max_tokens=256,
                 policy_version="manual.v1", repetition_id="0"):
        if not self.settings.model_calls_enabled:
            raise PermissionError("Model calls are explicitly disabled")
        if not operation_id or not isinstance(operation_id, str):
            raise ContractError("A stable operation_id is required for paid-call recovery")
        if type(max_tokens) is not int or not 1 <= max_tokens <= 4096:
            raise ContractError("Model output token budget must be between 1 and 4096")
        if not isinstance(repetition_id, str) or not repetition_id:
            raise ContractError("Explicit repetition identity must be a non-empty string")
        payload = {"model": self.settings.model_name, "messages": messages, "max_tokens": max_tokens}
        request_bytes = encode_json(payload)
        if len(request_bytes) > 1024 * 1024:
            raise ContractError("Model request exceeds the 1 MiB input budget")
        if self.receipts is None:
            if not self.settings.postgres_dsn or self.settings.demo:
                raise ContractError("Paid calls require a configured PostgreSQL receipt store")
            self.receipts = PostgresCallReceipts(secret(self.settings.postgres_dsn))
        identity = {"profile": "evonext.model-call.v1", "scope": self.settings.model_budget_scope,
                    "endpoint": str(self.client.base_url), "operation_id": operation_id,
                    "snapshot_id": snapshot_id, "policy_version": policy_version,
                    "repetition_id": repetition_id, "request_sha256": sha256(request_bytes)}
        key = sha256(encode_json(identity))
        limits = {60: self.settings.model_calls_per_minute,
                  3600: self.settings.model_calls_per_hour, 86400: self.settings.model_calls_per_day}
        # A single deployment/account scope shares budget across different model routes.
        saved = self.receipts.begin(key, self.settings.model_budget_scope, limits)
        if saved is not None:
            return self._decode(saved, key, reused=True)
        metadata = {"snapshot_id": snapshot_id or "", "operation_id": operation_id,
                    "call_key": key, "policy_version": policy_version,
                    "repetition_id": repetition_id,
                    "content_capture": str(self.settings.trace_content).lower()}
        try:
            with self.tracing.generation(self.settings.model_name, metadata) as observation:
                self.tracing.update(observation, input=messages if self.settings.trace_content else "[not captured]")
                with self.client.stream("POST", "chat/completions", content=request_bytes,
                                        headers={"Content-Type": "application/json"}) as response:
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 4 * 1024 * 1024:
                            raise ContractError("Model response exceeds storage budget; outcome unknown")
                    saved = ResponseReceipt(response.status_code, bytes(body).decode("utf-8"),
                                            self.tracing.trace_id())
                # Persist even malformed JSON / non-2xx BEFORE any semantic parsing.
                self.receipts.receive(key, saved)
                output = self._decode(saved, key, reused=False)
                values = {"output": output["response"] if self.settings.trace_content else "[not captured]"}
                usage = output["usage"]
                if isinstance(usage, dict):
                    values["usage_details"] = {k: usage[s] for k, s in
                        (("input", "prompt_tokens"), ("output", "completion_tokens"), ("total", "total_tokens"))
                        if s in usage}
                self.tracing.update(observation, **values)
                return output
        except Exception:
            # receive() already committed -> unknown() is a no-op. A receipt outage
            # leaves sending; both sending and unknown prohibit automatic resend.
            try:
                self.receipts.unknown(key)
            except Exception:
                log.warning("Could not settle model receipt; reconcile its persisted sending state")
            raise

    def complete_policy(self, policy, *, snapshot_id, operation_id, repetition_id="0"):
        if policy.config["model_profile"] != self.settings.model_name:
            raise ContractError("Policy model profile does not match the configured model route")
        return self.complete([{"role": "system", "content": policy.prompt}],
            snapshot_id=snapshot_id, operation_id=operation_id,
            max_tokens=policy.config["max_tokens"], policy_version=policy.version,
            repetition_id=repetition_id)

    def _decode(self, saved, key, *, reused):
        if not 200 <= saved.status_code < 300:
            response = httpx.Response(saved.status_code, request=httpx.Request("POST", self.client.base_url))
            response.raise_for_status()
        output = load_json(saved.body.encode("utf-8"))
        return {"response": output, "declared_model": self.settings.model_name,
                "observed_model": output.get("model"), "usage": output.get("usage"),
                "trace_id": saved.trace_id, "call_key": key, "reused": reused}

    def close(self):
        self.client.close()
        self.tracing.close()
        if self.receipts is not None:
            self.receipts.close()
