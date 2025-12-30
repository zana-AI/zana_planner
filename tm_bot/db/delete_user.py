# zana_planner/tm_bot/db/delete_user.py
"""
Script to delete all data for a user from the system.
This includes SQLite database records and file system artifacts.
"""
import os
import sqlite3
import shutil
import argparse
from pathlib import Path
from db.sqlite_db import resolve_db_path, connection_for_root


def delete_user_from_sqlite(root_dir: str, user_id: str) -> None:
    """Delete all user data from SQLite database."""
    db_path = resolve_db_path(root_dir)
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
    
    with connection_for_root(root_dir) as conn:
        user = str(user_id)
        
        # Delete in order respecting foreign key constraints
        # (Foreign keys are enabled via PRAGMA foreign_keys=ON)
        
        # Delete sessions (references promises)
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user,))
        
        # Delete actions (references promises)
        conn.execute("DELETE FROM actions WHERE user_id = ?", (user,))
        
        # Delete promise_events (references promises)
        conn.execute("DELETE FROM promise_events WHERE user_id = ?", (user,))
        
        # Delete promise_aliases (references promises)
        conn.execute("DELETE FROM promise_aliases WHERE user_id = ?", (user,))
        
        # Delete promises
        conn.execute("DELETE FROM promises WHERE user_id = ?", (user,))
        
        # Delete user settings
        conn.execute("DELETE FROM users WHERE user_id = ?", (user,))
        
        # Delete legacy imports
        conn.execute("DELETE FROM legacy_imports WHERE user_id = ?", (user,))
        
        conn.commit()
        print(f"Deleted all SQLite data for user {user_id}")


def delete_user_directory(root_dir: str, user_id: str) -> None:
    """Delete user's directory and all files in it."""
    user_dir = os.path.join(root_dir, str(user_id))
    if os.path.exists(user_dir):
        shutil.rmtree(user_dir)
        print(f"Deleted user directory: {user_dir}")
    else:
        print(f"User directory not found: {user_dir}")


def purge_user(root_dir: str, user_id: str) -> None:
    """
    Delete all data for a user. Irreversible.
    
    Args:
        root_dir: Path to USERS_DATA_DIR
        user_id: User ID to delete (as string or int)
    """
    user_id_str = str(user_id)
    print(f"Purging all data for user {user_id_str}...")
    
    # Delete from SQLite
    delete_user_from_sqlite(root_dir, user_id_str)
    
    # Delete user directory (contains nightly_state.json and any other files)
    delete_user_directory(root_dir, user_id_str)
    
    print(f"✓ Completed purging user {user_id_str}")


def main(argv=None):
    import os
    from db.export import _default_data_dir
    
    parser = argparse.ArgumentParser(
        description="Delete all data for a user from Zana bot. IRREVERSIBLE."
    )
    parser.add_argument(
        "--data-dir",
        default=_default_data_dir(),
        help="Path to USERS_DATA_DIR (default: env USERS_DATA_DIR/ROOT_DIR)"
    )
    parser.add_argument(
        "--user",
        required=True,
        help="User ID to delete (TEXT)"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Skip confirmation prompt (use with caution)"
    )
    args = parser.parse_args(argv)
    
    data_dir = os.path.abspath(args.data_dir)
    user_id = str(args.user)
    
    if not args.confirm:
        response = input(
            f"WARNING: This will PERMANENTLY delete ALL data for user {user_id}.\n"
            f"This includes promises, actions, sessions, settings, and all files.\n"
            f"Type 'DELETE {user_id}' to confirm: "
        )
        if response != f"DELETE {user_id}":
            print("Cancelled.")
            return 1
    
    purge_user(data_dir, user_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())