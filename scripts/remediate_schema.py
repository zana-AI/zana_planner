#!/usr/bin/env python3
"""Remediate schema drift by applying missing DDL from migrations 003-006.

The alembic_version table says we're at 012 (head), but migrations 003-006
silently failed due to try/except: pass wrappers.  This script idempotently
applies the missing DDL so the live schema matches what 012 expects.

Usage:
    # Dry-run (default) — shows SQL but does not execute
    python scripts/remediate_schema.py --database-url postgresql://...

    # Actually apply changes
    python scripts/remediate_schema.py --database-url postgresql://... --apply

    # Or use env var
    DATABASE_URL_STAGING=postgresql://... python scripts/remediate_schema.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys


def get_url(args) -> str:
    return args.database_url or os.getenv("DATABASE_URL_STAGING") or os.getenv("DATABASE_URL") or ""


def has_table(conn, table: str) -> bool:
    from sqlalchemy import text
    row = conn.execute(text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=:t"
    ), {"t": table}).fetchone()
    return row is not None


def has_column(conn, table: str, column: str) -> bool:
    from sqlalchemy import text
    row = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
    ), {"t": table, "c": column}).fetchone()
    return row is not None


def has_index(conn, index_name: str) -> bool:
    from sqlalchemy import text
    row = conn.execute(text(
        "SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:i"
    ), {"i": index_name}).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Each step is (description, callable(conn) -> list[sql_to_run])
# The callable inspects the DB and returns SQL only if the change is needed.
# ---------------------------------------------------------------------------

def _migration_003_steps(conn) -> list[tuple[str, str]]:
    """Migration 003: schedules, reminders, suggestions tables."""
    steps = []

    if not has_table(conn, "promise_schedule_weekly_slots"):
        steps.append(("Create table promise_schedule_weekly_slots", """
            CREATE TABLE promise_schedule_weekly_slots (
                slot_id TEXT NOT NULL PRIMARY KEY,
                promise_uuid TEXT NOT NULL REFERENCES promises(promise_uuid),
                weekday SMALLINT NOT NULL,
                start_local_time TIME NOT NULL,
                end_local_time TIME,
                tz TEXT,
                start_date TEXT,
                end_date TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                CONSTRAINT check_weekday_range CHECK (weekday >= 0 AND weekday <= 6)
            );
        """))
        steps.append(("Index ix_schedule_slots_promise",
                       "CREATE INDEX IF NOT EXISTS ix_schedule_slots_promise ON promise_schedule_weekly_slots(promise_uuid, is_active);"))

    if not has_table(conn, "promise_reminders"):
        steps.append(("Create table promise_reminders", """
            CREATE TABLE promise_reminders (
                reminder_id TEXT NOT NULL PRIMARY KEY,
                promise_uuid TEXT NOT NULL REFERENCES promises(promise_uuid),
                slot_id TEXT REFERENCES promise_schedule_weekly_slots(slot_id),
                kind TEXT NOT NULL,
                offset_minutes INTEGER,
                weekday SMALLINT,
                time_local TIME,
                tz TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                last_sent_at_utc TEXT,
                next_run_at_utc TEXT,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                CONSTRAINT check_reminder_kind CHECK (kind IN ('slot_offset', 'fixed_time')),
                CONSTRAINT check_reminder_weekday_range CHECK (weekday IS NULL OR (weekday >= 0 AND weekday <= 6))
            );
        """))
        steps.append(("Index ix_reminders_promise",
                       "CREATE INDEX IF NOT EXISTS ix_reminders_promise ON promise_reminders(promise_uuid, enabled);"))
        steps.append(("Index ix_reminders_next_run",
                       "CREATE INDEX IF NOT EXISTS ix_reminders_next_run ON promise_reminders(next_run_at_utc) WHERE enabled = 1 AND next_run_at_utc IS NOT NULL;"))
        steps.append(("Index ix_reminders_slot",
                       "CREATE INDEX IF NOT EXISTS ix_reminders_slot ON promise_reminders(slot_id);"))

    # promise_suggestions already exists per the drift check (not in missing list)

    return steps


def _migration_004_steps(conn) -> list[tuple[str, str]]:
    """Migration 004: simplify promise_templates (add new cols, drop legacy cols, copy data)."""
    steps = []

    # Add new columns
    if not has_column(conn, "promise_templates", "description"):
        steps.append(("Add promise_templates.description",
                       "ALTER TABLE promise_templates ADD COLUMN description TEXT;"))
        steps.append(("Copy why → description",
                       "UPDATE promise_templates SET description = why WHERE why IS NOT NULL AND why != '';"))

    if not has_column(conn, "promise_templates", "emoji"):
        steps.append(("Add promise_templates.emoji",
                       "ALTER TABLE promise_templates ADD COLUMN emoji TEXT;"))

    if not has_column(conn, "promise_templates", "created_by_user_id"):
        steps.append(("Add promise_templates.created_by_user_id",
                       "ALTER TABLE promise_templates ADD COLUMN created_by_user_id TEXT;"))

    # Drop legacy columns
    legacy_cols = [
        "program_key", "level", "why", "done", "effort", "template_kind",
        "target_direction", "estimated_hours_per_unit", "duration_type",
        "duration_weeks", "canonical_key", "source_promise_uuid", "origin",
    ]
    for col in legacy_cols:
        if has_column(conn, "promise_templates", col):
            steps.append((f"Drop promise_templates.{col}",
                           f"ALTER TABLE promise_templates DROP COLUMN IF EXISTS {col};"))

    # Drop stale indexes
    if has_index(conn, "ix_templates_canonical_key"):
        steps.append(("Drop ix_templates_canonical_key",
                       "DROP INDEX IF EXISTS ix_templates_canonical_key;"))

    if has_index(conn, "ix_templates_program"):
        steps.append(("Drop ix_templates_program (references dropped program_key/level)",
                       "DROP INDEX IF EXISTS ix_templates_program;"))

    return steps


def _migration_005_steps(conn) -> list[tuple[str, str]]:
    """Migration 005: user profiling tables."""
    steps = []

    if not has_table(conn, "user_profile_facts"):
        steps.append(("Create table user_profile_facts", """
            CREATE TABLE user_profile_facts (
                user_id TEXT NOT NULL,
                field_key TEXT NOT NULL,
                value_text TEXT NOT NULL,
                source TEXT NOT NULL,
                confidence DOUBLE PRECISION NOT NULL,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                PRIMARY KEY (user_id, field_key),
                CONSTRAINT check_profile_source CHECK (source IN ('explicit_answer', 'inferred', 'system')),
                CONSTRAINT check_profile_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0)
            );
        """))
        steps.append(("Index ix_profile_facts_user",
                       "CREATE INDEX IF NOT EXISTS ix_profile_facts_user ON user_profile_facts(user_id);"))
        steps.append(("Index ix_profile_facts_field",
                       "CREATE INDEX IF NOT EXISTS ix_profile_facts_field ON user_profile_facts(user_id, field_key);"))

    if not has_table(conn, "user_profile_state"):
        steps.append(("Create table user_profile_state", """
            CREATE TABLE user_profile_state (
                user_id TEXT NOT NULL PRIMARY KEY REFERENCES users(user_id),
                pending_field_key TEXT,
                pending_question_text TEXT,
                pending_asked_at_utc TEXT,
                last_question_asked_at_utc TEXT
            );
        """))

    return steps


def _migration_006_steps(conn) -> list[tuple[str, str]]:
    """Migration 006: bot_tokens table, broadcasts.bot_token_id column."""
    steps = []

    if not has_table(conn, "bot_tokens"):
        steps.append(("Create table bot_tokens", """
            CREATE TABLE bot_tokens (
                bot_token_id TEXT NOT NULL PRIMARY KEY,
                bot_token TEXT NOT NULL,
                bot_username TEXT,
                is_active BOOLEAN NOT NULL DEFAULT true,
                description TEXT,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            );
        """))
        steps.append(("Index ix_bot_tokens_active",
                       "CREATE INDEX IF NOT EXISTS ix_bot_tokens_active ON bot_tokens(is_active);"))

    if not has_column(conn, "broadcasts", "bot_token_id"):
        steps.append(("Add broadcasts.bot_token_id",
                       "ALTER TABLE broadcasts ADD COLUMN bot_token_id TEXT;"))

    return steps


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ALL_MIGRATION_STEPS = [
    ("003 — Schedules, reminders", _migration_003_steps),
    ("004 — Simplify promise_templates", _migration_004_steps),
    ("005 — User profiling", _migration_005_steps),
    ("006 — Bot tokens", _migration_006_steps),
]


def main():
    parser = argparse.ArgumentParser(description="Remediate schema drift (idempotent)")
    parser.add_argument("--database-url", help="PostgreSQL connection URL")
    parser.add_argument("--apply", action="store_true", help="Actually execute SQL (default is dry-run)")
    args = parser.parse_args()

    db_url = get_url(args)
    if not db_url:
        print("ERROR: No database URL. Set DATABASE_URL_STAGING or pass --database-url.", file=sys.stderr)
        sys.exit(2)

    from sqlalchemy import create_engine, text
    engine = create_engine(db_url, echo=False)

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        print(f"ERROR: Could not connect: {e}", file=sys.stderr)
        sys.exit(2)

    total_steps = 0
    with engine.connect() as conn:
        for label, step_fn in ALL_MIGRATION_STEPS:
            steps = step_fn(conn)
            if not steps:
                print(f"\n  [{label}] — nothing to do")
                continue

            print(f"\n  [{label}] — {len(steps)} change(s)")
            for desc, sql in steps:
                total_steps += 1
                sql_oneline = " ".join(sql.split())
                if len(sql_oneline) > 120:
                    sql_oneline = sql_oneline[:117] + "..."
                if args.apply:
                    try:
                        conn.execute(text(sql))
                        print(f"    ✓ {desc}")
                    except Exception as e:
                        print(f"    ✗ {desc}: {e}")
                else:
                    print(f"    [DRY-RUN] {desc}")
                    print(f"              {sql_oneline}")

        if args.apply:
            conn.commit()
            print(f"\n  Committed {total_steps} change(s).")
        else:
            conn.rollback()
            print(f"\n  Dry-run complete. {total_steps} change(s) would be applied.")
            print(f"  Re-run with --apply to execute.")


if __name__ == "__main__":
    main()
