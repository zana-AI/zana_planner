"""
Repository for promise templates.
"""
import uuid
from typing import List, Optional, Dict, Any
from datetime import date

from db.sqlite_db import connection_for_root, utc_now_iso, date_from_iso, date_to_iso


class TemplatesRepository:
    """SQLite-backed templates repository."""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def list_templates(
        self,
        category: Optional[str] = None,
        program_key: Optional[str] = None,
        is_active: Optional[bool] = True,
    ) -> List[Dict[str, Any]]:
        """List templates, optionally filtered by category/program."""
        with connection_for_root(self.root_dir) as conn:
            conditions = []
            params = []
            
            if is_active is not None:
                conditions.append("is_active = ?")
                params.append(1 if is_active else 0)

            if category:
                conditions.append("category = ?")
                params.append(category)

            if program_key:
                conditions.append("program_key = ?")
                params.append(program_key)

            where_clause = " AND ".join(conditions)
            rows = conn.execute(
                f"""
                SELECT template_id, category, program_key, level, title, why, done, effort,
                       template_kind, metric_type, target_value, target_direction,
                       estimated_hours_per_unit, duration_type, duration_weeks, is_active,
                       created_at_utc, updated_at_utc
                FROM promise_templates
                WHERE {where_clause}
                ORDER BY category, program_key, level;
                """,
                tuple(params),
            ).fetchall()

        return [dict(row) for row in rows]

    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Get a single template by ID."""
        with connection_for_root(self.root_dir) as conn:
            row = conn.execute(
                """
                SELECT template_id, category, program_key, level, title, why, done, effort,
                       template_kind, metric_type, target_value, target_direction,
                       estimated_hours_per_unit, duration_type, duration_weeks, is_active,
                       created_at_utc, updated_at_utc
                FROM promise_templates
                WHERE template_id = ?
                LIMIT 1;
                """,
                (template_id,),
            ).fetchone()

        return dict(row) if row else None

    def get_prerequisites(self, template_id: str) -> List[Dict[str, Any]]:
        """Get all prerequisites for a template, grouped by prereq_group."""
        with connection_for_root(self.root_dir) as conn:
            rows = conn.execute(
                """
                SELECT prereq_id, template_id, prereq_group, kind,
                       required_template_id, min_success_rate, window_weeks, created_at_utc
                FROM template_prerequisites
                WHERE template_id = ?
                ORDER BY prereq_group, prereq_id;
                """,
                (template_id,),
            ).fetchall()

        return [dict(row) for row in rows]

    def create_template(self, template_data: Dict[str, Any]) -> str:
        """Create a new template. Returns the template_id."""
        template_id = template_data.get("template_id") or str(uuid.uuid4())
        now = utc_now_iso()
        
        with connection_for_root(self.root_dir) as conn:
            conn.execute(
                """
                INSERT INTO promise_templates (
                    template_id, category, program_key, level, title, why, done, effort,
                    template_kind, metric_type, target_value, target_direction,
                    estimated_hours_per_unit, duration_type, duration_weeks, is_active,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    template_id,
                    template_data["category"],
                    template_data.get("program_key"),
                    template_data["level"],
                    template_data["title"],
                    template_data["why"],
                    template_data["done"],
                    template_data["effort"],
                    template_data.get("template_kind", "commitment"),
                    template_data["metric_type"],
                    template_data["target_value"],
                    template_data.get("target_direction", "at_least"),
                    template_data.get("estimated_hours_per_unit", 1.0),
                    template_data["duration_type"],
                    template_data.get("duration_weeks"),
                    template_data.get("is_active", True),
                    now,
                    now,
                ),
            )
            conn.commit()
        
        return template_id

    def update_template(self, template_id: str, template_data: Dict[str, Any]) -> bool:
        """Update an existing template. Returns True if updated."""
        now = utc_now_iso()
        
        with connection_for_root(self.root_dir) as conn:
            # Build update query dynamically based on provided fields
            updates = []
            params = []
            
            allowed_fields = [
                "category", "program_key", "level", "title", "why", "done", "effort",
                "template_kind", "metric_type", "target_value", "target_direction",
                "estimated_hours_per_unit", "duration_type", "duration_weeks", "is_active"
            ]
            
            for field in allowed_fields:
                if field in template_data:
                    updates.append(f"{field} = ?")
                    params.append(template_data[field])
            
            if not updates:
                return False
            
            updates.append("updated_at_utc = ?")
            params.append(now)
            params.append(template_id)
            
            cursor = conn.execute(
                f"""
                UPDATE promise_templates
                SET {", ".join(updates)}
                WHERE template_id = ?
                """,
                tuple(params),
            )
            conn.commit()
            
            return cursor.rowcount > 0

    def check_template_in_use(self, template_id: str) -> Dict[str, Any]:
        """
        Check if template is referenced by instances, prerequisites, or reviews.
        Returns dict with 'in_use' bool and 'reasons' list.
        """
        reasons = []
        with connection_for_root(self.root_dir) as conn:
            # Check instances
            instance_count = conn.execute(
                "SELECT COUNT(*) FROM promise_instances WHERE template_id = ?",
                (template_id,),
            ).fetchone()[0]
            if instance_count > 0:
                reasons.append(f"Template has {instance_count} active instance(s)")
            
            # Check prerequisites (templates that require this template)
            prereq_count = conn.execute(
                "SELECT COUNT(*) FROM template_prerequisites WHERE required_template_id = ?",
                (template_id,),
            ).fetchone()[0]
            if prereq_count > 0:
                reasons.append(f"Template is required by {prereq_count} prerequisite(s)")
            
            # Check reviews (if table exists)
            try:
                review_count = conn.execute(
                    "SELECT COUNT(*) FROM template_reviews WHERE template_id = ?",
                    (template_id,),
                ).fetchone()[0]
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
        with connection_for_root(self.root_dir) as conn:
            # Delete prerequisites first (foreign key constraint)
            conn.execute(
                "DELETE FROM template_prerequisites WHERE template_id = ?",
                (template_id,),
            )
            
            # Delete template
            cursor = conn.execute(
                "DELETE FROM promise_templates WHERE template_id = ?",
                (template_id,),
            )
            conn.commit()
            
            return cursor.rowcount > 0

