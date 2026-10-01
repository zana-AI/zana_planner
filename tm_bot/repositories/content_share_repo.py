"""Club shares of Library content, separate from an item's global visibility."""
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from db.postgres_db import get_db_session
from repositories.explore_repo import _youtube_video_id


class ContentShareRepository:
    def reserve_club_share(self, content_id: str, club_id: str, user_id: str) -> dict[str, Any]:
        """Validate and reserve a share before sending its Telegram message."""
        with get_db_session() as session:
            content = session.execute(text("""
                SELECT c.* FROM content c
                JOIN user_content uc ON uc.content_id = c.id AND uc.user_id = :user_id
                WHERE c.id = :content_id
            """), {"content_id": content_id, "user_id": user_id}).mappings().first()
            if not content:
                raise LookupError("Save this item to your Library first")
            content = dict(content)
            if content.get("visibility") == "club":
                raise PermissionError("Club-owned content cannot be reshared")
            metadata = content.get("metadata_json") or {}
            is_pdf = content.get("provider") == "telegram_pdf" or metadata.get("mime_type") == "application/pdf"
            video_id = _youtube_video_id(content) if content.get("provider") == "youtube" else None
            if not (is_pdf or video_id):
                raise ValueError("Only PDFs and YouTube videos can be shared")
            if is_pdf and str(content.get("owner_user_id") or "") != user_id and content.get("visibility") != "public":
                raise PermissionError("Only the PDF owner can share it")

            club = session.execute(text("""
                SELECT c.club_id, c.name, c.telegram_chat_id
                FROM clubs c JOIN club_members m ON m.club_id = c.club_id
                WHERE c.club_id = :club_id AND m.user_id = :user_id
                  AND m.status = 'active' AND c.status = 'active'
                  AND c.telegram_status IN ('ready', 'connected')
            """), {"club_id": club_id, "user_id": user_id}).mappings().first()
            if not club:
                raise PermissionError("Join this club before sharing with it")
            if not club["telegram_chat_id"]:
                raise ValueError("This club has no connected Telegram group")

            inserted = session.execute(text("""
                INSERT INTO content_club_shares (content_id, club_id, shared_by)
                VALUES (:content_id, :club_id, :user_id)
                ON CONFLICT DO NOTHING RETURNING content_id
            """), {"content_id": content_id, "club_id": club_id, "user_id": user_id}).first()
            if not inserted:
                existing = session.execute(text("""
                    SELECT status, created_at FROM content_club_shares
                    WHERE content_id = :content_id AND club_id = :club_id FOR UPDATE
                """), {"content_id": content_id, "club_id": club_id}).mappings().one()
                if existing["status"] == "sent":
                    return {"already_shared": True, "club_name": club["name"]}
                if existing["created_at"] > datetime.now(timezone.utc) - timedelta(minutes=5):
                    raise ValueError("This share is already being sent")
                session.execute(text("""
                    UPDATE content_club_shares SET shared_by = :user_id, created_at = now()
                    WHERE content_id = :content_id AND club_id = :club_id
                """), {"content_id": content_id, "club_id": club_id, "user_id": user_id})

            path = (f"/youtube-watch?video_id={video_id}&content_id={content_id}" if video_id
                    else f"/pdf-reader?content_id={content_id}")
            return {"already_shared": False, "club_name": club["name"],
                    "chat_id": str(club["telegram_chat_id"]),
                    "title": content.get("title") or "Untitled", "path": path}

    def finish_club_share(self, content_id: str, club_id: str, message_id: int) -> None:
        with get_db_session() as session:
            session.execute(text("""
                UPDATE content_club_shares SET status = 'sent', telegram_message_id = :message_id
                WHERE content_id = :content_id AND club_id = :club_id AND status = 'pending'
            """), {"content_id": content_id, "club_id": club_id, "message_id": message_id})

    def fail_club_share(self, content_id: str, club_id: str) -> None:
        with get_db_session() as session:
            session.execute(text("""
                DELETE FROM content_club_shares
                WHERE content_id = :content_id AND club_id = :club_id AND status = 'pending'
            """), {"content_id": content_id, "club_id": club_id})

    def list_for_member(self, user_id: str, club_id: str | None = None,
                        q: str | None = None, limit: int = 30, offset: int = 0) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"user_id": user_id, "limit": limit, "offset": offset}
        where = ["m.user_id = :user_id", "m.status = 'active'", "s.status = 'sent'",
                 "cl.status = 'active'"]
        if club_id:
            where.append("s.club_id = :club_id")
            params["club_id"] = club_id
        if q and q.strip():
            where.append("(c.title ILIKE :q OR c.author_channel ILIKE :q OR cl.name ILIKE :q)")
            params["q"] = f"%{q.strip()}%"
        with get_db_session() as session:
            rows = session.execute(text(f"""
                SELECT c.id AS content_id, c.title, c.description, c.provider, c.content_type,
                       c.language, c.duration_seconds, c.estimated_read_seconds, c.thumbnail_url,
                       c.author_channel, c.metadata_json, c.original_url, c.canonical_url,
                       s.club_id, cl.name AS club_name, s.shared_by, s.created_at,
                       (s.shared_by = :user_id OR cl.owner_user_id = :user_id) AS can_remove,
                       uc.status AS saved_status
                FROM content_club_shares s
                JOIN clubs cl ON cl.club_id = s.club_id
                JOIN club_members m ON m.club_id = s.club_id
                JOIN content c ON c.id = s.content_id
                LEFT JOIN user_content uc ON uc.content_id = c.id AND uc.user_id = :user_id
                WHERE {' AND '.join(where)}
                ORDER BY s.created_at DESC, c.id
                LIMIT :limit OFFSET :offset
            """), params).mappings().all()
        items = []
        for row in rows:
            item = dict(row)
            video_id = _youtube_video_id(item) if item.get("provider") == "youtube" else None
            item["path"] = (f"/youtube-watch?video_id={video_id}&content_id={item['content_id']}" if video_id
                            else f"/pdf-reader?content_id={item['content_id']}")
            items.append(item)
        return items

    def remove_club_share(self, content_id: str, club_id: str, user_id: str) -> bool:
        """The original sharer or club owner can remove an item from the shelf."""
        with get_db_session() as session:
            row = session.execute(text("""
                DELETE FROM content_club_shares s USING clubs c
                WHERE s.content_id = :content_id AND s.club_id = :club_id
                  AND c.club_id = s.club_id
                  AND (s.shared_by = :user_id OR c.owner_user_id = :user_id)
                RETURNING s.content_id
            """), {"content_id": content_id, "club_id": club_id, "user_id": user_id}).first()
        return bool(row)
