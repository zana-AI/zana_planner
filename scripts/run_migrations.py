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

def get_database_url() -> str:
    """
    Get database connection URL from environment.
    Simplified version that doesn't trigger bot initialization.
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
    
    raise ValueError(
        "No database URL found. Set DATABASE_URL_PROD, DATABASE_URL_STAGING, or DATABASE_URL"
    )

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
        return 0
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
