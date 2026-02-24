#!/usr/bin/env python3
"""Check live database schema against the expected schema at migration head (012).

Usage:
    # Uses DATABASE_URL_STAGING by default (or DATABASE_URL)
    python scripts/check_schema_drift.py

    # Point at a specific database
    DATABASE_URL=postgresql://... python scripts/check_schema_drift.py

    # JSON output for CI
    python scripts/check_schema_drift.py --json

Exit codes:
    0  – schema matches expected
    1  – drift detected (missing/extra tables or columns)
    2  – connection error
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# ---------------------------------------------------------------------------
# Expected schema at migration HEAD (012_content_learning_pipeline)
# Derived by replaying migrations 001 → 012 and tracking every ADD/DROP.
# ---------------------------------------------------------------------------

EXPECTED_SCHEMA: dict[str, list[str]] = {
    # --- 001: initial ---
    "schema_version": [
        "version", "applied_at_utc",
    ],
    "users": [
        "user_id", "timezone", "nightly_hh", "nightly_mm", "language",
        "voice_mode", "created_at_utc", "updated_at_utc", "first_name",
        "username", "last_seen_utc", "last_name", "display_name",
        "is_private", "default_promise_visibility", "avatar_file_id",
        "avatar_file_unique_id", "avatar_path", "avatar_updated_at_utc",
        "avatar_checked_at_utc", "avatar_visibility", "chat_not_found",
    ],
    "promises": [
        # 008 dropped angle_deg, radius
        "promise_uuid", "user_id", "current_id", "text", "hours_per_week",
        "recurring", "start_date", "end_date", "is_deleted",
        "created_at_utc", "updated_at_utc", "visibility", "description",
    ],
    "promise_aliases": [
        "user_id", "alias_id", "promise_uuid", "created_at_utc",
    ],
    "promise_events": [
        "event_uuid", "promise_uuid", "user_id", "event_type", "at_utc",
        "snapshot_json",
    ],
    "actions": [
        # 007 added notes
        "action_uuid", "user_id", "promise_uuid", "promise_id_text",
        "action_type", "time_spent_hours", "at_utc", "notes",
    ],
    "sessions": [
        # 009 added focus-timer fields
        "session_id", "user_id", "promise_uuid", "status",
        "started_at_utc", "ended_at_utc", "paused_seconds_total",
        "last_state_change_at_utc", "message_id", "chat_id",
        "expected_end_utc", "planned_duration_minutes", "timer_kind",
        "notified_at_utc",
    ],
    "legacy_imports": [
        "user_id", "source", "source_mtime_utc", "imported_at_utc",
    ],
    "conversations": [
        # 010 added importance fields
        "id", "user_id", "chat_id", "message_id", "message_type",
        "content", "created_at_utc", "conversation_session_id",
        "importance_score", "importance_reasoning", "intent_category",
        "key_themes", "scored_at_utc",
    ],
    "user_relationships": [
        "source_user_id", "target_user_id", "relationship_type",
        "is_active", "created_at_utc", "updated_at_utc", "ended_at_utc",
        "metadata",
    ],
    "clubs": [
        "club_id", "owner_user_id", "name", "description", "visibility",
        "created_at_utc", "updated_at_utc",
    ],
    "club_members": [
        "club_id", "user_id", "role", "status", "joined_at_utc",
        "left_at_utc",
    ],
    "promise_club_shares": [
        "promise_uuid", "club_id", "created_at_utc",
    ],
    "milestones": [
        "milestone_uuid", "user_id", "milestone_type", "value_int",
        "value_text", "promise_uuid", "trigger_action_uuid",
        "trigger_session_id", "computed_at_utc", "payload_json",
    ],
    "feed_items": [
        "feed_item_uuid", "actor_user_id", "created_at_utc", "visibility",
        "title", "body", "action_uuid", "session_id", "milestone_uuid",
        "promise_uuid", "context_json", "dedupe_key", "is_deleted",
    ],
    "feed_reactions": [
        "reaction_uuid", "feed_item_uuid", "actor_user_id",
        "reaction_type", "created_at_utc", "is_deleted",
    ],
    "social_events": [
        "event_uuid", "actor_user_id", "event_type", "subject_type",
        "subject_id", "object_type", "object_id", "created_at_utc",
        "metadata_json",
    ],
    "broadcasts": [
        # 006 added bot_token_id
        "broadcast_id", "admin_id", "message", "target_user_ids",
        "scheduled_time_utc", "status", "created_at_utc",
        "updated_at_utc", "bot_token_id",
    ],
    "promise_templates": [
        # 004 dropped: program_key, level, why, done, effort, template_kind,
        #   target_direction, estimated_hours_per_unit, duration_type,
        #   duration_weeks, canonical_key, source_promise_uuid, origin
        # 004 added: description, emoji
        "template_id", "category", "title", "metric_type", "target_value",
        "is_active", "created_at_utc", "updated_at_utc",
        "created_by_user_id", "description", "emoji",
    ],
    "template_prerequisites": [
        "prereq_id", "template_id", "prereq_group", "kind",
        "required_template_id", "min_success_rate", "window_weeks",
        "created_at_utc",
    ],
    "promise_instances": [
        "instance_id", "user_id", "template_id", "promise_uuid", "status",
        "metric_type", "target_value", "estimated_hours_per_unit",
        "start_date", "end_date", "created_at_utc", "updated_at_utc",
    ],
    "promise_weekly_reviews": [
        "review_id", "user_id", "instance_id", "week_start", "week_end",
        "metric_type", "target_value", "achieved_value", "success_ratio",
        "note", "computed_at_utc",
    ],
    "distraction_events": [
        "event_uuid", "user_id", "category", "minutes", "at_utc",
        "created_at_utc",
    ],
    # --- 003: schedules / reminders / suggestions ---
    "promise_schedule_weekly_slots": [
        "slot_id", "promise_uuid", "weekday", "start_local_time",
        "end_local_time", "tz", "start_date", "end_date", "is_active",
        "created_at_utc", "updated_at_utc",
    ],
    "promise_reminders": [
        "reminder_id", "promise_uuid", "slot_id", "kind",
        "offset_minutes", "weekday", "time_local", "tz", "enabled",
        "last_sent_at_utc", "next_run_at_utc", "created_at_utc",
        "updated_at_utc",
    ],
    "promise_suggestions": [
        "suggestion_id", "from_user_id", "to_user_id", "status",
        "template_id", "draft_json", "message", "created_at_utc",
        "responded_at_utc",
    ],
    # --- 005: user profiling ---
    "user_profile_facts": [
        "user_id", "field_key", "value_text", "source", "confidence",
        "created_at_utc", "updated_at_utc",
    ],
    "user_profile_state": [
        "user_id", "pending_field_key", "pending_question_text",
        "pending_asked_at_utc", "last_question_asked_at_utc",
    ],
    # --- 006: bot tokens ---
    "bot_tokens": [
        "bot_token_id", "bot_token", "bot_username", "is_active",
        "description", "created_at_utc", "updated_at_utc",
    ],
    # --- 011: content manager ---
    "content": [
        "id", "canonical_url", "original_url", "provider", "content_type",
        "title", "description", "author_channel", "language",
        "published_at", "duration_seconds", "estimated_read_seconds",
        "thumbnail_url", "metadata_json", "created_at", "updated_at",
    ],
    "user_content": [
        "id", "user_id", "content_id", "status", "added_at",
        "last_interaction_at", "completed_at", "last_position",
        "position_unit", "progress_ratio", "total_consumed_seconds",
        "notes", "rating",
    ],
    "content_consumption_event": [
        "id", "user_id", "content_id", "event_type", "start_position",
        "end_position", "position_unit", "started_at", "ended_at",
        "client", "device_id", "created_at",
    ],
    "user_content_rollup": [
        "user_id", "content_id", "bucket_count", "buckets", "updated_at",
    ],
    # --- 012: learning pipeline ---
    "content_ingest_job": [
        "id", "user_id", "content_id", "pipeline_version", "status",
        "stage", "attempt_count", "error_code", "error_detail",
        "created_at", "started_at", "finished_at", "trace_id",
    ],
    "content_asset": [
        "id", "content_id", "asset_type", "storage_uri", "size_bytes",
        "checksum", "created_at",
    ],
    "content_segment": [
        "id", "content_id", "segment_index", "text", "start_ms",
        "end_ms", "section_path", "token_count", "created_at",
    ],
    "content_artifact": [
        "id", "content_id", "artifact_type", "artifact_format",
        "payload_json", "model_name", "created_at",
    ],
    "content_concept": [
        "id", "content_id", "label", "concept_type", "definition",
        "examples_json", "importance_weight", "support_count",
        "created_at", "updated_at",
    ],
    "content_concept_edge": [
        "id", "content_id", "source_concept_id", "target_concept_id",
        "relation_type", "confidence", "weight", "created_at",
    ],
    "quiz_set": [
        "id", "content_id", "version", "title", "difficulty",
        "created_at",
    ],
    "quiz_question": [
        "id", "quiz_set_id", "concept_id", "question_type", "difficulty",
        "prompt", "options_json", "answer_key_json", "rationale",
        "source_segment_ids_json", "position",
    ],
    "quiz_attempt": [
        "id", "user_id", "quiz_set_id", "score", "max_score",
        "started_at", "submitted_at", "graded_at", "status",
        "idempotency_key",
    ],
    "quiz_attempt_answer": [
        "id", "attempt_id", "question_id", "user_answer_json",
        "is_correct", "score_awarded", "feedback", "graded_by_model",
        "created_at",
    ],
    "user_concept_mastery": [
        "user_id", "concept_id", "mastery_score", "attempt_count",
        "correct_count", "last_tested_at", "updated_at",
    ],
}

# View expected after migration 008 re-creates it
EXPECTED_VIEWS: dict[str, list[str]] = {
    "promises_with_type": [
        "promise_uuid", "user_id", "current_id", "text", "hours_per_week",
        "recurring", "start_date", "end_date", "is_deleted", "visibility",
        "description", "created_at_utc", "updated_at_utc",
        "is_check_based", "is_time_based", "promise_type",
    ],
}

# Columns that MUST NOT exist (were dropped by migrations).
# table -> [columns that should be gone]
MUST_NOT_EXIST: dict[str, list[str]] = {
    "promise_templates": [
        "program_key", "level", "why", "done", "effort", "template_kind",
        "target_direction", "estimated_hours_per_unit", "duration_type",
        "duration_weeks", "canonical_key", "source_promise_uuid", "origin",
    ],
    "promises": [
        "angle_deg", "radius",
    ],
}

# Alembic revision id at head
EXPECTED_ALEMBIC_HEAD = "012_content_learning_pipeline"


# ---------------------------------------------------------------------------
# DB introspection
# ---------------------------------------------------------------------------

def connect(database_url: str):
    """Return a SQLAlchemy engine."""
    from sqlalchemy import create_engine
    return create_engine(database_url, echo=False)


def get_db_tables(engine) -> set[str]:
    from sqlalchemy import text
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        )).fetchall()
    return {r[0] for r in rows}


def get_db_views(engine) -> set[str]:
    from sqlalchemy import text
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT table_name FROM information_schema.views "
            "WHERE table_schema = 'public'"
        )).fetchall()
    return {r[0] for r in rows}


def get_table_columns(engine, table_name: str) -> list[str]:
    from sqlalchemy import text
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t "
            "ORDER BY ordinal_position"
        ), {"t": table_name}).fetchall()
    return [r[0] for r in rows]


def get_alembic_head(engine) -> str | None:
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT version_num FROM alembic_version LIMIT 1"
            )).fetchone()
        return row[0] if row else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Comparison logic
# ---------------------------------------------------------------------------

def audit_schema(engine) -> dict:
    """Compare live DB against expected schema. Returns a report dict."""
    live_tables = get_db_tables(engine)
    live_views = get_db_views(engine)
    alembic_head = get_alembic_head(engine)

    report: dict = {
        "alembic_head": {
            "expected": EXPECTED_ALEMBIC_HEAD,
            "actual": alembic_head,
            "match": alembic_head == EXPECTED_ALEMBIC_HEAD,
        },
        "tables": {},
        "views": {},
        "stale_columns": {},
        "summary": {"ok": 0, "drift": 0, "missing_tables": 0, "extra_tables": 0},
    }

    # --- Tables ---
    expected_table_names = set(EXPECTED_SCHEMA.keys())
    # Ignore alembic's own table
    live_tables_filtered = live_tables - {"alembic_version"}

    missing_tables = expected_table_names - live_tables_filtered
    extra_tables = live_tables_filtered - expected_table_names

    report["summary"]["missing_tables"] = len(missing_tables)
    report["summary"]["extra_tables"] = len(extra_tables)

    for t in sorted(missing_tables):
        report["tables"][t] = {"status": "MISSING", "expected_columns": EXPECTED_SCHEMA[t]}

    for t in sorted(extra_tables):
        cols = get_table_columns(engine, t)
        report["tables"][t] = {"status": "EXTRA (not in expected schema)", "actual_columns": cols}

    for table_name in sorted(expected_table_names & live_tables_filtered):
        expected_cols = set(EXPECTED_SCHEMA[table_name])
        actual_cols = set(get_table_columns(engine, table_name))

        missing_cols = sorted(expected_cols - actual_cols)
        extra_cols = sorted(actual_cols - expected_cols)

        if missing_cols or extra_cols:
            report["tables"][table_name] = {
                "status": "DRIFT",
                "missing_columns": missing_cols,
                "extra_columns": extra_cols,
            }
            report["summary"]["drift"] += 1
        else:
            report["tables"][table_name] = {"status": "OK"}
            report["summary"]["ok"] += 1

    # --- Views ---
    for view_name, expected_cols in EXPECTED_VIEWS.items():
        if view_name in live_views:
            actual_cols = set(get_table_columns(engine, view_name))
            expected_set = set(expected_cols)
            missing_cols = sorted(expected_set - actual_cols)
            extra_cols = sorted(actual_cols - expected_set)
            if missing_cols or extra_cols:
                report["views"][view_name] = {
                    "status": "DRIFT",
                    "missing_columns": missing_cols,
                    "extra_columns": extra_cols,
                }
            else:
                report["views"][view_name] = {"status": "OK"}
        else:
            report["views"][view_name] = {"status": "MISSING"}

    # --- Stale columns that MUST NOT exist ---
    for table_name, banned_cols in MUST_NOT_EXIST.items():
        if table_name not in live_tables_filtered:
            continue
        actual_cols = set(get_table_columns(engine, table_name))
        still_present = sorted(set(banned_cols) & actual_cols)
        if still_present:
            report["stale_columns"][table_name] = still_present

    return report


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_RESET = "\033[0m"
_BOLD = "\033[1m"


def print_report(report: dict) -> None:
    s = report["summary"]
    alembic = report["alembic_head"]
    has_drift = (
        s["drift"] > 0
        or s["missing_tables"] > 0
        or bool(report["stale_columns"])
        or not alembic["match"]
    )

    print(f"\n{_BOLD}=== Schema Drift Report ==={_RESET}\n")

    # Alembic head
    if alembic["match"]:
        print(f"  Alembic head: {_GREEN}{alembic['actual']}{_RESET} (matches expected)")
    else:
        print(f"  Alembic head: {_RED}{alembic['actual']}{_RESET}  (expected: {alembic['expected']})")

    print(f"\n  Tables OK: {_GREEN}{s['ok']}{_RESET}  |  Drift: {_RED if s['drift'] else _GREEN}{s['drift']}{_RESET}"
          f"  |  Missing: {_RED if s['missing_tables'] else _GREEN}{s['missing_tables']}{_RESET}"
          f"  |  Extra: {_YELLOW if s['extra_tables'] else _GREEN}{s['extra_tables']}{_RESET}")

    # Details for tables with issues
    for table_name, info in sorted(report["tables"].items()):
        status = info["status"]
        if status == "OK":
            continue

        if status == "MISSING":
            print(f"\n  {_RED}MISSING TABLE: {table_name}{_RESET}")
            print(f"    Expected columns: {', '.join(info['expected_columns'])}")
        elif status == "DRIFT":
            print(f"\n  {_YELLOW}DRIFT: {table_name}{_RESET}")
            if info.get("missing_columns"):
                print(f"    {_RED}Missing columns:{_RESET} {', '.join(info['missing_columns'])}")
            if info.get("extra_columns"):
                print(f"    {_CYAN}Extra columns:{_RESET}   {', '.join(info['extra_columns'])}")
        elif "EXTRA" in status:
            print(f"\n  {_CYAN}EXTRA TABLE: {table_name}{_RESET}")
            print(f"    Columns: {', '.join(info.get('actual_columns', []))}")

    # Views
    for view_name, info in sorted(report["views"].items()):
        if info["status"] == "OK":
            continue
        if info["status"] == "MISSING":
            print(f"\n  {_RED}MISSING VIEW: {view_name}{_RESET}")
        elif info["status"] == "DRIFT":
            print(f"\n  {_YELLOW}VIEW DRIFT: {view_name}{_RESET}")
            if info.get("missing_columns"):
                print(f"    {_RED}Missing columns:{_RESET} {', '.join(info['missing_columns'])}")
            if info.get("extra_columns"):
                print(f"    {_CYAN}Extra columns:{_RESET}   {', '.join(info['extra_columns'])}")

    # Stale columns
    if report["stale_columns"]:
        print(f"\n  {_RED}{_BOLD}STALE COLUMNS (should have been dropped by migrations):{_RESET}")
        for table_name, cols in sorted(report["stale_columns"].items()):
            print(f"    {table_name}: {_RED}{', '.join(cols)}{_RESET}")

    if has_drift:
        print(f"\n{_RED}{_BOLD}RESULT: DRIFT DETECTED{_RESET}\n")
    else:
        print(f"\n{_GREEN}{_BOLD}RESULT: SCHEMA OK{_RESET}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Check DB schema against expected migration head")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human-readable report")
    parser.add_argument("--database-url", help="Override database URL (default: from environment)")
    args = parser.parse_args()

    db_url = args.database_url or os.getenv("DATABASE_URL_STAGING") or os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: No database URL. Set DATABASE_URL_STAGING, DATABASE_URL, or pass --database-url.", file=sys.stderr)
        sys.exit(2)

    try:
        engine = connect(db_url)
        # Quick connectivity test
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        print(f"ERROR: Could not connect to database: {e}", file=sys.stderr)
        sys.exit(2)

    report = audit_schema(engine)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report)

    s = report["summary"]
    has_drift = (
        s["drift"] > 0
        or s["missing_tables"] > 0
        or bool(report["stale_columns"])
        or not report["alembic_head"]["match"]
    )
    sys.exit(1 if has_drift else 0)


if __name__ == "__main__":
    main()
