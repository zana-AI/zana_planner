"""
Service for executing read-only SQL queries with security validation.
"""
import re
from typing import List, Dict, Tuple, Optional

from db.postgres_db import get_db_session
from sqlalchemy import text
from utils.logger import get_logger

logger = get_logger(__name__)


class QueryService:
    """Service for executing validated read-only SQL queries."""
    
    # Tables that have user_id column and should be accessible
    USER_TABLES = [
        "promises",
        "actions",
        "sessions",
        "users",
        "promise_aliases",
        "promise_events",
    ]
    
    def validate_and_execute_query(
        self, 
        sql_query: str, 
        user_id: str,
        auto_inject_user_id: bool = True
    ) -> Tuple[bool, Optional[List[Dict]], Optional[str]]:
        """
        Validate and execute a read-only SQL query with user isolation.
        
        Args:
            sql_query: The SQL query string
            user_id: The authenticated user ID
            auto_inject_user_id: If True, automatically replace {user_id} placeholders
        
        Returns:
            Tuple of (success: bool, results: List[Dict] or None, error_message: str or None)
        """
        if not sql_query or not sql_query.strip():
            return (False, None, "Please provide a SQL query.")
        
        safe_user_id = str(user_id).strip()
        if not safe_user_id.isdigit():
            return (False, None, "Invalid user ID.")
        
        # Auto-inject user_id for common placeholder patterns
        original_query = sql_query
        if auto_inject_user_id:
            placeholder_patterns = [
                (r"'\{user_id\}'", f"'{safe_user_id}'"),         # '{user_id}'
                (r'"\{user_id\}"', f"'{safe_user_id}'"),         # "{user_id}"
                (r"\{user_id\}", f"'{safe_user_id}'"),           # {user_id} unquoted
            ]
            for pattern, replacement in placeholder_patterns:
                sql_query = re.sub(pattern, replacement, sql_query, flags=re.IGNORECASE)
            
            if sql_query != original_query:
                logger.info(
                    f"[query_service] Auto-injected user_id={safe_user_id}. "
                    f"Original: {original_query[:150]}..."
                )
        
        # Validate the query
        is_valid, sanitized_query, error_msg = self._validate_sql_query(sql_query, safe_user_id)
        if not is_valid:
            return (False, None, f"Query rejected: {error_msg}")
        
        # Check that user_id filter is present in the query
        query_upper = sanitized_query.upper()
        if "USER_ID" not in query_upper:
            return (
                False,
                None,
                f"Query rejected: Your query must include a user_id filter. "
                f"Add \"WHERE user_id = '{safe_user_id}'\" to your query."
            )
        
        # SECURITY: Ensure every user_id referenced in the query is the authenticated user.
        # Scan all occurrences (handles UNION, subqueries, forged SELECT, user_id IN (...)).
        user_id_patterns = [
            re.compile(r"user_id\s*=\s*'([^']*)'", re.IGNORECASE),
            re.compile(r'user_id\s*=\s*"([^"]*)"', re.IGNORECASE),
            re.compile(r"user_id\s*=\s*(\d+)", re.IGNORECASE),
        ]
        found_ids = set()
        for pat in user_id_patterns:
            for match in pat.finditer(sanitized_query):
                found_ids.add(match.group(1).strip())
        # Also extract user_id values from IN (...) e.g. user_id IN ('id1', 'id2')
        in_clause = re.compile(r"user_id\s+IN\s*\(\s*([^)]+)\s*\)", re.IGNORECASE)
        for match in in_clause.finditer(sanitized_query):
            inner = match.group(1)
            for lit in re.findall(r"'([^']*)'", inner):
                found_ids.add(lit.strip())
            for lit in re.findall(r'"([^"]*)"', inner):
                found_ids.add(lit.strip())
            for lit in re.findall(r"\b(\d+)\b", inner):
                found_ids.add(lit)
        for found_id in found_ids:
            if found_id != safe_user_id:
                logger.warning(
                    f"[query_service] SECURITY: Query user_id mismatch! "
                    f"Authenticated user: {safe_user_id}, Query attempted for: {found_id}. "
                    f"Original query: {original_query[:200]}. "
                    f"After auto-inject: {sanitized_query[:200]}"
                )
                return (False, None, "Query rejected: You can only query your own data. Access to other users' data is not allowed.")
        
        # Execute the query
        success, result = self._execute_readonly_query(sanitized_query, safe_user_id)
        
        if not success:
            return (False, None, f"Query failed: {result}")
        
        return (True, result, None)
    
    def format_query_results(self, results: List[Dict], max_rows: int = 100) -> str:
        """
        Format query results as readable text.
        
        Args:
            results: List of dicts representing query results
            max_rows: Maximum number of rows to display
        
        Returns:
            Formatted string representation of results
        """
        if not results:
            return "Query returned no results."
        
        output_lines = [f"Query returned {len(results)} row(s):\n"]
        
        # Get column names from first result
        columns = list(results[0].keys())
        
        # Build a simple table format
        display_rows = results[:max_rows]
        for i, row in enumerate(display_rows):
            row_parts = []
            for col in columns:
                val = row.get(col)
                if val is None:
                    val = "NULL"
                elif isinstance(val, float):
                    val = f"{val:.2f}"
                row_parts.append(f"{col}: {val}")
            output_lines.append(f"  [{i+1}] {', '.join(row_parts)}")
        
        if len(results) > max_rows:
            output_lines.append(f"\n  ... and {len(results) - max_rows} more rows (truncated)")
        
        return "\n".join(output_lines)
    
    def _validate_sql_query(self, query: str, user_id: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate and sanitize SQL query for safe execution.
        
        Security checks:
        1. Only SELECT statements allowed (whitelist)
        2. Dangerous keywords blocked (blacklist as secondary defense)
        3. User ID filter enforced
        4. LIMIT clause added if missing
        
        Args:
            query: The SQL query string to validate
            user_id: The user ID that must be enforced in the query
            
        Returns:
            Tuple of (is_valid: bool, sanitized_query: str or None, error_msg: str or None)
            - If valid: (True, sanitized_query, None)
            - If invalid: (False, None, error_message)
        """
        if not query or not query.strip():
            return (False, None, "Query cannot be empty.")
        
        # Normalize query
        normalized = query.strip()
        query_upper = normalized.upper()
        
        # WHITELIST: Must start with SELECT
        if not query_upper.startswith("SELECT"):
            return (False, None, "Only SELECT queries are allowed. Query must start with SELECT.")
        
        # BLACKLIST: Block dangerous keywords as secondary defense
        dangerous_keywords = [
            "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", 
            "TRUNCATE", "REPLACE", "GRANT", "REVOKE", "ATTACH", "DETACH",
            "PRAGMA", "VACUUM", "REINDEX", "--", "/*", "*/", ";"
        ]
        
        # Check for dangerous keywords (but allow them in string literals)
        for keyword in dangerous_keywords:
            if keyword == ";":
                # Special handling: only allow one statement (no semicolons except at end)
                semicolon_count = normalized.count(";")
                if semicolon_count > 1 or (semicolon_count == 1 and not normalized.rstrip().endswith(";")):
                    return (False, None, "Multiple statements are not allowed.")
            elif keyword in query_upper:
                # More sophisticated check: make sure it's not inside a string
                parts = query_upper.replace("''", "").split("'")
                for i, part in enumerate(parts):
                    if i % 2 == 0 and keyword in part:  # Outside quotes
                        return (False, None, f"Dangerous keyword '{keyword}' is not allowed.")
        
        # Remove trailing semicolon for cleaner processing
        if normalized.rstrip().endswith(";"):
            normalized = normalized.rstrip()[:-1].strip()
        
        # Check if LIMIT is present, add if not (cap at 100)
        if "LIMIT" not in query_upper:
            normalized = f"{normalized} LIMIT 100"
        else:
            # Ensure existing LIMIT is not too high
            limit_match = re.search(r'LIMIT\s+(\d+)', query_upper)
            if limit_match:
                limit_val = int(limit_match.group(1))
                if limit_val > 100:
                    # Replace with max 100
                    normalized = re.sub(r'LIMIT\s+\d+', 'LIMIT 100', normalized, flags=re.IGNORECASE)
        
        return (True, normalized, None)
    
    def _execute_readonly_query(self, query: str, user_id: str) -> Tuple[bool, List[Dict] | str]:
        """
        Execute a validated read-only query with enforced user_id filtering.
        
        CRITICAL SECURITY: This method rewrites the query to ALWAYS filter by user_id.
        The user_id is passed as a parameter, never interpolated into the query string.
        
        Args:
            query: The validated SQL query (must be SELECT)
            user_id: The user ID to enforce in the query
            
        Returns:
            Tuple of (success: bool, result: list[dict] or error_message: str)
        """
        safe_user_id = str(user_id).strip()
        if not safe_user_id.isdigit():
            return (False, "Invalid user ID.")
        
        try:
            query_upper = query.upper()
            
            # Check which tables are referenced in the query
            referenced_tables = []
            for table in self.USER_TABLES:
                if table.upper() in query_upper:
                    referenced_tables.append(table)
            
            if not referenced_tables:
                return (False, "Query must reference at least one user data table (promises, actions, sessions, users).")
            
            # SECURITY: Always enforce user_id filtering at the SQL level.
            # Wrap the original query and add a parameterized user_id predicate.
            # This prevents cross-user leaks even if the model omits WHERE user_id.
            wrapped_query = f"SELECT * FROM ({query}) AS q WHERE q.user_id = :user_id"
            
            with get_db_session() as session:
                result = session.execute(text(wrapped_query), {"user_id": safe_user_id})
                rows = result.mappings().fetchall()
                
                # Convert to list of dicts
                results = [dict(row) for row in rows]
                
                return (True, results)
                
        except Exception as e:
            logger.error(f"SQL query execution error: {e}")
            # Don't leak internal error details to user
            error_msg = str(e)
            if "user_id" in error_msg.lower() and "column" in error_msg.lower():
                return (
                    False,
                    "Query must include user_id in the selected columns so access can be enforced.",
                )
            if "syntax error" in error_msg.lower():
                return (False, "SQL syntax error. Please check your query.")
            elif "no such table" in error_msg.lower():
                return (False, "Referenced table does not exist.")
            elif "no such column" in error_msg.lower():
                return (False, "Referenced column does not exist.")
            else:
                return (False, "Query execution failed. Please check your query syntax.")
