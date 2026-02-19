#!/usr/bin/env python3
"""
Run Alembic migrations for PostgreSQL database.

This script can be run from the host or inside a container.
It reads the database URL from environment variables.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import only what we need for migrations (avoid bot initialization)
from alembic.config import Config
from alembic import command

# Import get_database_url directly to avoid triggering bot initialization
import os as os_module

def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines into os.environ. Skips empty lines and # comments."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os_module.environ[key] = value

def get_database_url() -> str:
    """
    Get database connection URL from environment.
    If not set, tries loading ZANA_ENV_FILE or /opt/zana-config/.env.prod.
    ENVIRONMENT on the command line (e.g. ENVIRONMENT=staging) is preserved over file contents.
    """
    env = os_module.getenv("ENVIRONMENT", "").lower()

    if env in ("production", "prod"):
        url = os_module.getenv("DATABASE_URL_PROD")
        if url:
            return url

    if env in ("staging", "stage") or not env:
        url = os_module.getenv("DATABASE_URL_STAGING")
        if url:
            return url

    # Fallback to generic DATABASE_URL
    url = os_module.getenv("DATABASE_URL")
    if url:
        return url

    # Try loading env file so ENVIRONMENT=staging python run_migrations.py works
    env_file = os_module.getenv("ZANA_ENV_FILE")
    if env_file:
        _load_env_file(Path(env_file))
    else:
        _load_env_file(Path("/opt/zana-config/.env.prod"))
    # Retry using original env (command-line ENVIRONMENT=staging wins over file)
    if env in ("production", "prod"):
        url = os_module.getenv("DATABASE_URL_PROD")
        if url:
            return url
    if env in ("staging", "stage") or not env:
        url = os_module.getenv("DATABASE_URL_STAGING")
        if url:
            return url
    url = os_module.getenv("DATABASE_URL")
    if url:
        return url

    raise ValueError(
        "No database URL found. Set DATABASE_URL_PROD, DATABASE_URL_STAGING, or DATABASE_URL"
    )


def _print_table_counts(database_url: str) -> None:
    """Print name and row count for all tables in the public schema."""
    try:
        import psycopg2
        from psycopg2 import sql
    except ImportError:
        print("(Install psycopg2 to see table counts)")
        return
    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        tables = [row[0] for row in cur.fetchall()]
        if not tables:
            print("No tables in public schema.")
            cur.close()
            conn.close()
            return
        print("\nTable row counts:")
        max_name = max(len(t) for t in tables)
        for name in tables:
            cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(name)))
            count = cur.fetchone()[0]
            print(f"  {name:<{max_name}}  {count:>10,} rows")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"(Could not list table counts: {e})")


def main():
    """Run Alembic migrations."""
    # Get the alembic directory
    alembic_dir = project_root / "tm_bot" / "db" / "alembic"
    alembic_ini = project_root / "tm_bot" / "db" / "alembic.ini"
    
    if not alembic_ini.exists():
        print(f"Error: alembic.ini not found at {alembic_ini}")
        sys.exit(1)
    
    # Create Alembic config
    alembic_cfg = Config(str(alembic_ini))
    
    # Set the database URL directly in the config
    # This avoids importing postgres_db which might trigger bot initialization
    database_url = get_database_url()
    # Mask password in output
    safe_url = database_url.split('@')[1] if '@' in database_url else '***'
    print(f"Using database: {safe_url}")
    
    # Set the URL in Alembic config (env.py will override this, but we set it here too)
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    
    # Run migrations
    print("Running Alembic migrations...")
    try:
        command.upgrade(alembic_cfg, "head")
        print("✓ Migrations completed successfully!")
        _print_table_counts(database_url)
        return 0
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
