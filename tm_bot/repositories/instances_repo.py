"""
Repository for promise instances (user subscriptions to templates).
"""
import uuid
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta

from sqlalchemy import text

from db.postgres_db import (
    get_db_session,
    resolve_promise_uuid,
    utc_now_iso,
    date_from_iso,
    date_to_iso,
    dt_to_utc_iso,
)
from repositories.promises_repo import PromisesRepository
from models.models import Promise


class InstancesRepository:
    """PostgreSQL-backed promise instances repository."""

    def __init__(self, root_dir: str = None):
        # root_dir kept for backward compatibility but not used for PostgreSQL
        self.root_dir = root_dir
        self.promises_repo = PromisesRepository(root_dir)

    def subscribe_template(
        self,
        user_id: int,
        template_id: str,
        start_date: Optional[date] = None,
        target_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Subscribe to a template: creates a promise and an instance.
        
        Returns dict with instance_id, promise_id, promise_uuid, start_date, end_date.
        """
        from repositories.templates_repo import TemplatesRepository

        templates_repo = TemplatesRepository(self.root_dir)
        template = templates_repo.get_template(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")

        user = str(user_id)
        now = utc_now_iso()
        instance_id = str(uuid.uuid4())

        # Determine dates
        if not start_date:
            start_date = datetime.now().date()
        if not target_date:
            if template["duration_type"] == "week":
                weeks = template["duration_weeks"] or 1
                target_date = start_date + timedelta(weeks=weeks)
            elif template["duration_type"] == "one_time":
                target_date = start_date + timedelta(days=7)  # Default 1 week
            else:  # date
                # For date-based, target_date should be provided or we use duration_weeks
                weeks = template["duration_weeks"] or 4
                target_date = start_date + timedelta(weeks=weeks)

        # Generate promise ID (use template prefix + instance short ID)
        promise_id = f"T{instance_id[:6].upper()}"
        
        # Create promise text from template title
        promise_text = template["title"].replace(" ", "_")

        # Create the promise
        # Default to recurring=True, only set False for one_time templates
        is_recurring = template["duration_type"] != "one_time"
        promise = Promise(
            user_id=user,
            id=promise_id,
            text=promise_text,
            hours_per_week=template["target_value"] if template["metric_type"] == "hours" else 0.0,
            recurring=is_recurring,
            start_date=start_date,
            end_date=target_date,
            angle_deg=0,
            radius=0,
            visibility="private",
        )
        self.promises_repo.upsert_promise(user_id, promise)

        # Get promise_uuid
        promise_obj = self.promises_repo.get_promise(user_id, promise_id)
        if not promise_obj:
            raise RuntimeError("Failed to create promise")

        # Resolve promise_uuid
        with get_db_session() as session:
            promise_uuid = resolve_promise_uuid(session, user, promise_id)

            if not promise_uuid:
                raise RuntimeError("Failed to resolve promise UUID")

            # Create instance
            session.execute(
                text("""
                    INSERT INTO promise_instances (
                        instance_id, user_id, template_id, promise_uuid, status,
                        metric_type, target_value, estimated_hours_per_unit,
                        start_date, end_date, created_at_utc, updated_at_utc
                    ) VALUES (
                        :instance_id, :user_id, :template_id, :promise_uuid, :status,
                        :metric_type, :target_value, :estimated_hours_per_unit,
                        :start_date, :end_date, :created_at_utc, :updated_at_utc
                    );
                """),
                {
                    "instance_id": instance_id,
                    "user_id": user,
                    "template_id": template_id,
                    "promise_uuid": promise_uuid,
                    "status": "active",
                    "metric_type": template["metric_type"],
                    "target_value": template["target_value"],
                    "estimated_hours_per_unit": template["estimated_hours_per_unit"],
                    "start_date": date_to_iso(start_date),
                    "end_date": date_to_iso(target_date),
                    "created_at_utc": now,
                    "updated_at_utc": now,
                },
            )

        return {
            "instance_id": instance_id,
            "promise_id": promise_id,
            "promise_uuid": promise_uuid,
            "start_date": start_date.isoformat(),
            "end_date": target_date.isoformat() if target_date else None,
        }

    def list_active_instances(self, user_id: int) -> List[Dict[str, Any]]:
        """List all active instances for a user."""
        user = str(user_id)
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT i.instance_id, i.user_id, i.template_id, i.promise_uuid, i.status,
                           i.metric_type, i.target_value, i.estimated_hours_per_unit,
                           i.start_date, i.end_date, i.created_at_utc, i.updated_at_utc,
                           t.title, t.category, t.template_kind, t.target_direction
                    FROM promise_instances i
                    JOIN promise_templates t ON i.template_id = t.template_id
                    WHERE i.user_id = :user_id AND i.status = 'active'
                    ORDER BY i.created_at_utc DESC;
                """),
                {"user_id": user},
            ).fetchall()

        return [dict(row._mapping) for row in rows]

    def get_instance(self, user_id: int, instance_id: str) -> Optional[Dict[str, Any]]:
        """Get a single instance by ID."""
        user = str(user_id)
        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT i.instance_id, i.user_id, i.template_id, i.promise_uuid, i.status,
                           i.metric_type, i.target_value, i.estimated_hours_per_unit,
                           i.start_date, i.end_date, i.created_at_utc, i.updated_at_utc,
                           t.title, t.category, t.template_kind, t.target_direction
                    FROM promise_instances i
                    JOIN promise_templates t ON i.template_id = t.template_id
                    WHERE i.user_id = :user_id AND i.instance_id = :instance_id
                    LIMIT 1;
                """),
                {"user_id": user, "instance_id": instance_id},
            ).fetchone()

        return dict(row._mapping) if row else None

    def get_instance_by_promise_uuid(
        self, user_id: int, promise_uuid: str
    ) -> Optional[Dict[str, Any]]:
        """Get instance by promise_uuid."""
        user = str(user_id)
        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT i.instance_id, i.user_id, i.template_id, i.promise_uuid, i.status,
                           i.metric_type, i.target_value, i.estimated_hours_per_unit,
                           i.start_date, i.end_date, i.created_at_utc, i.updated_at_utc,
                           t.title, t.category, t.template_kind, t.target_direction
                    FROM promise_instances i
                    JOIN promise_templates t ON i.template_id = t.template_id
                    WHERE i.user_id = :user_id AND i.promise_uuid = :promise_uuid
                    LIMIT 1;
                """),
                {"user_id": user, "promise_uuid": promise_uuid},
            ).fetchone()

        return dict(row._mapping) if row else None

    def mark_completed(self, user_id: int, instance_id: str) -> bool:
        """Mark an instance as completed."""
        user = str(user_id)
        now = utc_now_iso()
        with get_db_session() as session:
            result = session.execute(
                text("""
                    UPDATE promise_instances
                    SET status = 'completed', updated_at_utc = :now
                    WHERE user_id = :user_id AND instance_id = :instance_id AND status = 'active';
                """),
                {"now": now, "user_id": user, "instance_id": instance_id},
            )
            return result.rowcount > 0

    def mark_abandoned(self, user_id: int, instance_id: str) -> bool:
        """Mark an instance as abandoned."""
        user = str(user_id)
        now = utc_now_iso()
        with get_db_session() as session:
            result = session.execute(
                text("""
                    UPDATE promise_instances
                    SET status = 'abandoned', updated_at_utc = :now
                    WHERE user_id = :user_id AND instance_id = :instance_id AND status = 'active';
                """),
                {"now": now, "user_id": user, "instance_id": instance_id},
            )
            return result.rowcount > 0

