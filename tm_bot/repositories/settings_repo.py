from db.legacy_importer import ensure_imported
from db.sqlite_db import connection_for_root, utc_now_iso
from models.models import UserSettings


class SettingsRepository:
    """SQLite-backed settings repository (with lazy import from settings.yaml)."""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def get_settings(self, user_id: int) -> UserSettings:
        user = str(user_id)
        with connection_for_root(self.root_dir) as conn:
            ensure_imported(conn, self.root_dir, user, "settings")
            row = conn.execute(
                """
                SELECT timezone, nightly_hh, nightly_mm, language, voice_mode
                FROM user_settings
                WHERE user_id = ?
                LIMIT 1;
                """,
                (user,),
            ).fetchone()

        if not row:
            return UserSettings(user_id=user)

        return UserSettings(
            user_id=user,
            timezone=str(row["timezone"] or "Europe/Paris"),
            nightly_hh=int(row["nightly_hh"] or 22),
            nightly_mm=int(row["nightly_mm"] or 0),
            language=str(row["language"] or "en"),
            voice_mode=row["voice_mode"],
        )

    def save_settings(self, settings: UserSettings) -> None:
        user = str(settings.user_id)
        now = utc_now_iso()
        with connection_for_root(self.root_dir) as conn:
            ensure_imported(conn, self.root_dir, user, "settings")
            conn.execute(
                """
                INSERT OR REPLACE INTO user_settings(
                    user_id, timezone, nightly_hh, nightly_mm, language, voice_mode,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    user,
                    settings.timezone or "Europe/Paris",
                    int(settings.nightly_hh or 22),
                    int(settings.nightly_mm or 0),
                    settings.language or "en",
                    settings.voice_mode,
                    now,
                    now,
                ),
            )
