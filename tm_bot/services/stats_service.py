"""
Privacy-safe database statistics service.
Provides aggregate statistics for the version command.
Reuses logic from bot_stats.py to avoid duplication.
"""
import os
import sys
from typing import Dict

from utils.logger import get_logger

# Import bot_stats function (bot_stats.py is at project root)
# Add project root to path to import it
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    from bot_stats import get_version_stats
except ImportError:
    # Fallback if bot_stats is not available
    get_version_stats = None

logger = get_logger(__name__)


def get_aggregate_stats(root_dir: str) -> Dict[str, int]:
    """
    Get privacy-safe aggregate database statistics for version command.
    
    Returns:
        dict with keys:
        - total_users: Count of distinct users
        - total_promises: Count of active promises (is_deleted=0)
        - actions_24h: Count of actions in the last 24 hours
    
    Security:
        - Only uses aggregate COUNT queries
        - No user-specific data returned
        - Uses read-only database connection
        - Reuses logic from bot_stats.py
    """
    if not get_version_stats:
        logger.warning("bot_stats module not available, returning zero stats")
        return {
            "total_users": 0,
            "total_promises": 0,
            "actions_24h": 0,
        }
    
    try:
        return get_version_stats(root_dir)
    except Exception as e:
        logger.error(f"Error getting aggregate stats: {e}")
        return {
            "total_users": 0,
            "total_promises": 0,
            "actions_24h": 0,
        }

