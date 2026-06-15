"""Minimal idempotent startup migrations.

There is no Alembic in this repo, and ``Base.metadata.create_all`` only
creates *missing tables* — it never alters an existing one. Until now every
column addition shipped with a "manual ALTER for existing deployments" note
(see the runway_id width comment on ``AnalysisLog``); this helper runs those
ALTERs automatically at startup instead.

Scope is deliberately tiny: additive nullable columns, plus in-place VARCHAR
*widening* (a metadata-only change on Postgres since 9.2 — no table rewrite,
no data loss). Anything more (real type changes, index builds on big tables,
backfills) deserves a real migration tool.

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
#
# NOTE for the model-lifecycle tables (``model_registry``, ``datasets``, ``jobs``):
# they are created whole by ``create_all`` on fresh DBs, so they need NO entry here
# today. But ``create_all`` never ALTERs an existing table — so any column ADDED to
# one of them later MUST get a row here too, or deployments that already built the
# table on an earlier version will be missing the column (same contract as
# ``analysis_logs.model_id`` below).
_STARTUP_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("analysis_logs", "model_id", "VARCHAR(96)"),
)

# Columns whose declared width grew after deployments shipped: (table, column,
# DDL type, minimum length). Postgres-only — SQLite ignores VARCHAR widths
# entirely (and has no ALTER COLUMN TYPE), so there is nothing to fix there.
_STARTUP_WIDENINGS: tuple[tuple[str, str, str, int], ...] = (
    # runway_id 32 -> 96: a custom runway id is "custom_" + an up-to-80-char
    # slug, which overflows the original VARCHAR(32) and 503s the analysis-log
    # write on Postgres (audit C2). create_all only sizes FRESH tables, so
    # pre-widening deployments keep 32 until this runs.
    ("analysis_logs", "runway_id", "VARCHAR(96)", 96),
)


def _add_column_sql(dialect_name: str, table: str, column: str, ddl_type: str) -> str:
    if dialect_name == "postgresql":
        # IF NOT EXISTS additionally makes concurrent replica startups race-safe.
        return f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl_type}"
    # SQLite (tests / local dev) has no IF NOT EXISTS for columns; the inspector
    # check below is the idempotence guard there.
    return f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"


def _widen_column_sql(table: str, column: str, ddl_type: str) -> str:
    # No IF-style guard exists for ALTER COLUMN TYPE, but the statement is
    # idempotent by effect: re-declaring VARCHAR(96) on a VARCHAR(96) column
    # is a no-op metadata change.
    return f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {ddl_type}"


def _undersized(col_type: object, min_length: int) -> bool:
    """True when a reflected column type declares a length below ``min_length``.

    ``length is None`` means TEXT/unbounded — never undersized.
    """
    length = getattr(col_type, "length", None)
    return length is not None and length < min_length


def run_startup_migrations(engine: Engine) -> None:
    """Add missing additive columns and widen undersized VARCHARs."""
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

    if engine.dialect.name != "postgresql":
        # SQLite does not enforce VARCHAR widths, so an "undersized" column
        # cannot overflow there — and it cannot ALTER COLUMN TYPE anyway.
        return
    for table, column, ddl_type, min_length in _STARTUP_WIDENINGS:
        if not inspector.has_table(table):
            continue
        info = next((col for col in inspector.get_columns(table) if col["name"] == column), None)
        if info is None or not _undersized(info["type"], min_length):
            continue
        logger.info("Startup migration: widening %s.%s to %s.", table, column, ddl_type)
        with engine.begin() as conn:
            conn.execute(text(_widen_column_sql(table, column, ddl_type)))
