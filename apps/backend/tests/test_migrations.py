"""Startup migration helper (audits COL-1 and C2).

create_all never ALTERs an existing table, so a deployment whose
analysis_logs predates the model_id column needs the startup ALTER, and one
whose runway_id still has the original VARCHAR(32) width needs the widening
ALTER. These tests pin: the column is added to a legacy table, the helper is
idempotent, the Postgres DDL is race-safe, the widening targets only truly
undersized columns, and a missing table is skipped.
"""

from __future__ import annotations

from app.migrations import (
    _add_column_sql,
    _undersized,
    _widen_column_sql,
    run_startup_migrations,
)
from sqlalchemy import String, Text, create_engine, inspect, text


def _legacy_engine(tmp_path):
    """A file-backed SQLite DB shaped like a REAL pre-migration deployment:
    no model_id column and the original (undersized) runway_id VARCHAR(32)."""
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE analysis_logs (
                    id VARCHAR(36) PRIMARY KEY,
                    media_type VARCHAR(24),
                    runway_id VARCHAR(32),
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


# --- runway_id widening (audit C2) ---------------------------------------


def test_widen_ddl_is_a_plain_alter_column_type():
    sql = _widen_column_sql("analysis_logs", "runway_id", "VARCHAR(96)")
    assert sql == "ALTER TABLE analysis_logs ALTER COLUMN runway_id TYPE VARCHAR(96)"


def test_undersized_detects_only_narrow_varchar():
    assert _undersized(String(32), 96) is True  # the real legacy width
    assert _undersized(String(96), 96) is False  # already migrated
    assert _undersized(String(128), 96) is False  # wider than needed
    assert _undersized(Text(), 96) is False  # unbounded — nothing to widen


def test_legacy_width_is_reflected_as_undersized(tmp_path):
    """The fixture's VARCHAR(32) must be SEEN as undersized through real
    reflection — this is the case the old test suite never covered (it built
    the 'legacy' table already at VARCHAR(96))."""
    engine = _legacy_engine(tmp_path)
    info = next(
        col for col in inspect(engine).get_columns("analysis_logs") if col["name"] == "runway_id"
    )
    assert _undersized(info["type"], 96) is True


def test_sqlite_skips_widening_but_still_accepts_long_ids(tmp_path):
    """On SQLite the widening is skipped (dialect guard): no ALTER COLUMN TYPE
    support, and declared widths are not enforced anyway — a >32-char custom
    runway id must still insert fine on the unmigrated table."""
    engine = _legacy_engine(tmp_path)

    run_startup_migrations(engine)  # must not raise / not attempt the ALTER

    info = next(
        col for col in inspect(engine).get_columns("analysis_logs") if col["name"] == "runway_id"
    )
    assert getattr(info["type"], "length", None) == 32  # declared width untouched
    long_id = "custom_" + "x" * 80
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO analysis_logs (id, media_type, runway_id) VALUES ('y', 'image', :rid)"),
            {"rid": long_id},
        )
        value = conn.execute(
            text("SELECT runway_id FROM analysis_logs WHERE id = 'y'")
        ).scalar()
    assert value == long_id
