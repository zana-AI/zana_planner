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
        is_active: bool = True,
    ) -> List[Dict[str, Any]]:
        """List templates, optionally filtered by category/program."""
        with connection_for_root(self.root_dir) as conn:
            conditions = ["is_active = ?"]
            params = [1 if is_active else 0]

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

