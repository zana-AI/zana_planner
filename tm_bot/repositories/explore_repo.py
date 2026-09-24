"""Read-only discovery projections. Never expose Library owners or club members."""

from sqlalchemy import bindparam, text

from db.postgres_db import get_db_session


class ExploreRepository:
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
                SELECT metadata_json->>'video_id' AS video_id, canonical_url, duration_seconds
                FROM content WHERE duration_seconds > 0 AND (
                    metadata_json->>'video_id' IN :ids OR canonical_url IN :urls)
                ORDER BY updated_at ASC
            """).bindparams(bindparam("ids", expanding=True), bindparam("urls", expanding=True)),
                {"ids": video_ids, "urls": list(urls)}).mappings()
            for row in durations:
                video_id = row["video_id"] or urls.get(row["canonical_url"])
                if video_id in result:
                    result[video_id]["duration_seconds"] = float(row["duration_seconds"])
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
