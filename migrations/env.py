from alembic import context
from sqlalchemy import create_engine

from evonext.config import Settings, secret
from evonext.ledger import metadata

settings = Settings()
if not settings.postgres_dsn:
    raise RuntimeError("EVONEXT_POSTGRES_DSN is required")
url = secret(settings.postgres_dsn)
if context.is_offline_mode():
    context.configure(url=url, target_metadata=metadata, literal_binds=True, include_schemas=True,
                      version_table="evonext_alembic_version")
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata, include_schemas=True,
                          version_table="evonext_alembic_version")
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
