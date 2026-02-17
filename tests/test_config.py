"""
Shared test configuration and helpers.

Single source of truth for test isolation on a shared PostgreSQL DB:
- unique_user_id(): deterministic per-test user IDs (counter-based) for reproducible runs.
- ensure_users_exist(): create users in the `users` table so FK constraints pass (social/repo tests).
"""

# Base for generated user IDs. Keeps repo/integration test users in a known range.
REPO_TEST_USER_BASE = 10_000_000

_test_user_counter = 0


def unique_user_id() -> int:
    """
    Return a user_id unique within this test run (counter-based).
    Same test order => same IDs => reproducible tests.
    """
    global _test_user_counter
    _test_user_counter += 1
    return REPO_TEST_USER_BASE + _test_user_counter


def ensure_users_exist(*user_ids: int) -> None:
    """Insert users into the users table so FK constraints are satisfied (e.g. user_relationships)."""
    from models.models import UserSettings
    from repositories.settings_repo import SettingsRepository

    settings_repo = SettingsRepository()
    for uid in user_ids:
        settings_repo.save_settings(UserSettings(user_id=str(uid)))
