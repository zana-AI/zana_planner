#!/usr/bin/env python3
"""
One-off: apply schema changes that Alembic would do (007: actions.notes, 008: drop angle_deg/radius).
Use when a Postgres DB has alembic_version ahead of actual schema (e.g. stamped without running migrations).
Reads DATABASE_URL or DATABASE_URL_STAGING from env.

Usage:
  export DATABASE_URL_STAGING="postgresql://..."
  python scripts/sync_postgres_schema_once.py
"""
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text

def get_url():
    url = os.environ.get("DATABASE_URL_STAGING") or os.environ.get("DATABASE_URL")
    if not url:
        print("Set DATABASE_URL_STAGING or DATABASE_URL", file=sys.stderr)
        sys.exit(1)
    return url

def main():
    url = get_url()
    engine = create_engine(url)
    with engine.connect() as conn:
        # 007: actions.notes
        r = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'actions' AND column_name = 'notes'
        """))
        if r.fetchone() is None:
            conn.execute(text("ALTER TABLE actions ADD COLUMN notes TEXT"))
            conn.commit()
            print("Added actions.notes")
        else:
            print("actions.notes already exists")

        # 008: drop view first (it depends on angle_deg/radius), then drop columns, then recreate view
        r = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'promises' AND column_name = 'angle_deg'
        """))
        if r.fetchone():
            conn.execute(text("DROP VIEW IF EXISTS promises_with_type"))
            conn.execute(text("ALTER TABLE promises DROP COLUMN IF EXISTS angle_deg"))
            conn.execute(text("ALTER TABLE promises DROP COLUMN IF EXISTS radius"))
            conn.commit()
            print("Dropped promises_with_type view and promises.angle_deg / radius")
        else:
            print("promises.angle_deg already dropped")

        # Recreate view to match current schema (no angle_deg/radius)
        conn.execute(text("DROP VIEW IF EXISTS promises_with_type"))
        conn.execute(text("""
            CREATE VIEW promises_with_type AS
            SELECT
                promise_uuid, user_id, current_id, text, hours_per_week, recurring,
                start_date, end_date, is_deleted, visibility, description,
                created_at_utc, updated_at_utc,
                CASE WHEN hours_per_week <= 0 THEN 1 ELSE 0 END AS is_check_based,
                CASE WHEN hours_per_week > 0 THEN 1 ELSE 0 END AS is_time_based,
                CASE WHEN hours_per_week <= 0 THEN 'check_based' ELSE 'time_based' END AS promise_type
            FROM promises
        """))
        conn.commit()
        print("Recreated promises_with_type view")

    print("Schema sync done.")

if __name__ == "__main__":
    main()
