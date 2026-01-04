"""
Repository for promise weekly reviews.
"""
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta

from db.sqlite_db import (
    connection_for_root,
    utc_now_iso,
    date_from_iso,
    date_to_iso,
    dt_to_utc_iso,
)
from utils.time_utils import get_week_range
# Import at function level to avoid circular dependencies


class ReviewsRepository:
    """SQLite-backed weekly reviews repository."""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def compute_or_get_weekly_review(
        self, user_id: int, instance_id: str, ref_time: datetime
    ) -> Dict[str, Any]:
        """
        Compute weekly review for an instance, or return existing if already computed.
        
        Returns dict with review_id, week_start, week_end, metric_type, target_value,
        achieved_value, success_ratio, note.
        """
        from repositories.instances_repo import InstancesRepository
        instances_repo = InstancesRepository(self.root_dir)
        instance = instances_repo.get_instance(user_id, instance_id)
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")

        week_start, week_end = get_week_range(ref_time)
        week_start_str = week_start.isoformat()
        week_end_str = week_end.isoformat()

        user = str(user_id)

        # Check if review already exists
        with connection_for_root(self.root_dir) as conn:
            existing = conn.execute(
                """
                SELECT review_id, user_id, instance_id, week_start, week_end,
                       metric_type, target_value, achieved_value, success_ratio, note, computed_at_utc
                FROM promise_weekly_reviews
                WHERE user_id = ? AND instance_id = ? AND week_start = ?
                LIMIT 1;
                """,
                (user, instance_id, week_start_str),
            ).fetchone()

            if existing:
                return dict(existing)

        # Compute achieved value based on metric_type
        metric_type = instance["metric_type"]
        target_value = instance["target_value"]
        target_direction = instance["target_direction"]

        from repositories.actions_repo import ActionsRepository
        actions_repo = ActionsRepository(self.root_dir)
        
        if metric_type == "count":
            # Count check-in actions for this promise in this week
            promise_uuid = instance["promise_uuid"]
            actions = actions_repo.list_actions(user_id, since=week_start)
            checkin_count = sum(
                1
                for a in actions
                if a.promise_id
                and week_start <= a.at <= week_end
                and a.action == "checkin"
            )
            # Need to match by promise_uuid - let's get the promise_id first
            from repositories.promises_repo import PromisesRepository
            promises_repo = PromisesRepository(self.root_dir)
            # Find promise by UUID
            with connection_for_root(self.root_dir) as conn:
                promise_row = conn.execute(
                    "SELECT current_id FROM promises WHERE promise_uuid = ? LIMIT 1;",
                    (promise_uuid,),
                ).fetchone()
                if promise_row:
                    promise_id = promise_row["current_id"]
                    checkin_count = sum(
                        1
                        for a in actions
                        if (a.promise_id or "").strip().upper() == promise_id.upper()
                        and week_start <= a.at <= week_end
                        and a.action == "checkin"
                    )
            achieved_value = float(checkin_count)

        elif metric_type == "hours":
            # For budget templates, use distraction_events
            from repositories.templates_repo import TemplatesRepository
            templates_repo = TemplatesRepository(self.root_dir)
            template = templates_repo.get_template(instance["template_id"])
            if template and template["template_kind"] == "budget":
                # Sum distraction minutes for this week, convert to hours
                with connection_for_root(self.root_dir) as conn:
                    week_start_utc = dt_to_utc_iso(week_start)
                    week_end_utc = dt_to_utc_iso(week_end)
                    rows = conn.execute(
                        """
                        SELECT SUM(minutes) as total_minutes
                        FROM distraction_events
                        WHERE user_id = ? AND at_utc >= ? AND at_utc <= ?
                        """,
                        (user, week_start_utc, week_end_utc),
                    ).fetchone()
                    total_minutes = float(rows["total_minutes"] or 0) if rows else 0.0
                    achieved_value = total_minutes / 60.0
            else:
                # Regular hours: sum time_spent from actions
                promise_uuid = instance["promise_uuid"]
                actions = actions_repo.list_actions(user_id, since=week_start)
                with connection_for_root(self.root_dir) as conn:
                    promise_row = conn.execute(
                        "SELECT current_id FROM promises WHERE promise_uuid = ? LIMIT 1;",
                        (promise_uuid,),
                    ).fetchone()
                    if promise_row:
                        promise_id = promise_row["current_id"]
                        achieved_value = sum(
                            a.time_spent
                            for a in actions
                            if (a.promise_id or "").strip().upper() == promise_id.upper()
                            and week_start <= a.at <= week_end
                            and a.action == "log_time"
                        )
                    else:
                        achieved_value = 0.0
        else:
            achieved_value = 0.0

        # Compute success ratio
        if target_direction == "at_least":
            # For commitments: success if achieved >= target
            if target_value > 0:
                success_ratio = min(achieved_value / target_value, 1.0) if achieved_value >= 0 else 0.0
            else:
                success_ratio = 1.0 if achieved_value >= 0 else 0.0
        else:  # at_most
            # For budgets: success if achieved <= target
            if target_value > 0:
                # Success ratio: 1.0 if under, decreasing as we go over
                if achieved_value <= target_value:
                    success_ratio = achieved_value / target_value if target_value > 0 else 1.0
                else:
                    # Over budget: ratio goes negative (or we cap at 0)
                    excess = achieved_value - target_value
                    success_ratio = max(0.0, 1.0 - (excess / target_value))
            else:
                success_ratio = 1.0 if achieved_value <= 0 else 0.0

        # Create review record
        review_id = str(uuid.uuid4())
        now = utc_now_iso()

        with connection_for_root(self.root_dir) as conn:
            conn.execute(
                """
                INSERT INTO promise_weekly_reviews (
                    review_id, user_id, instance_id, week_start, week_end,
                    metric_type, target_value, achieved_value, success_ratio, note, computed_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    review_id,
                    user,
                    instance_id,
                    week_start_str,
                    week_end_str,
                    metric_type,
                    target_value,
                    achieved_value,
                    success_ratio,
                    None,
                    now,
                ),
            )

        return {
            "review_id": review_id,
            "user_id": user,
            "instance_id": instance_id,
            "week_start": week_start_str,
            "week_end": week_end_str,
            "metric_type": metric_type,
            "target_value": target_value,
            "achieved_value": achieved_value,
            "success_ratio": success_ratio,
            "note": None,
            "computed_at_utc": now,
        }

    def update_weekly_note(
        self, user_id: int, instance_id: str, week_start: str, note: Optional[str]
    ) -> bool:
        """Update the note field for a weekly review."""
        user = str(user_id)
        with connection_for_root(self.root_dir) as conn:
            cursor = conn.execute(
                """
                UPDATE promise_weekly_reviews
                SET note = ?
                WHERE user_id = ? AND instance_id = ? AND week_start = ?;
                """,
                (note, user, instance_id, week_start),
            )
            return cursor.rowcount > 0

    def get_weekly_review(
        self, user_id: int, instance_id: str, week_start: str
    ) -> Optional[Dict[str, Any]]:
        """Get an existing weekly review."""
        user = str(user_id)
        with connection_for_root(self.root_dir) as conn:
            row = conn.execute(
                """
                SELECT review_id, user_id, instance_id, week_start, week_end,
                       metric_type, target_value, achieved_value, success_ratio, note, computed_at_utc
                FROM promise_weekly_reviews
                WHERE user_id = ? AND instance_id = ? AND week_start = ?
                LIMIT 1;
                """,
                (user, instance_id, week_start),
            ).fetchone()

        return dict(row) if row else None

    def list_reviews_for_instance(
        self, user_id: int, instance_id: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """List recent reviews for an instance."""
        user = str(user_id)
        with connection_for_root(self.root_dir) as conn:
            rows = conn.execute(
                """
                SELECT review_id, user_id, instance_id, week_start, week_end,
                       metric_type, target_value, achieved_value, success_ratio, note, computed_at_utc
                FROM promise_weekly_reviews
                WHERE user_id = ? AND instance_id = ?
                ORDER BY week_start DESC
                LIMIT ?;
                """,
                (user, instance_id, limit),
            ).fetchall()

        return [dict(row) for row in rows]

