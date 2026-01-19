"""
Repository for promise templates (simplified schema).
"""
import uuid
from typing import List, Optional, Dict, Any

from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso


class TemplatesRepository:
    """PostgreSQL-backed templates repository with simplified schema."""

    def __init__(self, root_dir: str = None):
        # root_dir kept for backward compatibility but not used for PostgreSQL
        self.root_dir = root_dir

    def _has_simplified_schema(self, session) -> bool:
        """Check if the database has the simplified schema (has 'description' column)."""
        try:
            result = session.execute(
                text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'promise_templates' 
                    AND column_name = 'description'
                    LIMIT 1
                """)
            ).fetchone()
            return result is not None
        except Exception:
            return False
    
    def _has_column(self, session, table_name: str, column_name: str) -> bool:
        """Check if a column exists in a table."""
        try:
            result = session.execute(
                text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = :table_name 
                    AND column_name = :column_name
                    LIMIT 1
                """),
                {"table_name": table_name, "column_name": column_name}
            ).fetchone()
            return result is not None
        except Exception:
            return False

    def list_templates(
        self,
        category: Optional[str] = None,
        program_key: Optional[str] = None,
        is_active: Optional[bool] = True,
    ) -> List[Dict[str, Any]]:
        """List templates, optionally filtered by category (program_key ignored)."""
        with get_db_session() as session:
            conditions = []
            params = {}
            
            if is_active is not None:
                conditions.append("is_active = :is_active")
                params["is_active"] = 1 if is_active else 0

            if category:
                conditions.append("category = :category")
                params["category"] = category

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            # Check schema version
            has_description = self._has_simplified_schema(session)
            has_created_by = self._has_column(session, "promise_templates", "created_by_user_id")
            
            if has_description:
                # Simplified schema
                select_fields = "template_id, title, description, category, target_value, metric_type, emoji, is_active, created_at_utc, updated_at_utc"
                if has_created_by:
                    select_fields = "template_id, title, description, category, target_value, metric_type, emoji, created_by_user_id, is_active, created_at_utc, updated_at_utc"
                rows = session.execute(
                    text(f"""
                        SELECT {select_fields}
                        FROM promise_templates
                        WHERE {where_clause}
                        ORDER BY category, title;
                    """),
                    params,
                ).fetchall()
            else:
                # Legacy schema - map old fields to new
                select_fields = "template_id, title, why as description, category, target_value, metric_type, NULL as emoji, is_active, created_at_utc, updated_at_utc"
                if has_created_by:
                    select_fields = "template_id, title, why as description, category, target_value, metric_type, NULL as emoji, created_by_user_id, is_active, created_at_utc, updated_at_utc"
                rows = session.execute(
                    text(f"""
                        SELECT {select_fields}
                        FROM promise_templates
                        WHERE {where_clause}
                        ORDER BY category, title;
                    """),
                    params,
                ).fetchall()

        return [dict(row._mapping) for row in rows]

    def get_prerequisites(self, template_id: str) -> List[Dict[str, Any]]:
        """Return prerequisites for a template. Simplified schema has none."""
        return []

    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Get a single template by ID."""
        with get_db_session() as session:
            has_description = self._has_simplified_schema(session)
            has_created_by = self._has_column(session, "promise_templates", "created_by_user_id")
            
            if has_description:
                # Simplified schema
                select_fields = "template_id, title, description, category, target_value, metric_type, emoji, is_active, created_at_utc, updated_at_utc"
                if has_created_by:
                    select_fields = "template_id, title, description, category, target_value, metric_type, emoji, created_by_user_id, is_active, created_at_utc, updated_at_utc"
                row = session.execute(
                    text(f"""
                        SELECT {select_fields}
                        FROM promise_templates
                        WHERE template_id = :template_id
                        LIMIT 1;
                    """),
                    {"template_id": template_id},
                ).fetchone()
            else:
                # Legacy schema
                select_fields = "template_id, title, why as description, category, target_value, metric_type, NULL as emoji, is_active, created_at_utc, updated_at_utc"
                if has_created_by:
                    select_fields = "template_id, title, why as description, category, target_value, metric_type, NULL as emoji, created_by_user_id, is_active, created_at_utc, updated_at_utc"
                row = session.execute(
                    text(f"""
                        SELECT {select_fields}
                        FROM promise_templates
                        WHERE template_id = :template_id
                        LIMIT 1;
                    """),
                    {"template_id": template_id},
                ).fetchone()

        return dict(row._mapping) if row else None

    def create_template(self, template_data: Dict[str, Any]) -> str:
        """Create a new template. Returns the template_id."""
        template_id = template_data.get("template_id") or str(uuid.uuid4())
        now = utc_now_iso()
        
        with get_db_session() as session:
            has_description = self._has_simplified_schema(session)
            has_created_by = self._has_column(session, "promise_templates", "created_by_user_id")
            
            if has_description:
                # Simplified schema
                columns = ["template_id", "title", "description", "category", "target_value", "metric_type", "emoji", "is_active", "created_at_utc", "updated_at_utc"]
                values = [":template_id", ":title", ":description", ":category", ":target_value", ":metric_type", ":emoji", ":is_active", ":created_at_utc", ":updated_at_utc"]
                params = {
                    "template_id": template_id,
                    "title": template_data["title"],
                    "description": template_data.get("description"),
                    "category": template_data["category"],
                    "target_value": template_data["target_value"],
                    "metric_type": template_data.get("metric_type", "count"),
                    "emoji": template_data.get("emoji"),
                    "is_active": 1 if template_data.get("is_active", True) else 0,
                    "created_at_utc": now,
                    "updated_at_utc": now,
                }
                
                if has_created_by:
                    columns.insert(-2, "created_by_user_id")  # Insert before is_active
                    values.insert(-2, ":created_by_user_id")
                    params["created_by_user_id"] = template_data.get("created_by_user_id")
                
                session.execute(
                    text(f"""
                        INSERT INTO promise_templates ({', '.join(columns)})
                        VALUES ({', '.join(values)})
                    """),
                    params,
                )
            else:
                # Legacy schema - insert with old field names
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
                        "program_key": "",
                        "level": "beginner",
                        "title": template_data["title"],
                        "why": template_data.get("description", ""),
                        "done": "",
                        "effort": "medium",
                        "template_kind": "commitment",
                        "metric_type": template_data.get("metric_type", "count"),
                        "target_value": template_data["target_value"],
                        "target_direction": "at_least",
                        "estimated_hours_per_unit": 1.0,
                        "duration_type": "week",
                        "duration_weeks": None,
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
            if self._has_simplified_schema(session):
                # Build update query dynamically
                updates = ["updated_at_utc = :updated_at_utc"]
                params = {"template_id": template_id, "updated_at_utc": now}
                
                field_map = {
                    "title": "title",
                    "description": "description",
                    "category": "category",
                    "target_value": "target_value",
                    "metric_type": "metric_type",
                    "emoji": "emoji",
                    "is_active": "is_active",
                }
                
                for key, col in field_map.items():
                    if key in template_data:
                        value = template_data[key]
                        if key == "is_active":
                            value = 1 if value else 0
                        updates.append(f"{col} = :{key}")
                        params[key] = value
                
                update_clause = ", ".join(updates)
                result = session.execute(
                    text(f"""
                        UPDATE promise_templates 
                        SET {update_clause}
                        WHERE template_id = :template_id
                    """),
                    params,
                )
            else:
                # Legacy schema
                updates = ["updated_at_utc = :updated_at_utc"]
                params = {"template_id": template_id, "updated_at_utc": now}
                
                if "title" in template_data:
                    updates.append("title = :title")
                    params["title"] = template_data["title"]
                if "description" in template_data:
                    updates.append("why = :why")
                    params["why"] = template_data["description"]
                if "category" in template_data:
                    updates.append("category = :category")
                    params["category"] = template_data["category"]
                if "target_value" in template_data:
                    updates.append("target_value = :target_value")
                    params["target_value"] = template_data["target_value"]
                if "metric_type" in template_data:
                    updates.append("metric_type = :metric_type")
                    params["metric_type"] = template_data["metric_type"]
                if "is_active" in template_data:
                    updates.append("is_active = :is_active")
                    params["is_active"] = 1 if template_data["is_active"] else 0
                
                update_clause = ", ".join(updates)
                result = session.execute(
                    text(f"""
                        UPDATE promise_templates 
                        SET {update_clause}
                        WHERE template_id = :template_id
                    """),
                    params,
                )
        
        return result.rowcount > 0

    def delete_template(self, template_id: str) -> bool:
        """Delete a template. Returns True if deleted."""
        with get_db_session() as session:
            result = session.execute(
                text("""
                    DELETE FROM promise_templates 
                    WHERE template_id = :template_id
                """),
                {"template_id": template_id},
            )
        
        return result.rowcount > 0

    def get_templates_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """Get templates created by a specific user."""
        with get_db_session() as session:
            has_description = self._has_simplified_schema(session)
            has_created_by = self._has_column(session, "promise_templates", "created_by_user_id")
            
            # Only query if created_by_user_id column exists
            if not has_created_by:
                return []
            
            if has_description:
                rows = session.execute(
                    text("""
                        SELECT template_id, title, description, category, target_value, 
                               metric_type, emoji, created_by_user_id, is_active,
                               created_at_utc, updated_at_utc
                        FROM promise_templates
                        WHERE created_by_user_id = :user_id AND is_active = 1
                        ORDER BY created_at_utc DESC;
                    """),
                    {"user_id": str(user_id)},
                ).fetchall()
            else:
                rows = session.execute(
                    text("""
                        SELECT template_id, title, why as description, category, target_value, 
                               metric_type, NULL as emoji, created_by_user_id, is_active,
                               created_at_utc, updated_at_utc
                        FROM promise_templates
                        WHERE created_by_user_id = :user_id AND is_active = 1
                        ORDER BY created_at_utc DESC;
                    """),
                    {"user_id": str(user_id)},
                ).fetchall()

        return [dict(row._mapping) for row in rows]

    def get_categories(self) -> List[str]:
        """Get list of unique categories."""
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT DISTINCT category 
                    FROM promise_templates 
                    WHERE is_active = 1 AND category IS NOT NULL
                    ORDER BY category;
                """)
            ).fetchall()

        return [row[0] for row in rows if row[0]]
