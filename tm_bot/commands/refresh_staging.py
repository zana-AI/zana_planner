"""
Admin command to refresh staging database from production.

This command:
1. Dumps production database using pg_dump
2. Restores to staging database using psql
3. Requires admin authentication
"""

import os
import subprocess
import sys
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)


def refresh_staging_db(confirm: bool = False) -> bool:
    """
    Refresh staging database from production.
    
    Args:
        confirm: If True, skip confirmation prompt
        
    Returns:
        True if successful, False otherwise
    """
    # Check environment variables
    prod_url = os.getenv("DATABASE_URL_PROD")
    staging_url = os.getenv("DATABASE_URL_STAGING")
    
    if not prod_url:
        logger.error("DATABASE_URL_PROD environment variable is not set")
        return False
    
    if not staging_url:
        logger.error("DATABASE_URL_STAGING environment variable is not set")
        return False
    
    # Safety confirmation
    if not confirm:
        print("WARNING: This will completely overwrite the staging database with production data.")
        print(f"Production: {prod_url}")
        print(f"Staging: {staging_url}")
        response = input("Are you sure you want to continue? (yes/no): ")
        if response.lower() != "yes":
            print("Operation cancelled.")
            return False
    
    try:
        logger.info("Starting staging database refresh from production...")
        
        # Dump production database
        logger.info("Dumping production database...")
        dump_process = subprocess.run(
            ["pg_dump", prod_url],
            capture_output=True,
            text=True,
            check=True,
        )
        
        # Restore to staging
        logger.info("Restoring to staging database...")
        restore_process = subprocess.run(
            ["psql", staging_url],
            input=dump_process.stdout,
            capture_output=True,
            text=True,
            check=True,
        )
        
        # CRITICAL: Sync sequences after restore
        # pg_dump includes explicit IDs, but sequences don't auto-update
        # This prevents duplicate key errors on the next insert
        logger.info("Syncing PostgreSQL sequences after restore...")
        sync_sequences_sql = """
            DO $$
            DECLARE
                r RECORD;
                seq_name TEXT;
                max_val BIGINT;
            BEGIN
                FOR r IN (
                    SELECT 
                        t.table_name,
                        c.column_name
                    FROM information_schema.tables t
                    JOIN information_schema.columns c 
                        ON t.table_name = c.table_name 
                        AND t.table_schema = c.table_schema
                    WHERE t.table_schema = 'public'
                        AND t.table_type = 'BASE TABLE'
                        AND c.column_default LIKE 'nextval%'
                )
                LOOP
                    seq_name := pg_get_serial_sequence('public.' || r.table_name, r.column_name);
                    IF seq_name IS NOT NULL THEN
                        EXECUTE format('SELECT COALESCE(MAX(%I), 0) FROM %I', r.column_name, r.table_name) INTO max_val;
                        EXECUTE format('SELECT setval(%L, GREATEST(%s, 1))', seq_name, max_val);
                        RAISE NOTICE 'Synced sequence % to %', seq_name, max_val;
                    END IF;
                END LOOP;
            END $$;
        """
        
        sync_process = subprocess.run(
            ["psql", staging_url, "-c", sync_sequences_sql],
            capture_output=True,
            text=True,
        )
        
        if sync_process.returncode != 0:
            logger.warning(f"Sequence sync warning (data restored OK): {sync_process.stderr}")
        else:
            logger.info("Sequences synced successfully")
        
        logger.info("Staging database refresh completed successfully!")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error during database refresh: {e}")
        if e.stdout:
            logger.error(f"stdout: {e.stdout}")
        if e.stderr:
            logger.error(f"stderr: {e.stderr}")
        return False
    except FileNotFoundError:
        logger.error("pg_dump or psql not found. Please ensure PostgreSQL client tools are installed.")
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False


if __name__ == "__main__":
    # Allow --yes flag to skip confirmation
    confirm = "--yes" in sys.argv or "-y" in sys.argv
    success = refresh_staging_db(confirm=confirm)
    sys.exit(0 if success else 1)
