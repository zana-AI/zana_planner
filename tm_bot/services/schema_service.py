"""
Service for generating database schema documentation dynamically from metadata.
"""
from typing import Dict, Optional

from db.postgres_db import get_db_session, get_table_columns, check_table_exists
from sqlalchemy import text
from utils.logger import get_logger

logger = get_logger(__name__)


class SchemaService:
    """Service for generating database schema documentation."""
    
    # Core user data tables that should be documented
    USER_TABLES = [
        "promises",
        "actions",
        "sessions",
        "users",
        "promise_aliases",
        "promise_events",
    ]
    
    # Example queries (static, but centralized here)
    EXAMPLE_QUERIES = """
EXAMPLE QUERIES:

1. Total hours by month:
   SELECT strftime('%Y-%m', at_utc) as month, 
          SUM(time_spent_hours) as total_hours
   FROM actions WHERE user_id = '{user_id}' 
   GROUP BY month ORDER BY month

2. Most active promises (by total hours):
   SELECT promise_id_text, 
          COUNT(*) as sessions, 
          SUM(time_spent_hours) as total_hours
   FROM actions WHERE user_id = '{user_id}' 
   GROUP BY promise_id_text ORDER BY total_hours DESC

3. Hours in a specific date range:
   SELECT SUM(time_spent_hours) as total
   FROM actions 
   WHERE user_id = '{user_id}' 
     AND at_utc >= '2025-01-01' AND at_utc < '2025-02-01'

4. Average session duration per promise:
   SELECT promise_id_text, 
          AVG(time_spent_hours) as avg_hours,
          COUNT(*) as sessions
   FROM actions WHERE user_id = '{user_id}'
   GROUP BY promise_id_text

5. Days with most activity:
   SELECT date(at_utc) as day, 
          SUM(time_spent_hours) as hours
   FROM actions WHERE user_id = '{user_id}'
   GROUP BY day ORDER BY hours DESC LIMIT 10

6. Promise details with text:
   SELECT current_id, text, hours_per_week, 
          start_date, is_deleted
   FROM promises WHERE user_id = '{user_id}'
"""
    
    def __init__(self):
        self._schema_cache: Optional[str] = None
    
    def get_schema_documentation(self, force_refresh: bool = False) -> str:
        """
        Get database schema documentation with table structures.
        
        Args:
            force_refresh: If True, regenerate schema even if cached.
        
        Returns:
            Formatted schema documentation string.
        """
        if self._schema_cache and not force_refresh:
            return self._schema_cache
        
        try:
            schema_lines = ["DATABASE SCHEMA:\n"]
            
            with get_db_session() as session:
                for table_name in self.USER_TABLES:
                    if not check_table_exists(session, table_name):
                        logger.warning(f"Table {table_name} does not exist, skipping")
                        continue
                    
                    columns = get_table_columns(session, table_name)
                    if not columns:
                        continue
                    
                    schema_lines.append(f"TABLE: {table_name}")
                    
                    # Get column types and constraints from information_schema
                    column_info = self._get_column_info(session, table_name)
                    
                    for col in columns:
                        col_type = column_info.get(col, {}).get('data_type', 'TEXT')
                        is_primary = column_info.get(col, {}).get('is_primary', False)
                        is_nullable = column_info.get(col, {}).get('is_nullable', True)
                        
                        primary_marker = " PRIMARY KEY" if is_primary else ""
                        nullable_marker = "" if is_nullable else " NOT NULL"
                        schema_lines.append(f"- {col}: {col_type}{primary_marker}{nullable_marker}")
                    
                    schema_lines.append("")
            
            schema_lines.append(self.EXAMPLE_QUERIES)
            schema_lines.append("\nIMPORTANT: Always include \"WHERE user_id = '{user_id}'\" in your queries.")
            schema_lines.append("Replace {user_id} with the actual user ID value.")
            
            self._schema_cache = "\n".join(schema_lines)
            return self._schema_cache
            
        except Exception as e:
            logger.error(f"Error generating schema documentation: {e}")
            # Return fallback schema if generation fails
            return self._get_fallback_schema()
    
    def _get_column_info(self, session, table_name: str) -> Dict[str, Dict]:
        """
        Get detailed column information including types and constraints.
        
        Returns:
            Dict mapping column_name -> {data_type, is_primary, is_nullable}
        """
        try:
            result = session.execute(
                text("""
                    SELECT 
                        c.column_name,
                        c.data_type,
                        c.is_nullable,
                        CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END as is_primary
                    FROM information_schema.columns c
                    LEFT JOIN (
                        SELECT ku.column_name
                        FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage ku
                            ON tc.constraint_name = ku.constraint_name
                            AND tc.table_schema = ku.table_schema
                        WHERE tc.constraint_type = 'PRIMARY KEY'
                            AND tc.table_name = :table_name
                            AND tc.table_schema = 'public'
                    ) pk ON c.column_name = pk.column_name
                    WHERE c.table_name = :table_name
                        AND c.table_schema = 'public'
                    ORDER BY c.ordinal_position
                """),
                {"table_name": table_name}
            ).fetchall()
            
            column_info = {}
            for row in result:
                column_info[row[0]] = {
                    'data_type': row[1].upper(),
                    'is_nullable': row[2] == 'YES',
                    'is_primary': row[3] if len(row) > 3 else False
                }
            
            return column_info
        except Exception as e:
            logger.warning(f"Could not get detailed column info for {table_name}: {e}")
            # Return basic info
            columns = get_table_columns(session, table_name)
            return {col: {'data_type': 'TEXT', 'is_nullable': True, 'is_primary': False} 
                   for col in columns}
    
    def _get_fallback_schema(self) -> str:
        """Return a fallback schema if dynamic generation fails."""
        return """DATABASE SCHEMA:

TABLE: promises (your goals/tasks)
- promise_uuid: TEXT (internal ID)
- user_id: TEXT (your user ID)
- current_id: TEXT (display ID like 'P10', 'T01')
- text: TEXT (promise name, underscores for spaces e.g. 'Do_sport')
- hours_per_week: REAL (target hours)
- recurring: INTEGER (0=one-time, 1=recurring)
- start_date: TEXT (ISO date 'YYYY-MM-DD')
- end_date: TEXT (ISO date)
- is_deleted: INTEGER (0=active, 1=deleted)
- created_at_utc: TEXT (ISO timestamp)

TABLE: actions (logged time entries)
- action_uuid: TEXT (internal ID)
- user_id: TEXT (your user ID)
- promise_uuid: TEXT (links to promises)
- promise_id_text: TEXT (display ID like 'P10')
- action_type: TEXT (usually 'log_time')
- time_spent_hours: REAL (hours logged)
- at_utc: TEXT (ISO timestamp when logged)

TABLE: sessions (active work sessions)
- session_id: TEXT
- user_id: TEXT
- promise_uuid: TEXT
- status: TEXT ('active', 'paused', 'ended')
- started_at_utc: TEXT
- ended_at_utc: TEXT
- paused_seconds_total: INTEGER

TABLE: users
- user_id: TEXT PRIMARY KEY
- timezone: TEXT
- language: TEXT
- nightly_hh: INTEGER (reminder hour)
- nightly_mm: INTEGER (reminder minute)

""" + self.EXAMPLE_QUERIES + "\nIMPORTANT: Always include \"WHERE user_id = '{user_id}'\" in your queries.\nReplace {user_id} with the actual user ID value."
