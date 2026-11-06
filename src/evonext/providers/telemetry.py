"""Langfuse owns model traces. Business facts remain in the owning stores."""
import logging
import sys
from contextlib import contextmanager

from evonext.config import secret

log = logging.getLogger(__name__)


class Tracing:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client
        if client is None and settings.langfuse_enabled:
            if not (settings.langfuse_base_url and settings.langfuse_public_key and settings.langfuse_secret_key):
                raise ValueError("Explicit Langfuse endpoint and credentials are required")
            from langfuse import Langfuse
            self.client = Langfuse(public_key=settings.langfuse_public_key,
                secret_key=secret(settings.langfuse_secret_key), base_url=settings.langfuse_base_url)

    @contextmanager
    def generation(self, model, metadata):
        cm, observation, entered = None, None, False
        if self.client is not None:
            try:
                cm = self.client.start_as_current_observation(name="evonext.model", as_type="generation",
                                                               model=model, metadata=metadata)
                observation = cm.__enter__()
                entered = True
            except Exception:
                log.warning("Tracing start failed; model execution is independent")
        try:
            yield observation
        finally:
            error = sys.exc_info()
            if entered:
                try:
                    cm.__exit__(*error)
                except Exception:
                    log.warning("Tracing export failed; business result was not retried")

    def update(self, observation, **values):
        if observation is not None:
            try:
                observation.update(**values)
            except Exception:
                log.warning("Tracing update failed")

    def trace_id(self):
        if self.client is not None:
            try:
                return self.client.get_current_trace_id()
            except Exception:
                return None
        return None

    def close(self):
        if self.client is not None:
            try:
                self.client.flush()
            except Exception:
                log.warning("Tracing flush failed")
