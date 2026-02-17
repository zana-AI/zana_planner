"""
Shared test configuration and helpers.

Single source of truth for test isolation on a shared PostgreSQL DB:
- unique_user_id(): unique per test; run-unique base so IDs are not reused across pytest runs.
- ensure_users_exist(): create users in the `users` table so FK constraints pass (social/repo tests).
"""

import random

# Base for generated user IDs. Run-unique offset so each pytest run uses a different range (avoids leftover data).
REPO_TEST_USER_BASE = 10_000_000

_run_base: int | None = None
_test_user_counter = 0


def unique_user_id() -> int:
    """
    Return a user_id unique within this test run.
    Base is chosen once per run (random) so IDs are not reused across runs and DB stays isolated.
    """
    global _run_base, _test_user_counter
    if _run_base is None:
        _run_base = REPO_TEST_USER_BASE + random.randint(0, 89_000_000)
    _test_user_counter += 1
    return _run_base + _test_user_counter


def ensure_users_exist(*user_ids: int) -> None:
    """Insert users into the users table so FK constraints are satisfied (e.g. user_relationships)."""
    from models.models import UserSettings
    from repositories.settings_repo import SettingsRepository

    settings_repo = SettingsRepository()
    for uid in user_ids:
        settings_repo.save_settings(UserSettings(user_id=str(uid)))
