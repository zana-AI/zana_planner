#!/usr/bin/env python3
"""
FastAPI stats service for Xaana AI bot.
Provides read-only stats endpoint for user activity metrics.
"""
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

# Add parent directory to path to import logger
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from tm_bot.utils.logger import get_logger

# Import stats logic from bot_stats.py (SQLite-based)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from bot_stats import compute_stats_sql

app = FastAPI(title="Xaana AI Stats Service", version="1.0.0")
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
    Compute statistics from SQLite in the user data directory.
    Reuses logic from bot_stats.py.
    """
    data_dir = get_users_data_dir()
    return compute_stats_sql(data_dir)


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