"""
Mock job scheduler for testing.
"""

from typing import Callable, Optional, Dict, Any, List
from datetime import datetime, time
from zoneinfo import ZoneInfo

from ..interfaces import IJobScheduler
from utils.logger import get_logger

logger = get_logger(__name__)


class MockJob:
    """Mock job representation."""
    
    def __init__(self, name: str, callback: Callable, data: Optional[dict] = None):
        self.name = name
        self.callback = callback
        self.data = data or {}
        self.enabled = True
        self.scheduled_time: Optional[datetime] = None
        self.interval: Optional[int] = None
        self.daily_time: Optional[time] = None
        self.daily_tz: Optional[str] = None


class MockJobScheduler(IJobScheduler):
    """Mock implementation of IJobScheduler for testing."""
    
    def __init__(self):
        """Initialize mock job scheduler."""
        self._jobs: Dict[str, MockJob] = {}
        self._executed_jobs: List[Dict[str, Any]] = []
    
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
        job_name = f"{name_prefix}-{user_id}"
        
        # Cancel existing job
        if job_name in self._jobs:
            del self._jobs[job_name]
        
        # Create mock job
        job = MockJob(job_name, callback, {"user_id": user_id})
        job.daily_time = time(hh, mm)
        job.daily_tz = tz
        self._jobs[job_name] = job
        
        logger.debug(f"Mock: Scheduled daily job {job_name} at {hh}:{mm:02d} {tz}")
    
    def schedule_once(
        self,
        name: str,
        callback: Callable,
        when_dt: datetime,
        data: Optional[dict] = None,
    ) -> None:
        """Schedule a one-time job."""
        # Cancel existing job
        if name in self._jobs:
            del self._jobs[name]
        
        # Create mock job
        job = MockJob(name, callback, data)
        job.scheduled_time = when_dt
        self._jobs[name] = job
        
        logger.debug(f"Mock: Scheduled one-time job {name} for {when_dt}")
    
    def schedule_repeating(
        self,
        name: str,
        callback: Callable,
        seconds: int,
        data: Optional[dict] = None,
    ) -> None:
        """Schedule a repeating job."""
        # Cancel existing job
        if name in self._jobs:
            del self._jobs[name]
        
        # Create mock job
        job = MockJob(name, callback, data)
        job.interval = seconds
        self._jobs[name] = job
        
        logger.debug(f"Mock: Scheduled repeating job {name} every {seconds}s")
    
    def cancel_job(self, name: str) -> None:
        """Cancel a job by name."""
        if name in self._jobs:
            del self._jobs[name]
            logger.debug(f"Mock: Cancelled job {name}")
    
    # Test helper methods
    def get_job(self, name: str) -> Optional[MockJob]:
        """Get a job by name (for testing)."""
        return self._jobs.get(name)
    
    def get_all_jobs(self) -> Dict[str, MockJob]:
        """Get all scheduled jobs (for testing)."""
        return self._jobs.copy()
    
    async def execute_job(self, name: str, context: Any = None) -> None:
        """Execute a job manually (for testing)."""
        if name not in self._jobs:
            logger.warning(f"Mock: Job {name} not found")
            return
        
        job = self._jobs[name]
        if not job.enabled:
            logger.debug(f"Mock: Job {name} is disabled")
            return
        
        try:
            # Create a mock context if needed
            if context is None:
                from ..types import JobContext
                context = JobContext(job_name=name, data=job.data)
            
            # Execute callback
            if callable(job.callback):
                if hasattr(job.callback, '__call__'):
                    # Check if it's async
                    import asyncio
                    if asyncio.iscoroutinefunction(job.callback):
                        await job.callback(context)
                    else:
                        job.callback(context)
            
            self._executed_jobs.append({
                "name": name,
                "timestamp": datetime.now(),
                "data": job.data,
            })
            
            logger.debug(f"Mock: Executed job {name}")
        except Exception as e:
            logger.error(f"Mock: Error executing job {name}: {e}")
    
    def get_executed_jobs(self) -> List[Dict[str, Any]]:
        """Get list of executed jobs (for testing)."""
        return self._executed_jobs.copy()
    
    def clear_executed_jobs(self) -> None:
        """Clear executed jobs list (for testing)."""
        self._executed_jobs.clear()

