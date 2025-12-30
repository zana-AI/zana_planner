"""
Telegram job scheduler adapter.

Wraps Telegram's JobQueue to implement the IJobScheduler interface.
"""

from typing import Callable, Optional
from datetime import datetime, time
from zoneinfo import ZoneInfo
from telegram.ext import JobQueue

from ..interfaces import IJobScheduler


class TelegramJobScheduler(IJobScheduler):
    """Telegram implementation of IJobScheduler."""
    
    def __init__(self, job_queue: JobQueue):
        """Initialize with Telegram's JobQueue."""
        self._job_queue = job_queue
    
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
        
        # Clear any existing job with the same name
        for job in self._job_queue.get_jobs_by_name(job_name):
            job.enabled = False
            job.schedule_removal()
        
        # Schedule the new job
        self._job_queue.run_daily(
            callback,
            time=time(hh, mm, tzinfo=ZoneInfo(tz)),
            days=(0, 1, 2, 3, 4, 5, 6),  # All days of the week
            name=job_name,
            data={"user_id": user_id}
        )
    
    def schedule_once(
        self,
        name: str,
        callback: Callable,
        when_dt: datetime,
        data: Optional[dict] = None,
    ) -> None:
        """Schedule a one-time job."""
        # Clear any existing job with the same name
        for job in self._job_queue.get_jobs_by_name(name):
            job.enabled = False
            job.schedule_removal()
        
        # Schedule the one-time job
        self._job_queue.run_once(
            callback,
            when_dt,
            name=name,
            data=data or {}
        )
    
    def schedule_repeating(
        self,
        name: str,
        callback: Callable,
        seconds: int,
        data: Optional[dict] = None,
    ) -> None:
        """Schedule a repeating job."""
        # Clear any existing job with the same name
        for job in self._job_queue.get_jobs_by_name(name):
            job.enabled = False
            job.schedule_removal()
        
        # Schedule the repeating job
        self._job_queue.run_repeating(
            callback,
            interval=seconds,
            first=0,  # Start immediately
            name=name,
            data=data or {}
        )
    
    def cancel_job(self, name: str) -> None:
        """Cancel a job by name."""
        for job in self._job_queue.get_jobs_by_name(name):
            job.schedule_removal()

