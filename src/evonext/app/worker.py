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


@app.task(name="evonext.outcome", acks_late=True)
def outcome(run_id: str):
    from evonext.evidence.service import EvidenceService
    from evonext.evaluation.service import OutcomeService
    from evonext.evaluation.store import PostgresOutcomes
    from evonext.providers.gateway import ModelGateway
    if not settings.postgres_dsn or not settings.model_calls_enabled:
        raise RuntimeError("Outcome requires PostgreSQL and explicit model-call enablement")
    repository, assets = stores(settings)
    ledger = Ledger(secret(settings.postgres_dsn))
    gateway = None
    store = PostgresOutcomes(ledger.engine)
    try:
        try:
            gateway = ModelGateway(settings)
        except Exception as exc:
            from evonext.evaluation.outcome import result_record
            row = store.get(run_id)
            if row and store.claim(run_id):
                store.finish(run_id, result_record(row["frozen"], execution="error",
                                                   error=type(exc).__name__))
            raise
        service = OutcomeService(EvidenceService(repository, assets, settings), store, settings)
        return service.execute(run_id, gateway)["status"]
    finally:
        if gateway:
            gateway.close()
        ledger.close()
        repository.close()
        assets.close()
