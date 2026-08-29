import uuid

import psycopg2
import pytest
from alembic import command
from psycopg2 import sql
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.db.migrations import SchemaDrift, alembic_config, migrate_database
from app.models import Base


@pytest.fixture
def migration_database_url():
    database_name = f"careflow_migration_test_{uuid.uuid4().hex}"
    configured_url = make_url(settings.DATABASE_URL)
    admin_url = configured_url.set(drivername="postgresql", database="postgres")
    connection = psycopg2.connect(admin_url.render_as_string(hide_password=False))
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        yield configured_url.set(database=database_name).render_as_string(hide_password=False)
    finally:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
        connection.close()


def test_fresh_database_upgrades_and_downgrades(migration_database_url):
    migrate_database(migration_database_url)
    engine = create_engine(migration_database_url)
    try:
        assert set(Base.metadata.tables) <= set(inspect(engine).get_table_names())
        command.downgrade(alembic_config(migration_database_url), "base")
        assert set(Base.metadata.tables).isdisjoint(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_matching_existing_schema_is_safely_adopted(migration_database_url):
    engine = create_engine(migration_database_url)
    try:
        Base.metadata.create_all(engine)
        migrate_database(migration_database_url)
        assert "alembic_version" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_schema_drift_is_not_stamped(migration_database_url):
    engine = create_engine(migration_database_url)
    try:
        Base.metadata.tables["application_users"].create(engine)
        with pytest.raises(SchemaDrift):
            migrate_database(migration_database_url)
        assert "alembic_version" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()
