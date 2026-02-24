import pytest

from sqlalchemy import text

from db.postgres_db import get_db_session
from models.models import UserSettings
from repositories.settings_repo import SettingsRepository

pytestmark = [pytest.mark.repo, pytest.mark.requires_postgres]


@pytest.mark.repo
def test_settings_repo_defaults_when_missing(tmp_path):
    repo = SettingsRepository()
    s = repo.get_settings(user_id=1)
    assert s.timezone
    assert s.nightly_hh is not None
    assert s.nightly_mm is not None
    assert s.language


@pytest.mark.repo
def test_settings_repo_save_and_load_roundtrip(tmp_path):
    repo = SettingsRepository()
    user_id = 42
    settings = UserSettings(
        user_id=str(user_id),
        timezone="UTC",
        nightly_hh=23,
        nightly_mm=15,
        language="fr",
        voice_mode="enabled",
    )
    repo.save_settings(settings)

    loaded = repo.get_settings(user_id)
    assert loaded.user_id == str(user_id)
    assert loaded.timezone == "UTC"
    assert loaded.nightly_hh == 23
    assert loaded.nightly_mm == 15
    assert loaded.language == "fr"
    assert loaded.voice_mode == "enabled"


@pytest.mark.repo
def test_mark_chat_not_found_sets_disabled_timezone(tmp_path):
    repo = SettingsRepository()
    user_id = 99
    settings = UserSettings(user_id=str(user_id), timezone="Europe/Paris")
    repo.save_settings(settings)

    repo.mark_chat_not_found(user_id)

    with get_db_session() as session:
        row = session.execute(
            text("SELECT timezone FROM users WHERE user_id = :uid"),
            {"uid": str(user_id)},
        ).mappings().fetchone()

    assert row is not None
    assert row["timezone"] == "DISABLED"


@pytest.mark.repo
def test_mark_chat_not_found_idempotent(tmp_path):
    repo = SettingsRepository()
    user_id = 100
    settings = UserSettings(user_id=str(user_id), timezone="UTC")
    repo.save_settings(settings)

    # Calling twice must not raise
    repo.mark_chat_not_found(user_id)
    repo.mark_chat_not_found(user_id)

    with get_db_session() as session:
        row = session.execute(
            text("SELECT timezone FROM users WHERE user_id = :uid"),
            {"uid": str(user_id)},
        ).mappings().fetchone()

    assert row["timezone"] == "DISABLED"
