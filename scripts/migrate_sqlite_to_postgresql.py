"""
Data migration script: Export SQLite data and import to PostgreSQL.

This script:
1. Connects to SQLite database
2. Exports all data to SQL format (PostgreSQL-compatible)
3. Imports data into PostgreSQL database
4. Handles SQL syntax differences between SQLite and PostgreSQL

Usage:
    python scripts/migrate_sqlite_to_postgresql.py --sqlite-path /path/to/zana.db --postgres-url postgresql://...

Or inside Docker (recommended), relying on env vars:
    # ENVIRONMENT=staging + DATABASE_URL_STAGING in env file
    python scripts/migrate_sqlite_to_postgresql.py
"""

import argparse
import os
import sqlite3
import sys
import re
from typing import Dict, List, Tuple

import psycopg2
from psycopg2.extras import execute_values
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from utils.logger import get_logger

logger = get_logger(__name__)

_SAFE_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _is_safe_ident(name: str) -> bool:
    return bool(name and _SAFE_IDENT_RE.match(name))


def sync_sequences(pg_session, table_names: List[str]) -> None:
    """
    After importing rows with explicit integer IDs, PostgreSQL sequences may be behind.
    This updates any serial/identity sequences for single-column primary keys.
    """
    for table_name in table_names:
        pk_cols = get_primary_key_columns(pg_session, table_name)
        if len(pk_cols) != 1:
            continue
        pk = pk_cols[0]
        if not (_is_safe_ident(table_name) and _is_safe_ident(pk)):
            continue

        seq_name = pg_session.execute(
            text("SELECT pg_get_serial_sequence(:tbl, :col)"),
            {"tbl": f"public.{table_name}", "col": pk},
        ).scalar()

        if not seq_name:
            continue

        # setval(seq, max(pk)) so next nextval() is max+1
        # NOTE: avoid ":seq::regclass" (bind params + casts can be finicky); use to_regclass(text) instead.
        pg_session.execute(
            text(
                f"SELECT setval(to_regclass(:seq), (SELECT COALESCE(MAX({pk}), 0) FROM {table_name}))"
            ),
            {"seq": str(seq_name)},
        )

    pg_session.commit()

def get_sqlite_tables(conn: sqlite3.Connection) -> List[str]:
    """Get list of all tables in SQLite database."""
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    return [row[0] for row in cursor.fetchall()]


def export_table_data(conn: sqlite3.Connection, table_name: str) -> List[Tuple]:
    """Export all data from a SQLite table."""
    cursor = conn.execute(f"SELECT * FROM {table_name};")
    columns = [description[0] for description in cursor.description]
    rows = cursor.fetchall()
    return columns, rows


def convert_sqlite_to_postgres_value(value) -> any:
    """Convert SQLite value to PostgreSQL-compatible value."""
    if value is None:
        return None
    if isinstance(value, bytes):
        # SQLite BLOB -> PostgreSQL BYTEA (as hex string)
        return value.hex()
    if isinstance(value, bool):
        # SQLite stores booleans as 0/1, PostgreSQL uses True/False
        return value
    return value


def get_primary_key_columns(pg_session, table_name: str) -> List[str]:
    """Get primary key column names for a table."""
    # Use information_schema to avoid regclass casts (which can be finicky with bind params).
    result = pg_session.execute(
        text(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = 'public'
              AND tc.table_name = :table_name
            ORDER BY kcu.ordinal_position
            """
        ),
        {"table_name": table_name},
    )
    return [row[0] for row in result.fetchall()]


def migrate_table(
    sqlite_conn: sqlite3.Connection,
    pg_session,
    table_name: str,
    batch_size: int = 1000
) -> int:
    """
    Migrate a single table from SQLite to PostgreSQL.
    
    Returns:
        Number of rows migrated
    """
    logger.info(f"Migrating table: {table_name}")
    
    # Get table schema from PostgreSQL
    result = pg_session.execute(
        text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = :table_name 
            ORDER BY ordinal_position
        """),
        {"table_name": table_name}
    )
    pg_columns = {row[0]: row[1] for row in result}
    
    if not pg_columns:
        logger.warning(f"Table {table_name} does not exist in PostgreSQL, skipping")
        return 0
    
    # Get primary key columns for ON CONFLICT clause
    pk_columns = get_primary_key_columns(pg_session, table_name)
    
    # Export data from SQLite
    columns, rows = export_table_data(sqlite_conn, table_name)
    
    if not rows:
        logger.info(f"  Table {table_name} is empty, skipping")
        return 0
    
    # Filter columns to only those that exist in PostgreSQL
    valid_columns = [col for col in columns if col in pg_columns]
    if not valid_columns:
        logger.warning(f"  No matching columns found for {table_name}, skipping")
        return 0
    
    # Ensure all primary key columns are in valid_columns
    missing_pk = [pk for pk in pk_columns if pk not in valid_columns]
    if missing_pk:
        logger.warning(f"  Primary key columns {missing_pk} not found in SQLite data, skipping")
        return 0
    
    # Convert data
    converted_rows = []
    for row in rows:
        row_dict = dict(zip(columns, row))
        converted_row = tuple(
            convert_sqlite_to_postgres_value(row_dict.get(col))
            for col in valid_columns
        )
        converted_rows.append(converted_row)
    
    # Insert into PostgreSQL in batches
    total_inserted = 0
    for i in range(0, len(converted_rows), batch_size):
        batch = converted_rows[i:i + batch_size]
        columns_str = ", ".join(valid_columns)
        placeholders = ", ".join([f":{col}" for col in valid_columns])
        
        # Build ON CONFLICT clause if we have primary keys
        if pk_columns:
            conflict_clause = f"ON CONFLICT ({', '.join(pk_columns)}) DO NOTHING"
        else:
            conflict_clause = ""  # No primary key, just try to insert
        
        insert_sql = f"""
            INSERT INTO {table_name} ({columns_str})
            VALUES ({placeholders})
            {conflict_clause}
        """
        
        try:
            for row in batch:
                params = dict(zip(valid_columns, row))
                pg_session.execute(text(insert_sql), params)
            pg_session.commit()
            total_inserted += len(batch)
            logger.info(f"  Inserted {total_inserted}/{len(converted_rows)} rows")
        except Exception as e:
            logger.error(f"  Error inserting batch: {e}")
            pg_session.rollback()
            raise
    
    logger.info(f"  ✓ Migrated {total_inserted} rows from {table_name}")
    return total_inserted


