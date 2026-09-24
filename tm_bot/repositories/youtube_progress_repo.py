"""Atomic, retry-safe watch reports using the existing consumption-event IDs."""
import json
import math
import uuid

from sqlalchemy import text
from db.postgres_db import get_db_session, utc_now_iso, resolve_promise_uuid


def coverage(ranges, duration):
    """Unique watched seconds, not the furthest playhead or number of reports."""
    merged = []
    for start, end in sorted(ranges):
        start, end = max(0, start), min(duration, end) if duration else end
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged, sum(end - start for start, end in merged)


class YoutubeProgressRepository:
    def get_progress(self, user_id, content_id, duration):
        with get_db_session() as session:
            ranges = session.execute(text("""
                SELECT start_position,end_position FROM content_consumption_event
                WHERE user_id=:uid AND content_id=:cid AND position_unit='seconds'
            """), {"uid": str(user_id), "cid": str(content_id)}).all()
        merged, _ = coverage(ranges, duration)
        return {"duration_seconds": duration, "segments": merged}

    def record(self, user_id, content_id, video_id, report_id, segments,
               duration=None, promise_id="", client="youtube_viewer"):
        user_id, content_id = str(user_id), str(content_id)
        now = utc_now_iso()
        event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"youtube:{user_id}:{content_id}:{report_id}"))
        with get_db_session() as session:
            # Serialize reports for this user/item; event and rollup commit together.
            session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                            {"key": f"watch:{user_id}:{content_id}"})
            params = {"uid": user_id, "cid": content_id, "now": now}
            if session.execute(text("SELECT 1 FROM content_consumption_event WHERE id=:id"),
                               {"id": event_id}).first():
                return {"ok": True, "duplicate": True}
            row = session.execute(text("SELECT duration_seconds FROM content WHERE id=:cid"), params).first()
            if row is None:
                raise ValueError("Content not found")
            duration = row[0] or duration
            if duration and not row[0]:
                session.execute(text("UPDATE content SET duration_seconds=:duration WHERE id=:cid AND (duration_seconds IS NULL OR duration_seconds<=0)"),
                                {**params, "duration": duration})
            session.execute(text("""
                INSERT INTO user_content (id,user_id,content_id,status,added_at)
                VALUES (:id,:uid,:cid,'saved',:now) ON CONFLICT (user_id,content_id) DO NOTHING
            """), {**params, "id": str(uuid.uuid4())})
            for index, (start, end) in enumerate(segments):
                session.execute(text("""
                    INSERT INTO content_consumption_event
                      (id,user_id,content_id,event_type,start_position,end_position,position_unit,client,created_at)
                    VALUES (:id,:uid,:cid,'consume',:start,:end,'seconds',:client,:now)
                """), {**params, "id": event_id if index == 0 else str(uuid.uuid5(uuid.UUID(event_id), str(index))),
                       "start": start, "end": end, "client": client})
            ranges = session.execute(text("""
                SELECT start_position,end_position FROM content_consumption_event
                WHERE user_id=:uid AND content_id=:cid AND position_unit='seconds'
            """), params).all()
            merged, watched = coverage(ranges, duration)
            ratio = min(1, watched / duration) if duration else 0
            buckets = [0] * 120
            if duration:
                previous = session.execute(text("SELECT buckets FROM user_content_rollup WHERE user_id=:uid AND content_id=:cid"), params).scalar()
                if isinstance(previous, list) and len(previous) == 120:
                    buckets = previous
                for start, end in merged:
                    for i in range(max(0, int(start / duration * 120)), min(120, math.ceil(end / duration * 120))):
                        buckets[i] = max(1, buckets[i])
                session.execute(text("""
                    INSERT INTO user_content_rollup (user_id,content_id,bucket_count,buckets,updated_at)
                    VALUES (:uid,:cid,120,CAST(:buckets AS jsonb),:now)
                    ON CONFLICT (user_id,content_id) DO UPDATE
                    SET buckets=EXCLUDED.buckets,bucket_count=120,updated_at=EXCLUDED.updated_at
                """), {**params, "buckets": json.dumps(buckets)})
            # Never downgrade a prior explicit completion, or unarchive an item.
            result = session.execute(text("""
                UPDATE user_content SET last_interaction_at=:now,last_position=:position,position_unit='seconds',
                  progress_ratio=GREATEST(COALESCE(progress_ratio,0),:ratio),
                  total_consumed_seconds=GREATEST(COALESCE(total_consumed_seconds,0),:total),
                  status=CASE WHEN status IN ('archived','completed') THEN status
                    WHEN GREATEST(COALESCE(progress_ratio,0),:ratio)>=0.95 THEN 'completed' ELSE 'in_progress' END,
                  completed_at=CASE WHEN GREATEST(COALESCE(progress_ratio,0),:ratio)>=0.95
                    THEN COALESCE(completed_at,:now) ELSE completed_at END
                WHERE user_id=:uid AND content_id=:cid RETURNING progress_ratio,status
            """), {**params, "position": segments[-1][1], "ratio": ratio,
                   "total": sum(max(0, end-start) for start, end in ranges)}).mappings().one()
            watched_delta = sum(end-start for start, end in segments)
            promise_uuid = resolve_promise_uuid(session, user_id, promise_id) if promise_id else None
            if promise_uuid and watched_delta >= 2:
                # Same transaction/idempotency boundary as progress: retries cannot double-log task time.
                session.execute(text("""
                    INSERT INTO actions (action_uuid,user_id,promise_uuid,promise_id_text,
                      action_type,time_spent_hours,at_utc,notes)
                    VALUES (:id,:uid,:promise,:pid,'log_time',:hours,:now,:notes)
                """), {**params, "id": event_id, "promise": promise_uuid, "pid": promise_id,
                       "hours": watched_delta/3600, "notes": f"YouTube watch {video_id}"})
                session.execute(text("""
                    UPDATE user_content SET assigned_promise_id=:promise,assigned_at=COALESCE(assigned_at,:now)
                    WHERE user_id=:uid AND content_id=:cid
                """), {**params, "promise": promise_uuid})
            return {"ok": True, "duplicate": False, **dict(result)}
