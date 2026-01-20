#!/usr/bin/env python3
"""
Fix the conversations table sequence if it's out of sync.

This script fixes the PostgreSQL sequence for the conversations table
by setting it to the maximum ID currently in the table.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from tm_bot.db.postgres_db import get_db_session
from utils.logger import get_logger

logger = get_logger(__name__)


def fix_conversations_sequence() -> None:
    """Fix the conversations table sequence."""
    try:
        with get_db_session() as session:
            # Get current max ID
            result = session.execute(
                text("SELECT COALESCE(MAX(id), 0) FROM conversations")
            ).scalar()
            max_id = result or 0
            
            logger.info(f"Current max ID in conversations table: {max_id}")
            
            # Fix the sequence
            session.execute(
                text("""
                    SELECT setval('conversations_id_seq', 
                        GREATEST(:max_id, 1), 
                        false)
                """),
                {"max_id": max_id}
            )
            
            # Verify the fix
            next_val = session.execute(
                text("SELECT nextval('conversations_id_seq')")
            ).scalar()
            
            # Reset it back (since we just consumed one)
            session.execute(
                text("SELECT setval('conversations_id_seq', :next_val - 1, false)"),
                {"next_val": next_val}
            )
            
            logger.info(f"Fixed conversations sequence. Next ID will be: {max_id + 1}")
            
    except Exception as e:
        logger.error(f"Failed to fix conversations sequence: {e}")
        raise


if __name__ == "__main__":
    try:
        fix_conversations_sequence()
        print("✓ Successfully fixed conversations sequence")
        sys.exit(0)
    except Exception as e:
        print(f"✗ Failed to fix conversations sequence: {e}")
        sys.exit(1)
