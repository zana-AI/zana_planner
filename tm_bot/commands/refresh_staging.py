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
