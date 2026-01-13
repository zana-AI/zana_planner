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

from alembic.config import Config
from alembic import command
from tm_bot.db.postgres_db import get_database_url

def main():
    """Run Alembic migrations."""
    # Get the alembic directory
    alembic_dir = project_root / "tm_bot" / "db" / "alembic"
    alembic_ini = alembic_dir / "alembic.ini"
    
    if not alembic_ini.exists():
        print(f"Error: alembic.ini not found at {alembic_ini}")
        sys.exit(1)
    
    # Create Alembic config
    alembic_cfg = Config(str(alembic_ini))
    
    # Set the database URL (env.py will use get_database_url() which reads from env)
    database_url = get_database_url()
    print(f"Using database: {database_url.split('@')[1] if '@' in database_url else '***'}")
    
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
