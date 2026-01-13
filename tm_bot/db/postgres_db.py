from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

# Re-export utility functions for backward compatibility
from db.sqlite_db import (
    date_from_iso,
    date_to_iso,
    dt_from_utc_iso,
    dt_to_utc_iso,
    dt_utc_iso_to_local_naive,
    json_compat,
    utc_now_iso,
)


def get_database_url() -> str:
    """
    Get database connection URL from environment.
    
    Determines environment from ENVIRONMENT variable:
    - 'production' or 'prod' -> DATABASE_URL_PROD
    - 'staging' or 'stage' -> DATABASE_URL_STAGING
    - default -> DATABASE_URL_STAGING (for safety)
    
    Falls back to DATABASE_URL if specific env vars not set.
    """
    env = os.getenv("ENVIRONMENT", "").lower()
    
    if env in ("production", "prod"):
        url = os.getenv("DATABASE_URL_PROD")
        if url:
            return url
    
    if env in ("staging", "stage") or not env:
        url = os.getenv("DATABASE_URL_STAGING")
        if url:
            return url
    
    # Fallback to generic DATABASE_URL
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    
    raise ValueError(
        "No database URL found. Set DATABASE_URL_PROD, DATABASE_URL_STAGING, or DATABASE_URL"
    )


# Global engine and session factory (lazy initialization)
_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def get_engine() -> Engine:
    """Get or create SQLAlchemy engine with connection pooling."""
    global _engine
    if _engine is None:
        database_url = get_database_url()
        _engine = create_engine(
            database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=3600,  # Recycle connections after 1 hour
            echo=False,  # Set to True for SQL debugging
        )
    return _engine


def get_session_factory() -> sessionmaker:
    """Get or create session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _SessionLocal


@contextmanager
def get_db_session() -> Iterator[Session]:
    """
    Context manager for database sessions.
    
    Replaces connection_for_root() for PostgreSQL.
    Automatically commits on success, rolls back on exception.
    """
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def resolve_promise_uuid(session: Session, user_id: str, promise_id: Optional[str]) -> Optional[str]:
    """
    Resolve promise UUID from promise_id (current_id or alias).
    
    PostgreSQL version of the SQLite function.
    """
    pid = (promise_id or "").strip().upper()
    if not pid:
        return None
    
    # Try current_id first
    result = session.execute(
        text("SELECT promise_uuid FROM promises WHERE user_id = :user_id AND current_id = :pid LIMIT 1"),
        {"user_id": user_id, "pid": pid}
    ).fetchone()
    
    if result and result[0]:
        return str(result[0])
    
    # Try alias
    result = session.execute(
        text("SELECT promise_uuid FROM promise_aliases WHERE user_id = :user_id AND alias_id = :pid LIMIT 1"),
        {"user_id": user_id, "pid": pid}
    ).fetchone()
    
    if result and result[0]:
        return str(result[0])
    
    return None


def check_table_exists(session: Session, table_name: str) -> bool:
    """Check if a table exists in the database."""
    result = session.execute(
        text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = :table_name
            )
        """),
        {"table_name": table_name}
    ).scalar()
    return bool(result)


def get_table_columns(session: Session, table_name: str) -> list[str]:
    """Get list of column names for a table."""
    result = session.execute(
        text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = :table_name
            ORDER BY ordinal_position
        """),
        {"table_name": table_name}
    ).fetchall()
    return [row[0] for row in result]


def check_view_exists(session: Session, view_name: str) -> bool:
    """Check if a view exists in the database."""
    result = session.execute(
        text("""
            SELECT EXISTS (
                SELECT FROM information_schema.views 
                WHERE table_schema = 'public' 
                AND table_name = :view_name
            )
        """),
        {"view_name": view_name}
    ).scalar()
    return bool(result)
