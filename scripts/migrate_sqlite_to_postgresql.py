"""
Data migration script: Export SQLite data and import to PostgreSQL.

This script:
1. Connects to SQLite database
2. Exports all data to SQL format (PostgreSQL-compatible)
3. Imports data into PostgreSQL database
4. Handles SQL syntax differences between SQLite and PostgreSQL

Usage:
    python scripts/migrate_sqlite_to_postgresql.py --sqlite-path /path/to/zana.db --postgres-url postgresql://...
"""

import argparse
import os
import sqlite3
import sys
from typing import Dict, List, Tuple

import psycopg2
from psycopg2.extras import execute_values
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from utils.logger import get_logger

logger = get_logger(__name__)


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
    result = pg_session.execute(
        text("""
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = :table_name::regclass
            AND i.indisprimary
            ORDER BY a.attnum
        """),
        {"table_name": table_name}
    )
    return [row[0] for row in result]


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
    parser.add_argument("--sqlite-path", required=True, help="Path to SQLite database file")
    parser.add_argument("--postgres-url", required=True, help="PostgreSQL connection URL")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for inserts")
    parser.add_argument("--tables", nargs="+", help="Specific tables to migrate (default: all)")
    args = parser.parse_args()
    
    # Validate SQLite file
    if not os.path.exists(args.sqlite_path):
        logger.error(f"SQLite database not found: {args.sqlite_path}")
        sys.exit(1)
    
    # Connect to SQLite
    logger.info(f"Connecting to SQLite: {args.sqlite_path}")
    sqlite_conn = sqlite3.connect(args.sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    
    # Connect to PostgreSQL
    logger.info(f"Connecting to PostgreSQL...")
    engine = create_engine(args.postgres_url)
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
        
        logger.info(f"✓ Migration complete! Total rows migrated: {total_rows}")
        
    finally:
        sqlite_conn.close()
        pg_session.close()


if __name__ == "__main__":
    main()
