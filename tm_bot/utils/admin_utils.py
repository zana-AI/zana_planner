"""
Admin utility functions for checking admin status.
"""
import os
from typing import Set
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Cache admin IDs to avoid repeated parsing
_admin_ids_cache: Set[int] = None


def _load_admin_ids() -> Set[int]:
    """Load admin IDs from environment variable."""
    global _admin_ids_cache
    
    if _admin_ids_cache is not None:
        return _admin_ids_cache
    
    admin_ids_str = os.getenv("ADMIN_IDS", "")
    if not admin_ids_str:
        _admin_ids_cache = set()
        return _admin_ids_cache
    
    # Parse comma-separated admin IDs
    admin_ids = set()
    for admin_id_str in admin_ids_str.split(","):
        admin_id_str = admin_id_str.strip()
        if admin_id_str:
            try:
                admin_ids.add(int(admin_id_str))
            except ValueError:
                # Skip invalid admin IDs
                pass
    
    _admin_ids_cache = admin_ids
    return _admin_ids_cache


def is_admin(user_id: int) -> bool:
    """
    Check if a user is an admin.
    
    Args:
        user_id: Telegram user ID to check
        
    Returns:
        True if user is an admin, False otherwise
    """
    admin_ids = _load_admin_ids()
    return user_id in admin_ids


def get_admin_ids() -> Set[int]:
    """
    Get all admin IDs.
    
    Returns:
        Set of admin user IDs
    """
    return _load_admin_ids().copy()
