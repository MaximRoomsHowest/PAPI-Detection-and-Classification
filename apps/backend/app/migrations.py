"""Minimal idempotent startup migrations.

There is no Alembic in this repo, and ``Base.metadata.create_all`` only
creates *missing tables* — it never alters an existing one. Until now every
column addition shipped with a "manual ALTER for existing deployments" note
(see the runway_id width comment on ``AnalysisLog``); this helper runs those
ALTERs automatically at startup instead.

Scope is deliberately tiny: additive, nullable columns only. Anything more
(type changes, index builds on big tables, backfills) deserves a real
migration tool.

Backfill decision for ``analysis_logs.model_id``: pre-existing rows keep
NULL — every read path falls back to ``result_json``; only the new
``model_id`` FILTER skips legacy rows. Optional operator backfill (Postgres):

    UPDATE analysis_logs
    SET model_id = result_json::jsonb->>'model_id'
    WHERE model_id IS NULL;
"""

from __future__ import annotations

import logging

from sqlalchemy import Engine, inspect, text

logger = logging.getLogger(__name__)

# (table, column, DDL type) tuples applied in order at startup.
_STARTUP_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("analysis_logs", "model_id", "VARCHAR(96)"),
)


def _add_column_sql(dialect_name: str, table: str, column: str, ddl_type: str) -> str:
    if dialect_name == "postgresql":
        # IF NOT EXISTS additionally makes concurrent replica startups race-safe.
        return f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl_type}"
    # SQLite (tests / local dev) has no IF NOT EXISTS for columns; the inspector
    # check below is the idempotence guard there.
    return f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"


def run_startup_migrations(engine: Engine) -> None:
    """Add any missing additive columns to already-existing tables."""
    inspector = inspect(engine)
    for table, column, ddl_type in _STARTUP_COLUMNS:
        if not inspector.has_table(table):
            # create_all either just built it (column included) or the table is
            # legitimately absent in this environment.
            continue
        existing = {col["name"] for col in inspector.get_columns(table)}
        if column in existing:
            continue
        logger.info("Startup migration: adding %s.%s (%s).", table, column, ddl_type)
        with engine.begin() as conn:
            conn.execute(text(_add_column_sql(engine.dialect.name, table, column, ddl_type)))
