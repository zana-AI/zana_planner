# zana_planner/tm_bot/db/delete_user.py
"""
Script to delete all data for a user from the system.
This includes PostgreSQL database records and file system artifacts.
"""
import os
import shutil
import argparse
from pathlib import Path
from sqlalchemy import text
from db.postgres_db import get_db_session


def delete_user_from_postgres(user_id: str) -> None:
    """Delete all user data from PostgreSQL database."""
    user = str(user_id)

    with get_db_session() as session:
        # Delete dependent rows using promise_uuid subquery
        session.execute(
            text("""
                DELETE FROM promise_reminders
                WHERE promise_uuid IN (SELECT promise_uuid FROM promises WHERE user_id = :user_id)
            """),
            {"user_id": user},
        )
        session.execute(
            text("""
                DELETE FROM promise_schedule_weekly_slots
                WHERE promise_uuid IN (SELECT promise_uuid FROM promises WHERE user_id = :user_id)
            """),
            {"user_id": user},
        )
        session.execute(
            text("DELETE FROM sessions WHERE user_id = :user_id"),
            {"user_id": user},
        )
        session.execute(
            text("DELETE FROM actions WHERE user_id = :user_id"),
            {"user_id": user},
        )
        session.execute(
            text("DELETE FROM distraction_events WHERE user_id = :user_id"),
            {"user_id": user},
        )
        session.execute(
            text("DELETE FROM promise_weekly_reviews WHERE user_id = :user_id"),
            {"user_id": user},
        )
        session.execute(
            text("DELETE FROM promise_events WHERE user_id = :user_id"),
            {"user_id": user},
        )
        session.execute(
            text("DELETE FROM promise_aliases WHERE user_id = :user_id"),
            {"user_id": user},
        )
        session.execute(
            text("DELETE FROM promise_instances WHERE user_id = :user_id"),
            {"user_id": user},
        )
        session.execute(
            text("DELETE FROM promises WHERE user_id = :user_id"),
            {"user_id": user},
        )
        session.execute(
            text("DELETE FROM promise_templates WHERE created_by_user_id = :user_id"),
            {"user_id": user},
        )
        session.execute(
            text("DELETE FROM promise_suggestions WHERE from_user_id = :user_id OR to_user_id = :user_id"),
            {"user_id": user},
        )
        session.execute(
            text("DELETE FROM user_relationships WHERE source_user_id = :user_id OR target_user_id = :user_id"),
            {"user_id": user},
        )
        session.execute(
            text("DELETE FROM legacy_imports WHERE user_id = :user_id"),
            {"user_id": user},
        )
        session.execute(
            text("DELETE FROM users WHERE user_id = :user_id"),
            {"user_id": user},
        )

    print(f"Deleted all PostgreSQL data for user {user_id}")


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
    
    # Delete from PostgreSQL
    delete_user_from_postgres(user_id_str)
    
    # Delete user directory (contains nightly_state.json and any other files)
    delete_user_directory(root_dir, user_id_str)
    
    print(f"✓ Completed purging user {user_id_str}")


def main(argv=None):
    import os
    from db.export import _default_data_dir
    
    parser = argparse.ArgumentParser(
        description="Delete all data for a user from Xaana bot. IRREVERSIBLE."
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