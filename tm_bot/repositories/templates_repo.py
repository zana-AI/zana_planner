"""
Repository for promise templates.
"""
import uuid
from typing import List, Optional, Dict, Any
from datetime import date

from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso, date_from_iso, date_to_iso


class TemplatesRepository:
    """PostgreSQL-backed templates repository."""

    def __init__(self, root_dir: str = None):
        # root_dir kept for backward compatibility but not used for PostgreSQL
        self.root_dir = root_dir

    def list_templates(
        self,
        category: Optional[str] = None,
        program_key: Optional[str] = None,
        is_active: Optional[bool] = True,
    ) -> List[Dict[str, Any]]:
        """List templates, optionally filtered by category/program."""
        with get_db_session() as session:
            conditions = []
            params = {}
            
            if is_active is not None:
                conditions.append("is_active = :is_active")
                params["is_active"] = 1 if is_active else 0

            if category:
                conditions.append("category = :category")
                params["category"] = category

            if program_key:
                conditions.append("program_key = :program_key")
                params["program_key"] = program_key

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            rows = session.execute(
                text(f"""
                    SELECT template_id, category, program_key, level, title, why, done, effort,
                           template_kind, metric_type, target_value, target_direction,
                           estimated_hours_per_unit, duration_type, duration_weeks, is_active,
                           created_at_utc, updated_at_utc
                    FROM promise_templates
                    WHERE {where_clause}
                    ORDER BY category, program_key, level;
                """),
                params,
            ).fetchall()

        return [dict(row._mapping) for row in rows]

    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Get a single template by ID."""
        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT template_id, category, program_key, level, title, why, done, effort,
                           template_kind, metric_type, target_value, target_direction,
                           estimated_hours_per_unit, duration_type, duration_weeks, is_active,
                           created_at_utc, updated_at_utc
                    FROM promise_templates
                    WHERE template_id = :template_id
                    LIMIT 1;
                """),
                {"template_id": template_id},
            ).fetchone()

        return dict(row._mapping) if row else None

    def get_prerequisites(self, template_id: str) -> List[Dict[str, Any]]:
        """Get all prerequisites for a template, grouped by prereq_group."""
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT prereq_id, template_id, prereq_group, kind,
                           required_template_id, min_success_rate, window_weeks, created_at_utc
                    FROM template_prerequisites
                    WHERE template_id = :template_id
                    ORDER BY prereq_group, prereq_id;
                """),
                {"template_id": template_id},
            ).fetchall()

        return [dict(row._mapping) for row in rows]

    def create_template(self, template_data: Dict[str, Any]) -> str:
        """Create a new template. Returns the template_id."""
        template_id = template_data.get("template_id") or str(uuid.uuid4())
        now = utc_now_iso()
        
        with get_db_session() as session:
            # Check if marketplace columns exist
            has_marketplace_fields = False
            try:
                result = session.execute(
                    text("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = 'promise_templates' 
                        AND column_name = 'canonical_key'
                        LIMIT 1
                    """)
                ).fetchone()
                has_marketplace_fields = result is not None
            except Exception:
                # If check fails, assume columns don't exist
                has_marketplace_fields = False
            
            if has_marketplace_fields:
                # Insert with marketplace fields
                session.execute(
                    text("""
                        INSERT INTO promise_templates (
                            template_id, category, program_key, level, title, why, done, effort,
                            template_kind, metric_type, target_value, target_direction,
                            estimated_hours_per_unit, duration_type, duration_weeks, is_active,
                            canonical_key, created_by_user_id, source_promise_uuid, origin,
                            created_at_utc, updated_at_utc
                        ) VALUES (
                            :template_id, :category, :program_key, :level, :title, :why, :done, :effort,
                            :template_kind, :metric_type, :target_value, :target_direction,
                            :estimated_hours_per_unit, :duration_type, :duration_weeks, :is_active,
                            :canonical_key, :created_by_user_id, :source_promise_uuid, :origin,
                            :created_at_utc, :updated_at_utc
                        )
                    """),
                    {
                        "template_id": template_id,
                        "category": template_data["category"],
                        "program_key": template_data.get("program_key"),
                        "level": template_data["level"],
                        "title": template_data["title"],
                        "why": template_data["why"],
                        "done": template_data["done"],
                        "effort": template_data["effort"],
                        "template_kind": template_data.get("template_kind", "commitment"),
                        "metric_type": template_data["metric_type"],
                        "target_value": template_data["target_value"],
                        "target_direction": template_data.get("target_direction", "at_least"),
                        "estimated_hours_per_unit": template_data.get("estimated_hours_per_unit", 1.0),
                        "duration_type": template_data["duration_type"],
                        "duration_weeks": template_data.get("duration_weeks"),
                        "is_active": 1 if template_data.get("is_active", True) else 0,
                        "canonical_key": template_data.get("canonical_key"),
                        "created_by_user_id": template_data.get("created_by_user_id"),
                        "source_promise_uuid": template_data.get("source_promise_uuid"),
                        "origin": template_data.get("origin"),
                        "created_at_utc": now,
                        "updated_at_utc": now,
                    },
                )
            else:
                # Insert without marketplace fields (for databases that haven't run migration yet)
                session.execute(
                    text("""
                        INSERT INTO promise_templates (
                            template_id, category, program_key, level, title, why, done, effort,
                            template_kind, metric_type, target_value, target_direction,
                            estimated_hours_per_unit, duration_type, duration_weeks, is_active,
                            created_at_utc, updated_at_utc
                        ) VALUES (
                            :template_id, :category, :program_key, :level, :title, :why, :done, :effort,
                            :template_kind, :metric_type, :target_value, :target_direction,
                            :estimated_hours_per_unit, :duration_type, :duration_weeks, :is_active,
                            :created_at_utc, :updated_at_utc
                        )
                    """),
                    {
                        "template_id": template_id,
                        "category": template_data["category"],
                        "program_key": template_data.get("program_key"),
                        "level": template_data["level"],
                        "title": template_data["title"],
                        "why": template_data["why"],
                        "done": template_data["done"],
                        "effort": template_data["effort"],
                        "template_kind": template_data.get("template_kind", "commitment"),
                        "metric_type": template_data["metric_type"],
                        "target_value": template_data["target_value"],
                        "target_direction": template_data.get("target_direction", "at_least"),
                        "estimated_hours_per_unit": template_data.get("estimated_hours_per_unit", 1.0),
                        "duration_type": template_data["duration_type"],
                        "duration_weeks": template_data.get("duration_weeks"),
                        "is_active": 1 if template_data.get("is_active", True) else 0,
                        "created_at_utc": now,
                        "updated_at_utc": now,
                    },
                )
        
        return template_id

    def update_template(self, template_id: str, template_data: Dict[str, Any]) -> bool:
        """Update an existing template. Returns True if updated."""
        now = utc_now_iso()
        
        with get_db_session() as session:
            # Build update query dynamically based on provided fields
            updates = []
            params = {}
            
            allowed_fields = [
                "category", "program_key", "level", "title", "why", "done", "effort",
                "template_kind", "metric_type", "target_value", "target_direction",
                "estimated_hours_per_unit", "duration_type", "duration_weeks", "is_active"
            ]
            
            for field in allowed_fields:
                if field in template_data:
                    updates.append(f"{field} = :{field}")
                    params[field] = template_data[field]
            
            if not updates:
                return False
            
            updates.append("updated_at_utc = :updated_at_utc")
            params["updated_at_utc"] = now
            params["template_id"] = template_id
            
            result = session.execute(
                text(f"""
                    UPDATE promise_templates
                    SET {", ".join(updates)}
                    WHERE template_id = :template_id
                """),
                params,
            )
            
            return result.rowcount > 0

    def check_template_in_use(self, template_id: str) -> Dict[str, Any]:
        """
        Check if template is referenced by instances, prerequisites, or reviews.
        Returns dict with 'in_use' bool and 'reasons' list.
        """
        reasons = []
        with get_db_session() as session:
            # Check instances
            instance_count = session.execute(
                text("SELECT COUNT(*) FROM promise_instances WHERE template_id = :template_id"),
                {"template_id": template_id},
            ).scalar()
            if instance_count > 0:
                reasons.append(f"Template has {instance_count} active instance(s)")
            
            # Check prerequisites (templates that require this template)
            prereq_count = session.execute(
                text("SELECT COUNT(*) FROM template_prerequisites WHERE required_template_id = :template_id"),
                {"template_id": template_id},
            ).scalar()
            if prereq_count > 0:
                reasons.append(f"Template is required by {prereq_count} prerequisite(s)")
            
            # Check reviews (if table exists)
            try:
                review_count = session.execute(
                    text("SELECT COUNT(*) FROM template_reviews WHERE template_id = :template_id"),
                    {"template_id": template_id},
                ).scalar()
                if review_count > 0:
                    reasons.append(f"Template has {review_count} review(s)")
            except Exception:
                # Table might not exist, skip this check
                pass
        
        return {
            "in_use": len(reasons) > 0,
            "reasons": reasons
        }

    def delete_template(self, template_id: str) -> bool:
        """
        Delete a template and its prerequisites.
        Returns True if deleted. Should check in_use first!
        """
        with get_db_session() as session:
            # Delete prerequisites first (foreign key constraint)
            session.execute(
                text("DELETE FROM template_prerequisites WHERE template_id = :template_id"),
                {"template_id": template_id},
            )
            
            # Delete template
            result = session.execute(
                text("DELETE FROM promise_templates WHERE template_id = :template_id"),
                {"template_id": template_id},
            )
            
            return result.rowcount > 0

