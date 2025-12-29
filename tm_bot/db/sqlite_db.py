from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterator, Optional


def resolve_db_path(root_dir: str) -> str:
    """
    Resolve SQLite DB location.

    Plan default: USERS_DATA_DIR/zana.db
    Runtime passes root_dir (normally USERS_DATA_DIR). Prefer the passed root_dir
    to keep tests/dev isolated.
    """
    # Allow explicit override for deployments where the data dir root is not writable
    # (common with Docker bind mounts owned by root).
    explicit = os.getenv("SQLITE_PATH")
    if explicit:
        p = str(explicit).strip().strip('"').strip("'")
        return os.path.abspath(os.path.expanduser(p))

    base = root_dir or os.getenv("USERS_DATA_DIR") or os.getenv("ROOT_DIR") or "."
    base = os.path.abspath(os.path.expanduser(str(base).strip().strip('"').strip("'")))
    return os.path.join(base, "zana.db")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def date_to_iso(d: Optional[date]) -> Optional[str]:
    """Convert date or datetime to ISO date string (YYYY-MM-DD)."""
    if d is None:
        return None
    # Handle both date and datetime objects, always store as date-only
    if isinstance(d, datetime):
        return d.date().isoformat()
    return d.isoformat()


def date_from_iso(s: Optional[str]) -> Optional[date]:
    """Parse ISO date string, handling both YYYY-MM-DD and YYYY-MM-DDTHH:MM:SS formats."""
    if not s:
        return None
    try:
        # Handle datetime format (e.g., "2025-12-29T00:00:00")
        if 'T' in s:
            # Strip timezone info if present
            dt_str = s.replace('Z', '+00:00')
            if '+' in dt_str[10:]:  # Check after date part
                dt_str = dt_str[:dt_str.index('+', 10)]
            elif dt_str.endswith('+00:00'):
                dt_str = dt_str[:-6]
            return datetime.fromisoformat(dt_str).date()
        return date.fromisoformat(s)
    except Exception:
        return None


def _parse_iso_datetime(s: str) -> datetime:
    # Accept both "...Z" and "...+00:00"
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def dt_to_utc_iso(dt: Optional[datetime], assume_local_tz: bool = True) -> Optional[str]:
    """
    Convert datetime to UTC ISO8601 string.

    If dt is naive and assume_local_tz is True, treat it as server local time.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        if assume_local_tz:
            local_tz = datetime.now().astimezone().tzinfo
            dt = dt.replace(tzinfo=local_tz)
        else:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def dt_from_utc_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = _parse_iso_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def dt_utc_iso_to_local_naive(s: Optional[str]) -> Optional[datetime]:
    """
    Parse a stored UTC ISO timestamp and return a naive datetime in server local time.

    This keeps backward compatibility with the existing codebase which mostly
    uses naive datetimes (and compares them without tz awareness).
    """
    dt = dt_from_utc_iso(s)
    if not dt:
        return None
    local_tz = datetime.now().astimezone().tzinfo
    return dt.astimezone(local_tz).replace(tzinfo=None)


def json_compat(obj: Any) -> Any:
    """
    Convert dataclasses/enums/datetime/date into JSON-serializable structures.
    Used for snapshot_json in promise_events.
    """
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, datetime):
        return dt_to_utc_iso(obj) or obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    # Enums: store their value when possible
    if hasattr(obj, "value"):
        try:
            return obj.value
        except Exception:
            pass
    if is_dataclass(obj):
        return {k: json_compat(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): json_compat(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [json_compat(v) for v in obj]
    return str(obj)


def resolve_promise_uuid(conn: sqlite3.Connection, user_id: str, promise_id: Optional[str]) -> Optional[str]:
    pid = (promise_id or "").strip().upper()
    if not pid:
        return None
    row = conn.execute(
        "SELECT promise_uuid FROM promises WHERE user_id = ? AND current_id = ? LIMIT 1;",
        (user_id, pid),
    ).fetchone()
    if row and row["promise_uuid"]:
        return str(row["promise_uuid"])
    row = conn.execute(
        "SELECT promise_uuid FROM promise_aliases WHERE user_id = ? AND alias_id = ? LIMIT 1;",
        (user_id, pid),
    ).fetchone()
    if row and row["promise_uuid"]:
        return str(row["promise_uuid"])
    return None


def connect(db_path: str) -> sqlite3.Connection:
    parent = os.path.dirname(db_path) or "."
    os.makedirs(parent, exist_ok=True)
    try:
        conn = sqlite3.connect(db_path, timeout=30, isolation_level=None)  # autocommit; manage transactions explicitly
    except sqlite3.OperationalError as e:
        # Add context to make permission/path issues obvious in logs.
        writable = None
        try:
            writable = os.access(parent, os.W_OK)
        except Exception:
            writable = None
        raise sqlite3.OperationalError(
            f"{e} (db_path={db_path!r}, parent={parent!r}, parent_exists={os.path.exists(parent)}, parent_writable={writable})"
        ) from e
    conn.row_factory = sqlite3.Row
    _apply_pragmas(conn)
    ensure_schema(conn)
    return conn


@contextmanager
def connection_for_root(root_dir: str) -> Iterator[sqlite3.Connection]:
    conn = connect(resolve_db_path(root_dir))
    try:
        yield conn
    finally:
        conn.close()


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON;")
    # WAL improves concurrency even in single-writer scenarios
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        # Some environments may restrict this; continue with defaults
        pass
    conn.execute("PRAGMA synchronous=NORMAL;")


SCHEMA_VERSION = 1


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at_utc TEXT NOT NULL
        );
        """
    )

    row = conn.execute("SELECT MAX(version) AS v FROM schema_version;").fetchone()
    current = int(row["v"] or 0)
    if current >= SCHEMA_VERSION:
        return

    with conn:
        _apply_v1(conn)
        conn.execute(
            "INSERT INTO schema_version(version, applied_at_utc) VALUES (?, ?);",
            (SCHEMA_VERSION, utc_now_iso()),
        )


