"""
Service for computing template unlock status.
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from repositories.templates_repo import TemplatesRepository
from repositories.instances_repo import InstancesRepository
from repositories.reviews_repo import ReviewsRepository
from db.sqlite_db import connection_for_root


class TemplateUnlocksService:
    """Service to compute which templates are unlocked for a user."""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.templates_repo = TemplatesRepository(root_dir)
        self.instances_repo = InstancesRepository(root_dir)
        self.reviews_repo = ReviewsRepository(root_dir)

    def get_unlock_status(
        self, user_id: int, template_id: str
    ) -> Dict[str, any]:
        """
        Get unlock status for a template.
        
        Returns dict with:
        - unlocked: bool
        - lock_reason: Optional[str] (if locked, explains why)
        - satisfied_prereq_groups: List[int] (which prereq groups are satisfied)
        """
        template = self.templates_repo.get_template(template_id)
        if not template:
            return {"unlocked": False, "lock_reason": "Template not found"}

        # If no prerequisites, template is unlocked
        prerequisites = self.templates_repo.get_prerequisites(template_id)
        if not prerequisites:
            return {"unlocked": True, "lock_reason": None, "satisfied_prereq_groups": []}

        # Group prerequisites by prereq_group
        prereq_groups: Dict[int, List[Dict]] = {}
        for p in prerequisites:
            group = p["prereq_group"]
            if group not in prereq_groups:
                prereq_groups[group] = []
            prereq_groups[group].append(p)

        # Check each group: unlocked if ANY group is fully satisfied
        satisfied_groups = []
        for group_num, group_prereqs in prereq_groups.items():
            if self._is_group_satisfied(user_id, group_prereqs):
                satisfied_groups.append(group_num)

        unlocked = len(satisfied_groups) > 0

        if unlocked:
            return {
                "unlocked": True,
                "lock_reason": None,
                "satisfied_prereq_groups": satisfied_groups,
            }
        else:
            # Find which prerequisites are missing
            missing = []
            for group_num, group_prereqs in prereq_groups.items():
                for p in group_prereqs:
                    if p["kind"] == "completed_template":
                        required_id = p["required_template_id"]
                        if not self._has_completed_template(user_id, required_id):
                            missing.append(f"Complete template: {required_id}")
                    elif p["kind"] == "success_rate":
                        required_id = p["required_template_id"]
                        min_rate = p["min_success_rate"]
                        window_weeks = p["window_weeks"] or 4
                        if not self._has_success_rate(
                            user_id, required_id, min_rate, window_weeks
                        ):
                            missing.append(
                                f"Achieve {min_rate*100}% success on {required_id} over {window_weeks} weeks"
                            )

            reason = "Unlock requirements not met: " + "; ".join(missing[:3])
            if len(missing) > 3:
                reason += f" (+{len(missing)-3} more)"

            return {
                "unlocked": False,
                "lock_reason": reason,
                "satisfied_prereq_groups": [],
            }

    def _is_group_satisfied(self, user_id: int, group_prereqs: List[Dict]) -> bool:
        """Check if all prerequisites in a group are satisfied."""
        for p in group_prereqs:
            if p["kind"] == "completed_template":
                required_id = p["required_template_id"]
                if not self._has_completed_template(user_id, required_id):
                    return False
            elif p["kind"] == "success_rate":
                required_id = p["required_template_id"]
                min_rate = p["min_success_rate"]
                window_weeks = p["window_weeks"] or 4
                if not self._has_success_rate(user_id, required_id, min_rate, window_weeks):
                    return False
        return True

    def _has_completed_template(self, user_id: int, template_id: str) -> bool:
        """Check if user has completed an instance of this template."""
        instances = self.instances_repo.list_active_instances(user_id)
        # Also check completed instances
        user = str(user_id)
        with connection_for_root(self.root_dir) as conn:
            rows = conn.execute(
                """
                SELECT instance_id FROM promise_instances
                WHERE user_id = ? AND template_id = ? AND status = 'completed'
                LIMIT 1;
                """,
                (user, template_id),
            ).fetchall()
            return len(rows) > 0

    def _has_success_rate(
        self, user_id: int, template_id: str, min_rate: float, window_weeks: int
    ) -> bool:
        """Check if user has achieved min_rate success over window_weeks."""
        user = str(user_id)
        # Get all instances of this template
        with connection_for_root(self.root_dir) as conn:
            instance_rows = conn.execute(
                """
                SELECT instance_id FROM promise_instances
                WHERE user_id = ? AND template_id = ?
                ORDER BY created_at_utc DESC
                LIMIT 10;
                """,
                (user, template_id),
            ).fetchall()

        if not instance_rows:
            return False

        # Get reviews for these instances in the last window_weeks
        cutoff_date = datetime.now() - timedelta(weeks=window_weeks)
        cutoff_str = cutoff_date.isoformat()

        total_reviews = 0
        successful_reviews = 0

        for row in instance_rows:
            instance_id = row["instance_id"]
            reviews = self.reviews_repo.list_reviews_for_instance(user_id, instance_id, limit=window_weeks * 2)
            for review in reviews:
                if review["week_start"] >= cutoff_str:
                    total_reviews += 1
                    if review["success_ratio"] >= min_rate:
                        successful_reviews += 1

        if total_reviews == 0:
            return False

        actual_rate = successful_reviews / total_reviews
        return actual_rate >= min_rate

    def annotate_templates_with_unlock_status(
        self, user_id: int, templates: List[Dict]
    ) -> List[Dict]:
        """Add unlock_status to each template dict."""
        result = []
        for template in templates:
            status = self.get_unlock_status(user_id, template["template_id"])
            template_copy = dict(template)
            template_copy["unlocked"] = status["unlocked"]
            template_copy["lock_reason"] = status["lock_reason"]
            result.append(template_copy)
        return result

