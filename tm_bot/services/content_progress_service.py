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
PDF_CHECKPOINT_CLIENT = "web_pdf_reader_checkpoint"
PDF_READ_CLIENT = "web_pdf_reader_read"


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


def map_ratio_to_bucket_indices_exclusive(start: float, end: float, bucket_count: int) -> List[int]:
    """
    Return bucket indices for a ratio interval using [start, end) semantics.
    This is used for PDF read-coverage buckets where clients send exact bucket
    boundaries, e.g. 0/120 -> 1/120 should mark only bucket 0.
    """
    if bucket_count <= 0:
        return []
    start = max(0.0, min(1.0, start))
    end = max(0.0, min(1.0, end))
    if end <= start:
        return []
    start_idx = int(math.floor(start * bucket_count))
    end_idx = int(math.ceil(end * bucket_count) - 1)
    start_idx = max(0, min(start_idx, bucket_count - 1))
    end_idx = max(0, min(end_idx, bucket_count - 1))
    if start_idx > end_idx:
        return []
    return list(range(start_idx, end_idx + 1))


def _progress_ratio_from_buckets(buckets: List[int]) -> float:
    if not buckets:
        return 0.0
    non_zero = sum(1 for b in buckets if (b or 0) > 0)
    return min(1.0, non_zero / len(buckets))


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
        is_pdf_checkpoint = position_unit == "ratio" and client == PDF_CHECKPOINT_CLIENT
        is_pdf_read = position_unit == "ratio" and client == PDF_READ_CLIENT
        if position_unit == "ratio":
            start_position = max(0.0, min(1.0, start_position))
            end_position = max(0.0, min(1.0, end_position))

        if position_unit not in {"seconds", "ratio"}:
            return {"progress_ratio": 0.0, "status": "saved", "skipped": "invalid position_unit"}

        content = self._repo.get_content_by_id(content_id)
        if not content:
            return {"progress_ratio": 0.0, "status": "saved", "skipped": "content not found"}

        # PDF resume checkpoints are not read coverage. They update where the
        # user left off, but never color heatmap buckets or inflate progress.
        if is_pdf_checkpoint:
            self._repo.add_user_content(user_id, content_id)
            self._repo.update_user_content_progress(
                user_id=user_id,
                content_id=content_id,
                last_position=end_position,
                position_unit=position_unit,
            )
            heatmap = self._repo.get_heatmap(user_id, content_id) if hasattr(self._repo, "get_heatmap") else None
            buckets = list((heatmap or {}).get("buckets") or [])
            progress_ratio = _progress_ratio_from_buckets(buckets)
            status = "completed" if progress_ratio >= COMPLETED_THRESHOLD else "in_progress" if progress_ratio > 0 else "saved"
            return {"progress_ratio": progress_ratio, "status": status, "checkpoint": True}

        if position_unit == "seconds":
            if (end_position - start_position) < MIN_SEGMENT_SECONDS:
                return {"progress_ratio": 0.0, "status": "saved", "skipped": "segment too short (seconds)"}
        elif position_unit == "ratio" and not is_pdf_read:
            if (end_position - start_position) < MIN_SEGMENT_RATIO:
                return {"progress_ratio": 0.0, "status": "saved", "skipped": "segment too short (ratio)"}
        elif is_pdf_read:
            if end_position <= start_position:
                return {"progress_ratio": 0.0, "status": "saved", "skipped": "empty pdf read segment"}

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
        indices = (
            map_ratio_to_bucket_indices_exclusive(start_position, end_position, len(buckets))
            if is_pdf_read
            else map_to_bucket_indices(start_position, end_position, duration_or_1, len(buckets))
        )
        for i in indices:
            if 0 <= i < len(buckets):
                buckets[i] = (buckets[i] or 0) + 1
        now = _now()
        self._repo.update_rollup_buckets(user_id, content_id, buckets, now)

        # Progress ratio = fraction of buckets with count > 0
        progress_ratio = _progress_ratio_from_buckets(buckets)

        # Determine status: saved -> in_progress, then completed when progress >= threshold
        current_status = "in_progress"
        if progress_ratio >= COMPLETED_THRESHOLD:
            current_status = "completed"

        self._repo.update_user_content_progress(
            user_id=user_id,
            content_id=content_id,
            last_position=None if is_pdf_read else end_position,
            position_unit=None if is_pdf_read else position_unit,
            progress_ratio=progress_ratio,
            status=current_status,
            completed_at=now if current_status == "completed" else None,
        )

        return {"progress_ratio": progress_ratio, "status": current_status}
