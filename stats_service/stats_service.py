#!/usr/bin/env python3
"""
FastAPI stats service for Zana AI bot.
Provides read-only stats endpoint for user activity metrics.
"""
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

# Add parent directory to path to import logger
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from tm_bot.utils.logger import get_logger

# Import stats logic from bot_stats.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from bot_stats import is_user_dir, file_info, count_users, active_within

app = FastAPI(title="Zana AI Stats Service", version="1.0.0")
logger = get_logger(__name__)

# Cache for stats (5 minutes)
_stats_cache: Optional[Dict] = None
_cache_timestamp: Optional[datetime] = None
CACHE_TTL = timedelta(minutes=5)


def get_users_data_dir() -> str:
    """Get users data directory from environment."""
    data_dir = os.getenv("USERS_DATA_DIR", "/app/USERS_DATA_DIR")
    if not os.path.exists(data_dir):
        logger.warning(f"Users data directory does not exist: {data_dir}")
    return data_dir


def compute_stats() -> Dict:
    """
    Compute statistics from user data directory.
    Reuses logic from bot_stats.py.
    """
    data_dir = get_users_data_dir()
    users = count_users(data_dir)
    now = datetime.now()
    
    total_users = len(users)
    users_with_promises = 0
    users_with_actions = 0
    
    # Activity windows
    windows = [7, 30, 90, 365]
    active_counts = {f"{d}d": 0 for d in windows}
    
    # New users (based on folder mtime)
    new_counts = {f"{d}d": 0 for d in [7, 30]}
    
    # Per-user details
    user_details: List[Dict] = []
    threshold_bytes = 12
    
    for uid in users:
        udir = os.path.join(data_dir, uid)
        
        # Promises.csv presence & size
        promises_path = os.path.join(udir, "promises.csv")
        pinfo = file_info(promises_path)
        has_promises = pinfo["exists"] and pinfo["bytes"] > threshold_bytes
        if has_promises:
            users_with_promises += 1
        
        # Actions.csv presence, size, and mtime
        actions_path = os.path.join(udir, "actions.csv")
        ainfo = file_info(actions_path)
        has_actions = ainfo["exists"] and ainfo["bytes"] > threshold_bytes
        last_activity = ainfo["mtime"].isoformat() if ainfo["mtime"] else None
        
        if has_actions:
            users_with_actions += 1
            for d in windows:
                if active_within(ainfo["mtime"], d, now):
                    active_counts[f"{d}d"] += 1
        
        # New users (directory mtime)
        try:
            dst = os.stat(udir)
            dir_mtime = datetime.fromtimestamp(dst.st_mtime)
            for d in [7, 30]:
                if active_within(dir_mtime, d, now):
                    new_counts[f"{d}d"] += 1
        except FileNotFoundError:
            pass
        
        # Add user detail
        user_details.append({
            "user_id": int(uid),
            "has_promises": has_promises,
            "has_actions": has_actions,
            "last_activity": last_activity,
        })
    
    return {
        "total_users": total_users,
        "users_with_promises": users_with_promises,
        "users_with_actions": users_with_actions,
        "active_last_7_days": active_counts["7d"],
        "active_last_30_days": active_counts["30d"],
        "active_users_by_actions_mtime": active_counts,
        "new_users_by_dir_mtime": new_counts,
        "details": user_details,
        "generated_at": now.isoformat(timespec="seconds"),
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "zana-stats"}


@app.get("/stats")
async def get_stats():
    """
    Get statistics about bot users.
    Returns cached results for 5 minutes to reduce filesystem I/O.
    """
    global _stats_cache, _cache_timestamp
    
    now = datetime.now()
    
    # Return cached stats if still valid
    if _stats_cache and _cache_timestamp and (now - _cache_timestamp) < CACHE_TTL:
        logger.debug("Returning cached stats")
        return _stats_cache
    
    try:
        stats = compute_stats()
        _stats_cache = stats
        _cache_timestamp = now
        
        # Log stats to Logtail
        logger.info({
            "event": "stats",
            "total_users": stats["total_users"],
            "active_users_7d": stats["active_last_7_days"],
            "active_users_30d": stats["active_last_30_days"],
            "users_with_promises": stats["users_with_promises"],
            "users_with_actions": stats["users_with_actions"],
        })
        
        return stats
    except Exception as e:
        logger.error({"event": "stats_error", "error": str(e)}, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to compute stats: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)