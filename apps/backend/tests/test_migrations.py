"""Startup migration helper (audit COL-1).

create_all never ALTERs an existing table, so a deployment whose
analysis_logs predates the model_id column needs the startup ALTER. These
tests pin: the column is added to a legacy table, the helper is idempotent,
the Postgres DDL is race-safe, and a missing table is skipped.
"""

from __future__ import annotations

from app.migrations import _add_column_sql, run_startup_migrations
from sqlalchemy import create_engine, inspect, text


def _legacy_engine(tmp_path):
    """A file-backed SQLite DB whose analysis_logs table lacks model_id."""
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE analysis_logs (
                    id VARCHAR(36) PRIMARY KEY,
                    media_type VARCHAR(24),
                    runway_id VARCHAR(96),
                    created_at DATETIME
                )
                """
            )
        )
    return engine


def test_adds_model_id_column_to_legacy_table(tmp_path):
    engine = _legacy_engine(tmp_path)

    run_startup_migrations(engine)

    columns = {col["name"] for col in inspect(engine).get_columns("analysis_logs")}
    assert "model_id" in columns
    # The migrated table accepts writes that use the new column.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO analysis_logs (id, media_type, runway_id, model_id) "
                "VALUES ('x', 'image', 'papi_24', 'nano')"
            )
        )
        value = conn.execute(
            text("SELECT model_id FROM analysis_logs WHERE id = 'x'")
        ).scalar()
    assert value == "nano"


def test_startup_migration_is_idempotent(tmp_path):
    engine = _legacy_engine(tmp_path)

    run_startup_migrations(engine)
    run_startup_migrations(engine)  # second run must not raise (SQLite has no IF NOT EXISTS)

    columns = [col["name"] for col in inspect(engine).get_columns("analysis_logs")]
    assert columns.count("model_id") == 1


def test_fresh_create_all_table_needs_no_alter(tmp_path):
    """A table built by create_all already has the column; the helper no-ops."""
    from app import models  # noqa: F401 -- registers AnalysisLog
    from app.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    Base.metadata.create_all(bind=engine)

    run_startup_migrations(engine)  # must not raise (duplicate ADD would)

    columns = [col["name"] for col in inspect(engine).get_columns("analysis_logs")]
    assert columns.count("model_id") == 1


def test_postgres_ddl_uses_add_column_if_not_exists():
    sql = _add_column_sql("postgresql", "analysis_logs", "model_id", "VARCHAR(96)")
    assert sql == "ALTER TABLE analysis_logs ADD COLUMN IF NOT EXISTS model_id VARCHAR(96)"
    sqlite_sql = _add_column_sql("sqlite", "analysis_logs", "model_id", "VARCHAR(96)")
    assert "IF NOT EXISTS" not in sqlite_sql


def test_skips_missing_table(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    run_startup_migrations(engine)  # no analysis_logs at all — must not raise
    assert not inspect(engine).has_table("analysis_logs")
