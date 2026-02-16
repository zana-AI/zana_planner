#!/usr/bin/env python3
import argparse
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

# Import from sqlite_db to avoid duplicating DB filename logic
try:
    from tm_bot.db.sqlite_db import get_db_filename
except ImportError:
    # Fallback for when running as standalone script
    def get_db_filename() -> str:
        return os.getenv("DB_FILENAME", "zana.db")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _db_path(data_dir: str) -> str:
    return os.path.join(data_dir, get_db_filename())


def _connect_ro(db_path: str) -> Optional[sqlite3.Connection]:
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


def _list_users(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        """
        SELECT user_id FROM (
            SELECT user_id FROM promises
            UNION
            SELECT user_id FROM actions
            UNION
            SELECT user_id FROM sessions
            UNION
            SELECT user_id FROM users
        ) u
        ORDER BY user_id ASC;
        """
    ).fetchall()
    return [str(r["user_id"]) for r in rows if r["user_id"] is not None]


def _count_distinct(conn: sqlite3.Connection, sql: str, params: Tuple = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def compute_stats_sql(data_dir: str) -> Dict:
    """
    Privacy-friendly usage stats from SQLite.

    The DB file is expected at: <data_dir>/<DB_FILENAME> (defaults to zana.db if DB_FILENAME not set)
    """
    db_path = _db_path(data_dir)
    conn = _connect_ro(db_path)
    now = _utc_now()

    if not conn:
        return {
            "total_users": 0,
            "users_with_promises": 0,
            "users_with_actions": 0,
            "active_last_7_days": 0,
            "active_last_30_days": 0,
            "active_users_by_actions_mtime": {k: 0 for k in ["7d", "30d", "90d", "365d"]},
            "new_users_by_dir_mtime": {k: 0 for k in ["7d", "30d"]},
            "details": [],
            "data_dir": os.path.abspath(data_dir),
            "generated_at": _utc_iso(now),
        }

    with conn:
        users = _list_users(conn)
        total_users = len(users)

        users_with_promises = _count_distinct(
            conn,
            "SELECT COUNT(DISTINCT user_id) FROM promises WHERE is_deleted = 0;",
        )
        users_with_actions = _count_distinct(
            conn,
            "SELECT COUNT(DISTINCT user_id) FROM actions;",
        )

        windows = [7, 30, 90, 365]
        active_counts: Dict[str, int] = {}
        for d in windows:
            threshold = _utc_iso(now - timedelta(days=d))
            active_counts[f"{d}d"] = _count_distinct(
                conn,
                "SELECT COUNT(DISTINCT user_id) FROM actions WHERE at_utc >= ?;",
                (threshold,),
            )

        # Best-effort "new users": first seen in any table within window
        new_counts: Dict[str, int] = {}
        for d in [7, 30]:
            threshold = _utc_iso(now - timedelta(days=d))
            new_counts[f"{d}d"] = _count_distinct(
                conn,
                """
                SELECT COUNT(*) FROM (
                    SELECT user_id, MIN(ts) AS first_seen
                    FROM (
                        SELECT user_id, created_at_utc AS ts FROM users
                        UNION ALL
                        SELECT user_id, created_at_utc AS ts FROM promises
                        UNION ALL
                        SELECT user_id, at_utc AS ts FROM actions
                        UNION ALL
                        SELECT user_id, started_at_utc AS ts FROM sessions
                    ) t
                    WHERE ts IS NOT NULL AND ts <> ''
                    GROUP BY user_id
                ) u
                WHERE u.first_seen >= ?;
                """,
                (threshold,),
            )

        # Per-user detail
        details: List[Dict] = []
        for uid in users:
            has_promises = _count_distinct(
                conn,
                "SELECT COUNT(*) FROM promises WHERE user_id = ? AND is_deleted = 0 LIMIT 1;",
                (uid,),
            ) > 0
            has_actions = _count_distinct(
                conn,
                "SELECT COUNT(*) FROM actions WHERE user_id = ? LIMIT 1;",
                (uid,),
            ) > 0
            last_row = conn.execute(
                "SELECT MAX(at_utc) AS m FROM actions WHERE user_id = ?;",
                (uid,),
            ).fetchone()
            last_activity = str(last_row["m"]) if last_row and last_row["m"] else None
            details.append(
                {
                    "user_id": int(uid) if str(uid).isdigit() else uid,
                    "has_promises": has_promises,
                    "has_actions": has_actions,
                    "last_activity": last_activity,
                }
            )

    return {
        "total_users": total_users,
        "users_with_promises": users_with_promises,
        "users_with_actions": users_with_actions,
        "active_last_7_days": active_counts["7d"],
        "active_last_30_days": active_counts["30d"],
        "active_users_by_actions_mtime": active_counts,
        "new_users_by_dir_mtime": new_counts,
        "details": details,
        "data_dir": os.path.abspath(data_dir),
        "generated_at": _utc_iso(now),
    }


def get_version_stats(data_dir: str) -> Dict[str, int]:
    """
    Get lightweight aggregate stats for version command (SQLite).
    Returns only: total_users, total_promises, actions_24h.
    Prefer get_version_stats_postgres() when using PostgreSQL.
    """
    db_path = _db_path(data_dir)
    conn = _connect_ro(db_path)
    now = _utc_now()

    if not conn:
        return {
            "total_users": 0,
            "total_promises": 0,
            "actions_24h": 0,
        }

    with conn:
        # Total distinct users
        total_users = _count_distinct(
            conn,
            "SELECT COUNT(DISTINCT user_id) FROM users;"
        )
        
        # Total active promises
        total_promises = _count_distinct(
            conn,
            "SELECT COUNT(*) FROM promises WHERE is_deleted = 0;"
        )
        
        # Actions in last 24 hours
        threshold = _utc_iso(now - timedelta(hours=24))
        actions_24h = _count_distinct(
            conn,
            "SELECT COUNT(*) FROM actions WHERE at_utc >= ?;",
            (threshold,)
        )
        
        return {
            "total_users": total_users,
            "total_promises": total_promises,
            "actions_24h": actions_24h,
        }


def get_version_stats_postgres() -> Dict[str, int]:
    """
    Get lightweight aggregate stats for version command from PostgreSQL.
    Returns: total_users, total_promises, actions_24h.
    """
    from sqlalchemy import text
    from db.postgres_db import get_db_session, dt_to_utc_iso

    result = {"total_users": 0, "total_promises": 0, "actions_24h": 0}
    try:
        # 24h ago in UTC ISO (same format as at_utc in actions)
        threshold_dt = datetime.now(timezone.utc) - timedelta(hours=24)
        threshold = dt_to_utc_iso(threshold_dt, assume_local_tz=False) or threshold_dt.isoformat()

        with get_db_session() as session:
            row = session.execute(
                text("SELECT COUNT(DISTINCT user_id) FROM users;")
            ).fetchone()
            result["total_users"] = int(row[0] or 0) if row else 0

            row = session.execute(
                text("SELECT COUNT(*) FROM promises WHERE is_deleted = 0;")
            ).fetchone()
            result["total_promises"] = int(row[0] or 0) if row else 0

            row = session.execute(
                text("SELECT COUNT(*) FROM actions WHERE at_utc >= :threshold;"),
                {"threshold": threshold},
            ).fetchone()
            result["actions_24h"] = int(row[0] or 0) if row else 0
    except Exception:
        pass
    return result


def main():
    parser = argparse.ArgumentParser(description="Privacy-friendly usage stats for Xaana Planner bot.")
    parser.add_argument("data_dir", help="Path to USERS_DATA_DIR")
    parser.add_argument("--threshold-bytes", type=int, default=12,
                        help="Minimum bytes to consider a CSV as non-empty (default: 12)")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a table")
    args = parser.parse_args()
    report = compute_stats_sql(args.data_dir)
    # Keep legacy arg in output (informational only)
    report["threshold_bytes"] = args.threshold_bytes

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    # pretty print
    print(f"== Xaana Planner usage stats ==")
    print(f"Data dir:    ***{report['data_dir'][-19:]}")
    print(f"Generated:   {report['generated_at']}")
    print()
    print(f"Total users: {report['total_users']}")
    print(f"With promises: {report['users_with_promises']}")
    print(f"With actions:  {report['users_with_actions']}")
    print()
    print("Active users (by actions.csv mtime):")
    for k in ["7d", "30d", "90d", "365d"]:
        print(f"  last {k:>4}: {report['active_users_by_actions_mtime'][k]}")
    print()
    print("New users (by folder mtime):")
    for k in ["7d", "30d"]:
        print(f"  last {k:>4}: {report['new_users_by_dir_mtime'][k]}")
    print()
    print("(Computed from SQLite; threshold-bytes is legacy-only.)")

if __name__ == "__main__":
    main()
