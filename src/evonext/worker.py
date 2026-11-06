"""Use mature Celery transport; do not invent a second job scheduler."""
from celery import Celery
from pymongo.errors import AutoReconnect
from sqlalchemy.exc import OperationalError

from .config import Settings, secret
from .ledger import Ledger
from .storage import stores
from .verification import verify_snapshot

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
