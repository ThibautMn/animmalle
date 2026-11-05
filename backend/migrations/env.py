"""Le mode hors ligne ne lit aucun secret et ne se connecte à aucun serveur."""

from alembic import context
from sqlalchemy import create_engine, pool

from animmalle.config import load_database_url
from animmalle.models import Base


def run_migrations_offline():
    context.configure(dialect_name='postgresql', target_metadata=Base.metadata,
                      literal_binds=True, compare_type=True,
                      compare_server_default=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = create_engine(load_database_url(), poolclass=pool.NullPool,
                           hide_parameters=True)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata,
                              compare_type=True, compare_server_default=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
