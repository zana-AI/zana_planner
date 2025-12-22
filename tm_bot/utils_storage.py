import os


def create_user_directory(root_dir, user_id: int) -> bool:
    """
    Create a directory for the user if it doesn't exist.

    Legacy versions initialized CSV/YAML files here. After migrating to SQLite,
    we keep only the directory (used for a few non-SQL artifacts like
    nightly_state.json) and do not create any CSV/YAML placeholders.
    """
    user_dir = os.path.join(root_dir, str(user_id))
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)
        return True
    return False

def initialize_files(user_dir: str) -> None:
    """
    No-op kept for backwards compatibility.

    Storage initialization is now handled by SQLite schema bootstrap in
    `tm_bot/db/sqlite_db.py`.
    """
    return None