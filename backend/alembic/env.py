"""
Alembic environment configuration for System Database migrations.

Reads SYSTEM_DATABASE_URL from .env via app.config and targets
the SystemBase metadata so that autogenerate works correctly.
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings
from app.models.system import SystemBase

# Alembic Config object
config = context.config

# Set up loggers
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use SystemBase metadata for autogenerate
target_metadata = SystemBase.metadata

# Override sqlalchemy.url from environment
system_url = settings.system_database_url
if system_url:
    # Escape % for configparser interpolation (e.g. URL-encoded passwords)
    config.set_main_option("sqlalchemy.url", system_url.replace("%", "%%"))


def run_migrations_offline() -> None:
    """Run migrations in offline mode (emit SQL without connecting)."""
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
    """Run migrations in online mode (connect to database)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
