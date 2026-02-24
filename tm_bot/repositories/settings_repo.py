from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso, dt_from_utc_iso, dt_to_utc_iso
from models.models import UserSettings


class SettingsRepository:
    """PostgreSQL-backed settings repository."""

    def __init__(self) -> None:
        pass

    def get_settings(self, user_id: int) -> UserSettings:
        user = str(user_id)
        with get_db_session() as session:
            # Use .mappings() so rows are dict-like (row["timezone"]) even for text() queries.
            row = session.execute(
                text("""
                    SELECT timezone, nightly_hh, nightly_mm, language, voice_mode, 
                           first_name, username, last_seen_utc
                    FROM users
                    WHERE user_id = :user_id
                    LIMIT 1;
                """),
                {"user_id": user},
            ).mappings().fetchone()

        if not row:
            return UserSettings(user_id=user)

        return UserSettings(
            user_id=user,
            timezone=str(row["timezone"] or "DEFAULT"),
            nightly_hh=int(row["nightly_hh"] or 22),
            nightly_mm=int(row["nightly_mm"] or 0),
            language=str(row["language"] or "en"),
            voice_mode=row["voice_mode"],
            first_name=row["first_name"],
            username=row["username"],
            last_seen=dt_from_utc_iso(row["last_seen_utc"]) if row["last_seen_utc"] else None,
        )

    def mark_chat_not_found(self, user_id: int) -> None:
        user = str(user_id)
        now = utc_now_iso()
        with get_db_session() as session:
            session.execute(
                text("""
                    UPDATE users
                    SET chat_not_found = TRUE, updated_at_utc = :updated_at_utc
                    WHERE user_id = :user_id;
                """),
                {"user_id": user, "updated_at_utc": now},
            )

    def save_settings(self, settings: UserSettings) -> None:
        user = str(settings.user_id)
        now = utc_now_iso()
        with get_db_session() as session:
            session.execute(
                text("""
                    INSERT INTO users(
                        user_id, timezone, nightly_hh, nightly_mm, language, voice_mode,
                        first_name, username, last_seen_utc,
                        created_at_utc, updated_at_utc
                    ) VALUES (
                        :user_id, :timezone, :nightly_hh, :nightly_mm, :language, :voice_mode,
                        :first_name, :username, :last_seen_utc,
                        :created_at_utc, :updated_at_utc
                    )
                    ON CONFLICT (user_id) DO UPDATE SET
                        timezone = EXCLUDED.timezone,
                        nightly_hh = EXCLUDED.nightly_hh,
                        nightly_mm = EXCLUDED.nightly_mm,
                        language = EXCLUDED.language,
                        voice_mode = EXCLUDED.voice_mode,
                        first_name = EXCLUDED.first_name,
                        username = EXCLUDED.username,
                        last_seen_utc = EXCLUDED.last_seen_utc,
                        updated_at_utc = EXCLUDED.updated_at_utc;
                """),
                {
                    "user_id": user,
                    "timezone": settings.timezone or "DEFAULT",
                    "nightly_hh": int(settings.nightly_hh or 22),
                    "nightly_mm": int(settings.nightly_mm or 0),
                    "language": settings.language or "en",
                    "voice_mode": settings.voice_mode,
                    "first_name": settings.first_name,
                    "username": settings.username,
                    "last_seen_utc": dt_to_utc_iso(settings.last_seen) if settings.last_seen else None,
                    "created_at_utc": now,
                    "updated_at_utc": now,
                },
            )
