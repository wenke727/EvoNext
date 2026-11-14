"""Use mature Celery transport; do not invent a second job scheduler."""
from celery import Celery
from pymongo.errors import AutoReconnect
from sqlalchemy.exc import OperationalError

from evonext.config import Settings, secret
from evonext.operations.ledger import Ledger
from evonext.evidence.store import stores
from evonext.operations.verification import verify_snapshot

settings = Settings()
if settings.demo:
    raise RuntimeError("A separate worker cannot share demo memory; configure real infrastructure")
app = Celery("evonext", broker=secret(settings.broker_url))
app.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json",
    task_ignore_result=True, worker_prefetch_multiplier=1,
    task_default_queue="evonext.bulk", task_create_missing_queues=True,
    broker_connection_retry_on_startup=True)


@app.task(name="evonext.verify_snapshot", acks_late=True,
          autoretry_for=(AutoReconnect, OperationalError), retry_backoff=True,
          retry_kwargs={"max_retries": 3})
def verify(snapshot_id: str):
    if not settings.postgres_dsn:
        raise RuntimeError("Configure PostgreSQL and run migrations before starting a worker")
    repository, assets = stores(settings)
    ledger = Ledger(secret(settings.postgres_dsn))
    try:
        return verify_snapshot(snapshot_id, repository, assets, ledger)
    finally:
        repository.close()
        ledger.close()


@app.task(name="evonext.evaluate", acks_late=True)
def evaluate(operation_id: str):
    from evonext.evaluation.service import run, keys
    from evonext.evidence.service import EvidenceService
    from evonext.providers.gateway import ModelGateway
    repository, assets = stores(settings)
    ledger = Ledger(secret(settings.postgres_dsn))
    gateway = None
    try:
        gateway = ModelGateway(settings)
        return run(operation_id, EvidenceService(repository, assets, settings), ledger, gateway)
    except Exception as exc:
        request_key, _ = keys(operation_id)
        row = ledger.get(request_key)
        if row:
            ledger.record(request_key + "-error", row["snapshot_id"], "evaluation_error.v1",
                          {"error_type": type(exc).__name__, "automatic_retry": False})
        raise
    finally:
        if gateway is not None:
            gateway.close()
        repository.close()
        assets.close()
        ledger.close()


@app.task(name="evonext.workshop", acks_late=True)
def workshop(operation_id: str):
    from evonext.app.workshop_api import configured_workshop
    from evonext.evidence.service import EvidenceService
    from evonext.providers.gateway import ModelGateway
    from evonext.skills.workshop.service import run, keys
    repository, assets = stores(settings)
    ledger = Ledger(secret(settings.postgres_dsn))
    gateway = None
    try:
        gateway = ModelGateway(settings)
        return run(operation_id, configured_workshop(settings),
                   EvidenceService(repository, assets, settings), ledger, gateway)
    except Exception as exc:
        key = keys(operation_id)
        row = ledger.get(key)
        if row:
            ledger.record(key + "-error", row["snapshot_id"], "workshop_error.v1",
                          {"automatic_retry": False, "needs_reconciliation": True,
                           "error_type": type(exc).__name__})
        raise exc
    finally:
        if gateway is not None:
            gateway.close()
        repository.close()
        assets.close()
        ledger.close()
