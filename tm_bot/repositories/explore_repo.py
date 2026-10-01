"""Explore projections and explicit, owner-authorized content sharing."""

import json
import math
import re
from urllib.parse import parse_qs, urlparse

from sqlalchemy import bindparam, text

from db.postgres_db import get_db_session


def _youtube_video_id(content: dict) -> str | None:
    metadata = content.get("metadata_json") or {}
    candidate = metadata.get("video_id")
    if candidate and re.fullmatch(r"[A-Za-z0-9_-]{11}", str(candidate)):
        return str(candidate)
    for raw in (content.get("canonical_url"), content.get("original_url")):
        if not raw:
            continue
        parsed = urlparse(str(raw))
        host = (parsed.hostname or "").lower()
        if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            candidate = parse_qs(parsed.query).get("v", [None])[0]
            if not candidate and parsed.path.startswith(("/shorts/", "/embed/")):
                candidate = parsed.path.split("/")[2]
        elif host in {"youtu.be", "www.youtu.be"}:
            candidate = parsed.path.strip("/").split("/")[0]
        else:
            continue
        if candidate and re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
            return candidate
    return None


def _already_in_explore(document: dict, content_id: str, video_id: str | None) -> bool:
    for category in document.get("categories", []):
        for topic in category.get("topics", []):
            for item in topic.get("items", []):
                ref = item.get("native_ref") or ""
                matches = (item.get("content_id") == content_id or
                           bool(re.search(r"[?&]content_id=" + re.escape(content_id) + r"(?:[&#]|$)", ref)) or
                           bool(video_id and re.search(r"[?&]video_id=" + re.escape(video_id) + r"(?:[&#]|$)", ref)))
                if matches and not (category.get("published", True) and topic.get("published", True)
                                    and item.get("published", True)):
                    raise PermissionError("This item is hidden from Explore")
                if matches:
                    return True
    return False


_LANGUAGE_NAMES = {"en": "English", "fr": "French", "fa": "Persian"}