def _apply_v1(conn: sqlite3.Connection) -> None:
    # Note: storing IDs uppercased in repos keeps uniqueness sane without NOCASE schema.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT PRIMARY KEY,
            timezone TEXT NOT NULL,
            nightly_hh INTEGER NOT NULL,
            nightly_mm INTEGER NOT NULL,
            language TEXT NOT NULL,
            voice_mode TEXT NULL,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS promises (
            promise_uuid TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            current_id TEXT NOT NULL,
            text TEXT NOT NULL,
            hours_per_week REAL NOT NULL,
            recurring INTEGER NOT NULL,
            start_date TEXT NULL,
            end_date TEXT NULL,
            angle_deg INTEGER NOT NULL,
            radius INTEGER NOT NULL,
            is_deleted INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            UNIQUE(user_id, current_id)
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS promise_aliases (
            user_id TEXT NOT NULL,
            alias_id TEXT NOT NULL,
            promise_uuid TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY(user_id, alias_id),
            FOREIGN KEY(promise_uuid) REFERENCES promises(promise_uuid)
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS promise_events (
            event_uuid TEXT PRIMARY KEY,
            promise_uuid TEXT NOT NULL,
            user_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            at_utc TEXT NOT NULL,
            snapshot_json TEXT NOT NULL,
            FOREIGN KEY(promise_uuid) REFERENCES promises(promise_uuid)
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS actions (
            action_uuid TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            promise_uuid TEXT NULL,
            promise_id_text TEXT NOT NULL,
            action_type TEXT NOT NULL,
            time_spent_hours REAL NOT NULL,
            at_utc TEXT NOT NULL,
            FOREIGN KEY(promise_uuid) REFERENCES promises(promise_uuid)
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            promise_uuid TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at_utc TEXT NOT NULL,
            ended_at_utc TEXT NULL,
            paused_seconds_total INTEGER NOT NULL,
            last_state_change_at_utc TEXT NULL,
            message_id INTEGER NULL,
            chat_id INTEGER NULL,
            FOREIGN KEY(promise_uuid) REFERENCES promises(promise_uuid)
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS legacy_imports (
            user_id TEXT NOT NULL,
            source TEXT NOT NULL,
            source_mtime_utc TEXT NULL,
            imported_at_utc TEXT NOT NULL,
            PRIMARY KEY(user_id, source)
        );
        """
    )

    # Indexes
    conn.execute("CREATE INDEX IF NOT EXISTS ix_promises_user ON promises(user_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_actions_user_at ON actions(user_id, at_utc);")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_actions_user_promise_at ON actions(user_id, promise_uuid, at_utc);")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_sessions_user_status ON sessions(user_id, status);")

