from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.core.config import BACKEND_DIR, settings
from app.models import Base


class SchemaDrift(RuntimeError):
    pass


def alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(Path(BACKEND_DIR) / "alembic.ini"))
    config.attributes["database_url"] = database_url or settings.DATABASE_URL
    return config


def migrate_database(database_url: str | None = None) -> None:
    url = database_url or settings.DATABASE_URL
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
            careflow_tables = set(Base.metadata.tables)
            if "alembic_version" not in tables and tables.intersection(careflow_tables):
                differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
                if differences:
                    kinds = sorted({str(difference[0]) for difference in differences})
                    raise SchemaDrift(
                        "Existing database does not match the migration baseline "
                        f"({', '.join(kinds)}). Resolve the drift before stamping it."
                    )
                command.stamp(alembic_config(url), "head")
        command.upgrade(alembic_config(url), "head")
    finally:
        engine.dispose()
