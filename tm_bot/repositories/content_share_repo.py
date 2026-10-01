"""Club shares of Library content, separate from an item's global visibility."""
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
import json

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

            path = (f"/youtube-watch?video_id={video_id}&content_id={content_id}&club_id={club_id}" if video_id
                    else f"/pdf-reader?content_id={content_id}&club_id={club_id}")
            thumbnail_storage_uri = None
            if is_pdf:
                thumbnail = session.execute(text("""
                    SELECT storage_uri FROM content_asset
                    WHERE content_id = :content_id AND asset_type = 'pdf_thumbnail'
                    ORDER BY created_at DESC LIMIT 1
                """), {"content_id": content_id}).mappings().first()
                thumbnail_storage_uri = thumbnail["storage_uri"] if thumbnail else None
            return {"already_shared": False, "club_name": club["name"],
                    "chat_id": str(club["telegram_chat_id"]),
                    "title": content.get("title") or "Untitled", "path": path,
                    "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg" if video_id else None,
                    "thumbnail_storage_uri": thumbnail_storage_uri}

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
            item["path"] = (f"/youtube-watch?video_id={video_id}&content_id={item['content_id']}&club_id={item['club_id']}" if video_id
                            else f"/pdf-reader?content_id={item['content_id']}&club_id={item['club_id']}")
            items.append(item)
        return items

    def is_active_member_of_share(self, content_id: str, club_id: str, user_id: str) -> bool:
        """A club URL alone does not grant access to members' reading activity."""
        with get_db_session() as session:
            return bool(session.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM content_club_shares s
                    JOIN clubs c ON c.club_id = s.club_id AND c.status = 'active'
                    JOIN club_members m ON m.club_id = s.club_id
                    WHERE s.content_id = :content_id AND s.club_id = :club_id
                      AND s.status = 'sent' AND m.user_id = :user_id AND m.status = 'active'
                )
            """), {"content_id": content_id, "club_id": club_id, "user_id": user_id}).scalar())

    def list_activity(self, content_id: str, club_id: str) -> list[dict[str, Any]]:
        """Progress and annotation counts for active members of one shared item."""
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT m.user_id, COALESCE(NULLIF(u.first_name, ''), NULLIF(u.username, ''), 'Member') AS name,
                       COALESCE(uc.progress_ratio, 0) AS progress_ratio,
                       COALESCE(uc.total_consumed_seconds, 0) AS total_consumed_seconds,
                       uc.last_interaction_at, COALESCE(h.highlight_count, 0) AS highlight_count,
                       COALESCE(v.annotation_count, 0) AS annotation_count
                FROM club_members m
                JOIN content_club_shares s ON s.club_id = m.club_id AND s.content_id = :content_id AND s.status = 'sent'
                JOIN users u ON u.user_id = m.user_id
                LEFT JOIN user_content uc ON uc.user_id = m.user_id AND uc.content_id = :content_id
                LEFT JOIN (
                    SELECT user_id, COUNT(*) AS highlight_count FROM content_highlight
                    WHERE content_id = :content_id AND club_visible = true GROUP BY user_id
                ) h ON h.user_id = m.user_id
                LEFT JOIN (
                    SELECT user_id, COUNT(*) AS annotation_count FROM club_video_annotation
                    WHERE content_id = :content_id AND club_id = :club_id GROUP BY user_id
                ) v ON v.user_id = m.user_id
                WHERE m.club_id = :club_id AND m.status = 'active'
                ORDER BY COALESCE(uc.progress_ratio, 0) DESC, name ASC
                LIMIT 200
            """), {"content_id": content_id, "club_id": club_id}).mappings().all()
        return [dict(row) for row in rows]

    def list_club_highlights(self, content_id: str, club_id: str, asset_id: str,
                             viewer_user_id: str, as_user_id: str | None = None) -> list[dict[str, Any]]:
        """Club-visible PDF marks, optionally narrowed to one active member."""
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT h.id, h.user_id, h.content_id, h.asset_id, h.page_index, h.rects_json,
                       h.selected_text, h.note, h.color, h.created_at, h.updated_at, h.club_visible,
                       COALESCE(NULLIF(u.first_name, ''), NULLIF(u.username, ''), 'Member') AS author_name
                FROM content_highlight h
                JOIN content_club_shares s ON s.content_id = h.content_id AND s.club_id = :club_id AND s.status = 'sent'
                JOIN club_members m ON m.user_id = h.user_id AND m.club_id = :club_id AND m.status = 'active'
                JOIN users u ON u.user_id = h.user_id
                WHERE h.content_id = :content_id AND h.asset_id = :asset_id
                  AND (h.club_visible = true OR h.user_id = :viewer_user_id)
                  AND (:as_user_id IS NULL OR h.user_id = :as_user_id)
                ORDER BY h.page_index ASC, h.created_at ASC
                LIMIT 1000
            """), {"content_id": content_id, "club_id": club_id, "asset_id": asset_id,
                   "viewer_user_id": viewer_user_id, "as_user_id": as_user_id}).mappings().all()
        items = []
        for row in rows:
            item = dict(row)
            rects = item.get("rects_json")
            item["rects_json"] = rects if isinstance(rects, list) else json.loads(rects) if isinstance(rects, str) else []
            item["is_mine"] = str(item["user_id"]) == viewer_user_id
            item["is_teacher_author"] = False
            items.append(item)
        return items

    def list_video_annotations(self, content_id: str, club_id: str, user_id: str) -> list[dict[str, Any]]:
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT a.id, a.user_id, a.position_seconds, a.body, a.created_at,
                       COALESCE(NULLIF(u.first_name, ''), NULLIF(u.username, ''), 'Member') AS author_name
                FROM club_video_annotation a
                JOIN content_club_shares s ON s.content_id = a.content_id AND s.club_id = a.club_id AND s.status = 'sent'
                JOIN club_members m ON m.user_id = a.user_id AND m.club_id = a.club_id AND m.status = 'active'
                JOIN users u ON u.user_id = a.user_id
                WHERE a.content_id = :content_id AND a.club_id = :club_id
                ORDER BY a.position_seconds ASC, a.created_at ASC
                LIMIT 500
            """), {"content_id": content_id, "club_id": club_id}).mappings().all()
        return [{**dict(row), "is_mine": str(row["user_id"]) == user_id} for row in rows]

    def add_video_annotation(self, content_id: str, club_id: str, user_id: str,
                             position_seconds: int, body: str) -> str:
        annotation_id = str(uuid4())
        with get_db_session() as session:
            row = session.execute(text("""
                INSERT INTO club_video_annotation (id, content_id, club_id, user_id, position_seconds, body)
                SELECT :id, s.content_id, s.club_id, :user_id, :position_seconds, :body
                FROM content_club_shares s
                JOIN club_members m ON m.club_id = s.club_id AND m.user_id = :user_id AND m.status = 'active'
                JOIN clubs c ON c.club_id = s.club_id AND c.status = 'active'
                WHERE s.content_id = :content_id AND s.club_id = :club_id AND s.status = 'sent'
                RETURNING id
            """), {"id": annotation_id, "content_id": content_id, "club_id": club_id,
                   "user_id": user_id, "position_seconds": position_seconds, "body": body}).first()
        if not row:
            raise PermissionError("This item is not shared with your club")
        return annotation_id

    def remove_video_annotation(self, content_id: str, club_id: str, user_id: str, annotation_id: str) -> bool:
        with get_db_session() as session:
            row = session.execute(text("""
                DELETE FROM club_video_annotation
                WHERE id = :id AND content_id = :content_id AND club_id = :club_id AND user_id = :user_id
                RETURNING id
            """), {"id": annotation_id, "content_id": content_id, "club_id": club_id,
                   "user_id": user_id}).first()
        return bool(row)

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
