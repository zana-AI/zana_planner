"""
Content consumption progress: record events, update rollup buckets, compute progress_ratio,
and update user_content status.
"""
import math
from typing import Any, Dict, List, Optional

from db.postgres_db import utc_now_iso
from repositories.content_repo import ContentRepository
from utils.logger import get_logger

logger = get_logger(__name__)

# Minimum segment length to record: 2 seconds for audio/video, 0.01 ratio for text
MIN_SEGMENT_SECONDS = 2.0
MIN_SEGMENT_RATIO = 0.01
# Progress >= this ratio marks content as completed
COMPLETED_THRESHOLD = 0.95
DEFAULT_BUCKET_COUNT = 120


def _now() -> str:
    return utc_now_iso()


def map_to_bucket_indices(start: float, end: float, duration_or_1: float, bucket_count: int) -> List[int]:
    """
    Return list of bucket indices that the interval [start, end] intersects.
    For audio/video, duration_or_1 is duration_seconds; for text, use 1.0 (ratio 0..1).
    """
    if duration_or_1 <= 0 or bucket_count <= 0:
        return []
    start_idx = int(math.floor((start / duration_or_1) * bucket_count))
    end_idx = int(math.floor((end / duration_or_1) * bucket_count))
    start_idx = max(0, min(start_idx, bucket_count - 1))
    end_idx = max(0, min(end_idx, bucket_count - 1))
    if start_idx > end_idx:
        start_idx, end_idx = end_idx, start_idx
    return list(range(start_idx, end_idx + 1))


class ContentProgressService:
    """Record consumption events and maintain rollup + user_content progress."""

    def __init__(self, content_repo: Optional[ContentRepository] = None):
        self._repo = content_repo or ContentRepository()

    def record_consumption(
        self,
        user_id: str,
        content_id: str,
        start_position: float,
        end_position: float,
        position_unit: str,
        started_at: Optional[str] = None,
        ended_at: Optional[str] = None,
        client: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Record a consumption segment: validate, filter short segments, insert event,
        update rollup buckets, compute progress_ratio, update user_content.
        Returns {progress_ratio, status, ...}.
        """
        user_id = str(user_id)
        content_id = str(content_id)
        if end_position <= start_position:
            return {"progress_ratio": 0.0, "status": "saved", "skipped": "end <= start"}

        if position_unit == "seconds":
            if (end_position - start_position) < MIN_SEGMENT_SECONDS:
                return {"progress_ratio": 0.0, "status": "saved", "skipped": "segment too short (seconds)"}
        elif position_unit == "ratio":
            if (end_position - start_position) < MIN_SEGMENT_RATIO:
                return {"progress_ratio": 0.0, "status": "saved", "skipped": "segment too short (ratio)"}
        else:
            return {"progress_ratio": 0.0, "status": "saved", "skipped": "invalid position_unit"}

        content = self._repo.get_content_by_id(content_id)
        if not content:
            return {"progress_ratio": 0.0, "status": "saved", "skipped": "content not found"}

        duration_or_1 = content.get("duration_seconds") or content.get("estimated_read_seconds")
        if duration_or_1 is None:
            if position_unit == "ratio":
                duration_or_1 = 1.0
            else:
                duration_or_1 = max(end_position, 1.0)

        if position_unit == "ratio":
            duration_or_1 = 1.0

        # Ensure user_content row exists (lazy add when first consumption)
        self._repo.add_user_content(user_id, content_id)

        # Insert event
        self._repo.insert_consumption_event(
            user_id=user_id,
            content_id=content_id,
            start_pos=start_position,
            end_pos=end_position,
            unit=position_unit,
            started_at=started_at,
            ended_at=ended_at,
            client=client,
        )

        # Get or create rollup and update buckets
        rollup = self._repo.get_or_create_rollup(user_id, content_id, bucket_count=DEFAULT_BUCKET_COUNT)
        buckets = list(rollup.get("buckets") or [])
        if len(buckets) != rollup.get("bucket_count", DEFAULT_BUCKET_COUNT):
            buckets = [0] * (rollup.get("bucket_count") or DEFAULT_BUCKET_COUNT)
        indices = map_to_bucket_indices(start_position, end_position, duration_or_1, len(buckets))
        for i in indices:
            if 0 <= i < len(buckets):
                buckets[i] = (buckets[i] or 0) + 1
        now = _now()
        self._repo.update_rollup_buckets(user_id, content_id, buckets, now)

        # Progress ratio = fraction of buckets with count > 0
        non_zero = sum(1 for b in buckets if (b or 0) > 0)
        progress_ratio = min(1.0, non_zero / len(buckets)) if buckets else 0.0

        # Determine status: saved -> in_progress, then completed when progress >= threshold
        current_status = "in_progress"
        if progress_ratio >= COMPLETED_THRESHOLD:
            current_status = "completed"

        self._repo.update_user_content_progress(
            user_id=user_id,
            content_id=content_id,
            last_position=end_position,
            position_unit=position_unit,
            progress_ratio=progress_ratio,
            status=current_status,
            completed_at=now if current_status == "completed" else None,
        )

        return {"progress_ratio": progress_ratio, "status": current_status}