def main():
    parser = argparse.ArgumentParser(description="Migrate data from SQLite to PostgreSQL")
    parser.add_argument(
        "--sqlite-path",
        required=False,
        default=None,
        help="Path to SQLite database file (default: USERS_DATA_DIR/zana.db inside containers)",
    )
    parser.add_argument(
        "--postgres-url",
        required=False,
        default=None,
        help="PostgreSQL connection URL (default: derived from ENVIRONMENT + DATABASE_URL_* env vars)",
    )
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for inserts")
    parser.add_argument("--tables", nargs="+", help="Specific tables to migrate (default: all)")
    args = parser.parse_args()

    # Resolve defaults from environment to make container usage simpler
    sqlite_path = args.sqlite_path
    if not sqlite_path:
        try:
            from tm_bot.db.sqlite_db import resolve_db_path

            # Prefer USERS_DATA_DIR (compose mounts it), then ROOT_DIR, else default container path
            base_root = os.getenv("USERS_DATA_DIR") or os.getenv("ROOT_DIR") or "/app/USERS_DATA_DIR"
            sqlite_path = resolve_db_path(base_root)
        except Exception:
            sqlite_path = "/app/USERS_DATA_DIR/zana.db"

    postgres_url = args.postgres_url
    if not postgres_url:
        from tm_bot.db.postgres_db import get_database_url

        postgres_url = get_database_url()
    
    # Validate SQLite file
    if not os.path.exists(sqlite_path):
        logger.error(f"SQLite database not found: {sqlite_path}")
        sys.exit(1)
    
    # Connect to SQLite
    logger.info(f"Connecting to SQLite: {sqlite_path}")
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    
    # Connect to PostgreSQL
    logger.info(f"Connecting to PostgreSQL...")
    engine = create_engine(postgres_url)
    SessionLocal = sessionmaker(bind=engine)
    pg_session = SessionLocal()
    
    try:
        # Get list of tables to migrate
        if args.tables:
            tables_to_migrate = args.tables
        else:
            tables_to_migrate = get_sqlite_tables(sqlite_conn)
            # Exclude schema_version (will be handled separately)
            tables_to_migrate = [t for t in tables_to_migrate if t != "schema_version"]
        
        logger.info(f"Tables to migrate: {', '.join(tables_to_migrate)}")
        
        # Migrate each table
        total_rows = 0
        for table_name in tables_to_migrate:
            try:
                rows = migrate_table(sqlite_conn, pg_session, table_name, args.batch_size)
                total_rows += rows
            except Exception as e:
                logger.error(f"Failed to migrate {table_name}: {e}")
                raise

        # Fix sequences for autoincrement PKs (e.g., conversations.id) after import
        try:
            logger.info("Syncing PostgreSQL sequences after import...")
            sync_sequences(pg_session, tables_to_migrate)
            logger.info("✓ Sequences synced")
        except Exception as e:
            logger.warning(f"Sequence sync failed (may be safe to ignore): {e}")
        
        logger.info(f"✓ Migration complete! Total rows migrated: {total_rows}")
        
    finally:
        sqlite_conn.close()
        pg_session.close()


if __name__ == "__main__":
    main()
