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


SCHEMA_VERSION = 3


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
    
    with conn:
        # Apply migrations in order
        if current < 1:
            _apply_v1(conn)
            conn.execute(
                "INSERT INTO schema_version(version, applied_at_utc) VALUES (?, ?);",
                (1, utc_now_iso()),
            )
        if current < 2:
            _apply_v2(conn)
            conn.execute(
                "INSERT INTO schema_version(version, applied_at_utc) VALUES (?, ?);",
                (2, utc_now_iso()),
            )
        if current < 3:
            _apply_v3(conn)
            conn.execute(
                "INSERT INTO schema_version(version, applied_at_utc) VALUES (?, ?);",
                (3, utc_now_iso()),
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


def _apply_v2(conn: sqlite3.Connection) -> None:
    """Apply schema version 2 migrations: conversations table and user_settings extensions."""
    # Add conversations table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            chat_id TEXT,
            message_id INTEGER,
            message_type TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES user_settings(user_id)
        );
        """
    )
    
    # Add index for conversations
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_conversations_user_time ON conversations(user_id, created_at_utc DESC);"
    )
    
    # Add new columns to user_settings (if they don't exist)
    # SQLite doesn't support ALTER TABLE ADD COLUMN IF NOT EXISTS, so we check first
    existing_columns = [row[1] for row in conn.execute("PRAGMA table_info(user_settings);").fetchall()]
    
    if "first_name" not in existing_columns:
        conn.execute("ALTER TABLE user_settings ADD COLUMN first_name TEXT NULL;")
    
    if "username" not in existing_columns:
        conn.execute("ALTER TABLE user_settings ADD COLUMN username TEXT NULL;")
    
    if "last_seen_utc" not in existing_columns:
        conn.execute("ALTER TABLE user_settings ADD COLUMN last_seen_utc TEXT NULL;")


def _apply_v3(conn: sqlite3.Connection) -> None:
    """Apply schema version 3 migrations: social features, rename user_settings to users."""
    
    # Step 1: Rename user_settings to users if it exists and users doesn't
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
    
    if "user_settings" in tables and "users" not in tables:
        # Rename the table
        conn.execute("ALTER TABLE user_settings RENAME TO users;")
        
        # Update foreign key in conversations table if it exists
        if "conversations" in tables:
            # SQLite doesn't support ALTER TABLE to change FK, so we recreate the table
            # First, get all data
            conversations_data = conn.execute("SELECT * FROM conversations;").fetchall()
            columns = [desc[0] for desc in conn.execute("PRAGMA table_info(conversations);").fetchall()]
            
            # Drop old table
            conn.execute("DROP TABLE conversations;")
            
            # Recreate with correct FK
            conn.execute(
                """
                CREATE TABLE conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    chat_id TEXT,
                    message_id INTEGER,
                    message_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );
                """
            )
            
            # Restore data if any
            if conversations_data and columns:
                # Build insert statement
                placeholders = ", ".join(["?"] * len(columns))
                col_names = ", ".join(columns)
                for row in conversations_data:
                    values = tuple(row)
                    conn.execute(f"INSERT INTO conversations({col_names}) VALUES ({placeholders});", values)
            
            # Recreate index
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_conversations_user_time ON conversations(user_id, created_at_utc DESC);"
            )
    
    # Step 2: Ensure users table has all required columns
    existing_columns = [row[1] for row in conn.execute("PRAGMA table_info(users);").fetchall()]
    
    # Social/profile columns
    new_columns = [
        ("last_name", "TEXT NULL"),
        ("display_name", "TEXT NULL"),
        ("is_private", "INTEGER NOT NULL DEFAULT 0"),
        ("default_promise_visibility", "TEXT NOT NULL DEFAULT 'private'"),
        ("avatar_file_id", "TEXT NULL"),
        ("avatar_file_unique_id", "TEXT NULL"),
        ("avatar_path", "TEXT NULL"),
        ("avatar_updated_at_utc", "TEXT NULL"),
        ("avatar_checked_at_utc", "TEXT NULL"),
        ("avatar_visibility", "TEXT NOT NULL DEFAULT 'public'"),
    ]
    
    for col_name, col_def in new_columns:
        if col_name not in existing_columns:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def};")
    
    # Step 3: Add visibility column to promises
    promise_columns = [row[1] for row in conn.execute("PRAGMA table_info(promises);").fetchall()]
    if "visibility" not in promise_columns:
        conn.execute("ALTER TABLE promises ADD COLUMN visibility TEXT NOT NULL DEFAULT 'private';")
        # Backfill existing rows
        conn.execute("UPDATE promises SET visibility = 'private' WHERE visibility IS NULL;")
    
    # Step 4: Create user_follows table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_follows (
            follower_user_id TEXT NOT NULL,
            followee_user_id TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            unfollowed_at_utc TEXT NULL,
            notifications_enabled INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (follower_user_id, followee_user_id),
            CHECK (follower_user_id <> followee_user_id),
            FOREIGN KEY (follower_user_id) REFERENCES users(user_id),
            FOREIGN KEY (followee_user_id) REFERENCES users(user_id)
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_follows_followee ON user_follows(followee_user_id, created_at_utc DESC);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_follows_follower ON user_follows(follower_user_id, created_at_utc DESC);"
    )
    
    # Step 5: Create user_blocks table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_blocks (
            blocker_user_id TEXT NOT NULL,
            blocked_user_id TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            lifted_at_utc TEXT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            reason TEXT NULL,
            PRIMARY KEY (blocker_user_id, blocked_user_id),
            CHECK (blocker_user_id <> blocked_user_id),
            FOREIGN KEY (blocker_user_id) REFERENCES users(user_id),
            FOREIGN KEY (blocked_user_id) REFERENCES users(user_id)
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_blocks_blocker ON user_blocks(blocker_user_id, created_at_utc DESC);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_blocks_blocked ON user_blocks(blocked_user_id, created_at_utc DESC);"
    )
    
    # Step 6: Create user_mutes table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_mutes (
            muter_user_id TEXT NOT NULL,
            muted_user_id TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            lifted_at_utc TEXT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            scope TEXT NOT NULL DEFAULT 'all',
            PRIMARY KEY (muter_user_id, muted_user_id),
            CHECK (muter_user_id <> muted_user_id),
            FOREIGN KEY (muter_user_id) REFERENCES users(user_id),
            FOREIGN KEY (muted_user_id) REFERENCES users(user_id)
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_mutes_muter ON user_mutes(muter_user_id, created_at_utc DESC);"
    )
    
    # Step 7: Create clubs table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS clubs (
            club_id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NULL,
            visibility TEXT NOT NULL DEFAULT 'private',
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            FOREIGN KEY (owner_user_id) REFERENCES users(user_id)
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_clubs_owner ON clubs(owner_user_id, created_at_utc DESC);"
    )
    
    # Step 8: Create club_members table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS club_members (
            club_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            status TEXT NOT NULL DEFAULT 'active',
            joined_at_utc TEXT NOT NULL,
            left_at_utc TEXT NULL,
            PRIMARY KEY (club_id, user_id),
            FOREIGN KEY (club_id) REFERENCES clubs(club_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_club_members_user ON club_members(user_id, club_id);"
    )
    
    # Step 9: Create promise_club_shares table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS promise_club_shares (
            promise_uuid TEXT NOT NULL,
            club_id TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (promise_uuid, club_id),
            FOREIGN KEY (promise_uuid) REFERENCES promises(promise_uuid),
            FOREIGN KEY (club_id) REFERENCES clubs(club_id)
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_promise_club_shares_promise ON promise_club_shares(promise_uuid);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_promise_club_shares_club ON promise_club_shares(club_id);"
    )
    
    # Step 10: Create milestones table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS milestones (
            milestone_uuid TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            milestone_type TEXT NOT NULL,
            value_int INTEGER NULL,
            value_text TEXT NULL,
            promise_uuid TEXT NULL,
            trigger_action_uuid TEXT NULL,
            trigger_session_id TEXT NULL,
            computed_at_utc TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (promise_uuid) REFERENCES promises(promise_uuid),
            FOREIGN KEY (trigger_action_uuid) REFERENCES actions(action_uuid),
            FOREIGN KEY (trigger_session_id) REFERENCES sessions(session_id)
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_milestones_user ON milestones(user_id, computed_at_utc DESC);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_milestones_promise ON milestones(promise_uuid, computed_at_utc DESC);"
    )
    
    # Step 11: Create feed_items table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feed_items (
            feed_item_uuid TEXT PRIMARY KEY,
            actor_user_id TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            visibility TEXT NOT NULL,
            title TEXT NULL,
            body TEXT NULL,
            action_uuid TEXT NULL,
            session_id TEXT NULL,
            milestone_uuid TEXT NULL,
            promise_uuid TEXT NULL,
            context_json TEXT NOT NULL DEFAULT '{}',
            dedupe_key TEXT NULL,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (actor_user_id) REFERENCES users(user_id),
            FOREIGN KEY (action_uuid) REFERENCES actions(action_uuid),
            FOREIGN KEY (session_id) REFERENCES sessions(session_id),
            FOREIGN KEY (milestone_uuid) REFERENCES milestones(milestone_uuid),
            FOREIGN KEY (promise_uuid) REFERENCES promises(promise_uuid)
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_feed_items_actor_time ON feed_items(actor_user_id, created_at_utc DESC);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_feed_items_time ON feed_items(created_at_utc DESC);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_feed_items_promise ON feed_items(promise_uuid, created_at_utc DESC);"
    )
    
    # Step 12: Create feed_reactions table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feed_reactions (
            reaction_uuid TEXT PRIMARY KEY,
            feed_item_uuid TEXT NOT NULL,
            actor_user_id TEXT NOT NULL,
            reaction_type TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            UNIQUE(feed_item_uuid, actor_user_id, reaction_type),
            FOREIGN KEY (feed_item_uuid) REFERENCES feed_items(feed_item_uuid),
            FOREIGN KEY (actor_user_id) REFERENCES users(user_id)
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_reactions_feed_time ON feed_reactions(feed_item_uuid, created_at_utc DESC);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_reactions_actor ON feed_reactions(actor_user_id, created_at_utc DESC);"
    )
    
    # Step 13: Create social_events table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS social_events (
            event_uuid TEXT PRIMARY KEY,
            actor_user_id TEXT NULL,
            event_type TEXT NOT NULL,
            subject_type TEXT NULL,
            subject_id TEXT NULL,
            object_type TEXT NULL,
            object_id TEXT NULL,
            created_at_utc TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (actor_user_id) REFERENCES users(user_id)
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_social_events_actor ON social_events(actor_user_id, created_at_utc DESC);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_social_events_type ON social_events(event_type, created_at_utc DESC);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_social_events_time ON social_events(created_at_utc DESC);"
    )

