"""
Alembic environment configuration for LegionTrap TI.

Reads DB_PATH from app.core.config.settings so that migration targets respect
the same environment variable as the application. Running against :memory: is
intentionally blocked here — Alembic migrations must run against a real file.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make project root importable when running `alembic` from the repo root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from app.core.config import settings  # noqa: E402

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

# Override the sqlalchemy.url from alembic.ini with the runtime DB_PATH.
if settings.DB_PATH == ":memory:":
    raise RuntimeError(
        "Alembic migrations cannot run against DB_PATH=':memory:'. "
        "Set DB_PATH to a file path before running migrations."
    )
config.set_main_option("sqlalchemy.url", f"sqlite:///{settings.DB_PATH}")

target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
