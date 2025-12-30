"""
FastAPI job scheduler implementation.

Uses asyncio for scheduling jobs in a FastAPI context.
"""

from typing import Callable, Optional, Dict, Any
from datetime import datetime, time
import asyncio

from ..interfaces import IJobScheduler
from ..types import JobContext
from utils.logger import get_logger

logger = get_logger(__name__)


class FastAPIJobScheduler(IJobScheduler):
    """
    Job scheduler for FastAPI platform using asyncio.
    """
    
    def __init__(self):
        """Initialize FastAPI job scheduler."""
        self._jobs: Dict[str, asyncio.Task] = {}
        self._running = True
    
    def schedule_daily(
        self,
        user_id: int,
        tz: str,
        callback: Callable,
        hh: int = 22,
        mm: int = 0,
        name_prefix: str = "job",
    ) -> None:
        """Schedule a daily recurring job for a user."""
        name = f"{name_prefix}-{user_id}"
        
        # Cancel existing job if any
        if name in self._jobs:
            self.cancel_job(name)
        
        # Create daily job task
        task = asyncio.create_task(self._daily_job_loop(name, user_id, tz, callback, hh, mm))
        self._jobs[name] = task
        logger.info(f"Scheduled daily job {name} for user {user_id} at {hh:02d}:{mm:02d}")
    
    async def _daily_job_loop(
        self,
        name: str,
        user_id: int,
        tz: str,
        callback: Callable,
        hh: int,
        mm: int,
    ) -> None:
        """Run daily job loop."""
        import pytz
        
        try:
            # Try zoneinfo first (Python 3.9+)
            try:
                from zoneinfo import ZoneInfo
                timezone = ZoneInfo(tz)
            except (ImportError, ValueError):
                # Fallback to pytz
                timezone = pytz.timezone(tz)
        except Exception:
            timezone = pytz.UTC
        
        while self._running:
            try:
                # Calculate next run time
                now = datetime.now(timezone)
                target_time = time(hh, mm)
                next_run = datetime.combine(now.date(), target_time).replace(tzinfo=timezone)
                
                # If time has passed today, schedule for tomorrow
                if next_run <= now:
                    from datetime import timedelta
                    next_run += timedelta(days=1)
                
                # Wait until next run time
                wait_seconds = (next_run - now).total_seconds()
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
                
                # Execute callback
                context = JobContext(
                    user_id=user_id,
                    data={"scheduled_time": next_run.isoformat()}
                )
                
                if asyncio.iscoroutinefunction(callback):
                    await callback(context)
                else:
                    callback(context)
                
                # Wait until next day
                await asyncio.sleep(86400)  # 24 hours
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in daily job {name}: {e}", exc_info=True)
                await asyncio.sleep(3600)  # Wait 1 hour before retrying
    
    def schedule_once(
        self,
        name: str,
        callback: Callable,
        when_dt: datetime,
        data: Optional[dict] = None,
    ) -> None:
        """Schedule a one-time job."""
        if name in self._jobs:
            self.cancel_job(name)
        
        task = asyncio.create_task(self._once_job(name, callback, when_dt, data))
        self._jobs[name] = task
        logger.info(f"Scheduled one-time job {name} for {when_dt}")
    
    async def _once_job(
        self,
        name: str,
        callback: Callable,
        when_dt: datetime,
        data: Optional[dict],
    ) -> None:
        """Execute a one-time job."""
        try:
            now = datetime.now(when_dt.tzinfo) if when_dt.tzinfo else datetime.now()
            wait_seconds = (when_dt - now).total_seconds()
            
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            
            context = JobContext(user_id=data.get("user_id", 0) if data else 0, data=data or {})
            
            if asyncio.iscoroutinefunction(callback):
                await callback(context)
            else:
                callback(context)
            
            # Remove job after execution
            if name in self._jobs:
                del self._jobs[name]
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in one-time job {name}: {e}", exc_info=True)
        finally:
            if name in self._jobs:
                del self._jobs[name]
    
    def schedule_repeating(
        self,
        name: str,
        callback: Callable,
        seconds: int,
        data: Optional[dict] = None,
    ) -> None:
        """Schedule a repeating job."""
        if name in self._jobs:
            self.cancel_job(name)
        
        task = asyncio.create_task(self._repeating_job(name, callback, seconds, data))
        self._jobs[name] = task
        logger.info(f"Scheduled repeating job {name} every {seconds} seconds")
    
    async def _repeating_job(
        self,
        name: str,
        callback: Callable,
        seconds: int,
        data: Optional[dict],
    ) -> None:
        """Execute a repeating job."""
        try:
            while self._running and name in self._jobs:
                context = JobContext(user_id=data.get("user_id", 0) if data else 0, data=data or {})
                
                if asyncio.iscoroutinefunction(callback):
                    await callback(context)
                else:
                    callback(context)
                
                await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in repeating job {name}: {e}", exc_info=True)
        finally:
            if name in self._jobs:
                del self._jobs[name]
    
    def cancel_job(self, name: str) -> None:
        """Cancel a job by name."""
        if name in self._jobs:
            task = self._jobs[name]
            task.cancel()
            del self._jobs[name]
            logger.info(f"Cancelled job {name}")