def _add_explore_item(document: dict, content: dict, path: str, video_id: str | None,
                      language: str | None, level: str | None) -> None:
    code = (language or "").lower().split("-")[0]
    category = next((row for row in document["categories"] if row.get("language") == code and code), None)
    if category is None:
        category_id = f"language-{code}" if code else "other"
        category = next((row for row in document["categories"] if row.get("id") == category_id), None)
        if category is None:
            category = {"id": category_id, "title": _LANGUAGE_NAMES.get(code, code.upper() if code else "Other"),
                        "language": code or None, "order": 90, "published": True, "topics": []}
            document["categories"].append(category)
    if not category.get("published", True):
        raise PermissionError("This subject is hidden from Explore")
    topic_id = "watch" if video_id else "read"
    topic = next((row for row in category["topics"] if row.get("id") == topic_id), None)
    if topic is None:
        topic = {"id": topic_id, "title": "Watch" if video_id else "Read",
                 "order": 20 if video_id else 30, "published": True, "items": []}
        category["topics"].append(topic)
    if not topic.get("published", True):
        raise PermissionError("This content type is hidden from Explore")
    content_id = str(content["id"])
    entry = {"id": f"shared-{content_id}", "title": content.get("title") or "Untitled",
             "type": "video" if video_id else "pdf", "order": max((int(row.get("order", 0)) for row in topic["items"]), default=0) + 10,
             "published": True, "native_ref": path, "content_id": content_id,
             "description": (content.get("description") or "")[:240] or None,
             "creator": content.get("author_channel"), "language": code or None, "level": level,
             "image": content.get("thumbnail_url") or (f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg" if video_id else None)}
    duration = float(content.get("duration_seconds") or 0)
    if video_id and math.isfinite(duration) and duration > 0:
        entry["duration_seconds"] = duration
    if not video_id and content.get("estimated_read_seconds") and int(content["estimated_read_seconds"]) > 0:
        entry["estimated_read_seconds"] = int(content["estimated_read_seconds"])
    topic["items"].append(entry)


class ExploreRepository:
    def saved_content(self, user_id: str) -> tuple[set[str], set[str]]:
        """The viewer's Library identities, including alternate URLs for a video."""
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT c.id, c.canonical_url, c.original_url, c.metadata_json
                FROM user_content uc JOIN content c ON c.id = uc.content_id
                WHERE uc.user_id = :user_id
            """), {"user_id": str(user_id)}).mappings().all()
        content_ids, video_ids = set(), set()
        for row in rows:
            content = dict(row)
            content_ids.add(str(content["id"]))
            if isinstance(content.get("metadata_json"), str):
                content["metadata_json"] = json.loads(content["metadata_json"])
            video_id = _youtube_video_id(content)
            if video_id:
                video_ids.add(video_id)
        return content_ids, video_ids

    def share_library_content(self, content_id: str, user_id: str, destination: str,
                              language: str | None = None, level: str | None = None) -> dict:
        """Make an owned PDF linkable, or explicitly list a saved item in Explore.

        The catalog row is locked so two taps cannot create duplicate cards. A
        visibility change and catalog insertion commit in the same transaction.
        """
        with get_db_session() as session:
            content = session.execute(text("SELECT * FROM content WHERE id=:id"), {"id": content_id}).mappings().one_or_none()
            if not content:
                raise LookupError("Content not found")
            content = dict(content)
            saved = session.execute(text("SELECT EXISTS(SELECT 1 FROM user_content WHERE user_id=:uid AND content_id=:id)"),
                                    {"uid": user_id, "id": content_id}).scalar()
            if not saved:
                raise PermissionError("Save this item to your Library first")
            metadata = content.get("metadata_json") or {}
            is_pdf = content.get("provider") == "telegram_pdf" or metadata.get("mime_type") == "application/pdf"
            video_id = _youtube_video_id(content) if content.get("provider") == "youtube" else None
            if not (is_pdf or video_id):
                raise ValueError("Only PDFs and YouTube videos can be shared")
            if is_pdf and str(content.get("owner_user_id") or "") != user_id and content.get("visibility") != "public":
                raise PermissionError("Only the PDF owner can share it")
            if content.get("visibility") == "club":
                raise PermissionError("Club content cannot be shared publicly")

            path = (f"/youtube-watch?video_id={video_id}" if video_id
                    else f"/pdf-reader?content_id={content_id}")
            document = None
            already = False
            if destination == "explore":
                document = session.execute(text("SELECT document FROM explore_catalog WHERE id='main' FOR UPDATE")).scalar_one_or_none()
                if not isinstance(document, dict):
                    raise LookupError("Explore catalog unavailable")
                already = _already_in_explore(document, content_id, video_id)

            if content.get("visibility") != "public":
                session.execute(text("UPDATE content SET visibility='public', updated_at=now() WHERE id=:id"), {"id": content_id})

            if document is not None and not already:
                selected_language = (language or content.get("language") or "").lower().split("-")[0] or None
                selected_level = level or metadata.get("level")
                if selected_language or selected_level:
                    updated_metadata = dict(metadata)
                    if selected_level:
                        updated_metadata["level"] = selected_level
                    session.execute(text("""UPDATE content SET language=COALESCE(:language, language),
                        metadata_json=CAST(:metadata AS jsonb), updated_at=now() WHERE id=:id"""),
                        {"id": content_id, "language": selected_language,
                         "metadata": json.dumps(updated_metadata, ensure_ascii=False)})
                _add_explore_item(document, content, path, video_id, selected_language, selected_level)
                session.execute(text("UPDATE explore_catalog SET document=CAST(:document AS jsonb), updated_at=now() WHERE id='main'"),
                                {"document": json.dumps(document, ensure_ascii=False)})
        return {"path": path, "already_in_explore": already}

    def video_metadata(self, video_ids: list[str]) -> dict:
        if not video_ids:
            return {}
        urls = {f"https://www.youtube.com/watch?v={video_id}": video_id for video_id in video_ids}
        result = {video_id: {"subtitles_available": False} for video_id in video_ids}
        with get_db_session() as session:
            transcripts = session.execute(text("""
                SELECT video_id, language,
                    cue_count > 0 AND CASE WHEN jsonb_typeof(cues) = 'array'
                        THEN jsonb_array_length(cues) > 0 ELSE FALSE END AS ready
                FROM video_transcript WHERE video_id IN :ids
            """).bindparams(bindparam("ids", expanding=True)), {"ids": video_ids}).mappings()
            for row in transcripts:
                result[row["video_id"]].update(
                    subtitles_available=bool(row["ready"]), subtitle_language=row["language"]
                )
            # Transcript duration is the last cue's end, NOT the video length.
            # Read only public-video metadata, never private user_content state.
            durations = session.execute(text("""
                SELECT metadata_json->>'video_id' AS video_id, canonical_url, duration_seconds,
                       language, metadata_json->>'level' AS level
                FROM content WHERE visibility='public' AND (
                    metadata_json->>'video_id' IN :ids OR canonical_url IN :urls)
                ORDER BY updated_at ASC
            """).bindparams(bindparam("ids", expanding=True), bindparam("urls", expanding=True)),
                {"ids": video_ids, "urls": list(urls)}).mappings()
            for row in durations:
                video_id = row["video_id"] or urls.get(row["canonical_url"])
                if video_id in result:
                    if row["duration_seconds"] and row["duration_seconds"] > 0:
                        result[video_id]["duration_seconds"] = float(row["duration_seconds"])
                    if row["language"]:
                        result[video_id]["language"] = row["language"]
                    if row["level"]:
                        result[video_id]["level"] = row["level"]
        return result

    def clubs(self, user_id: int) -> list[dict]:
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT c.club_id, c.name, c.description,
                    EXISTS (SELECT 1 FROM club_members m WHERE m.club_id = c.club_id
                        AND m.user_id = :user_id AND m.status = 'active') AS joined
                FROM clubs c
                WHERE COALESCE(c.status, 'active') = 'active' AND (
                    c.visibility = 'public' OR EXISTS (
                        SELECT 1 FROM club_members m WHERE m.club_id = c.club_id
                            AND m.user_id = :user_id AND m.status = 'active'))
                ORDER BY joined DESC, c.name, c.club_id
                LIMIT 100
            """), {"user_id": str(user_id)}).mappings().all()
        return [dict(row) for row in rows]
