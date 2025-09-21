from datetime import datetime, time
from zoneinfo import ZoneInfo
from telegram.ext import JobQueue


def schedule_user_daily(job_queue: JobQueue, user_id: int, tz: str, callback, hh: int = 22, mm: int = 0, name_prefix: str = "nightly"):
    """Schedule a daily job for a user at timezone-aware time."""
    job_name = f"{name_prefix}-{user_id}"
    
    # Clear any existing job with the same name
    for job in job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()
    
    # Schedule the new job
    job_queue.run_daily(
        callback,
        time=time(hh, mm, tzinfo=ZoneInfo(tz)),
        days=(0, 1, 2, 3, 4, 5, 6),  # All days of the week
        name=job_name,
        data={"user_id": user_id}
    )


def schedule_repeating(job_queue: JobQueue, name: str, callback, seconds: int, data=None):
    """Schedule a repeating job (used for session tickers)."""
    # Clear any existing job with the same name
    for job in job_queue.get_jobs_by_name(name):
        job.schedule_removal()
    
    # Schedule the new repeating job
    job_queue.run_repeating(
        callback,
        interval=seconds,
        first=0,  # Start immediately
        name=name,
        data=data
    )


def schedule_once(job_queue: JobQueue, name: str, callback, when_dt: datetime, data=None):
    """Schedule a one-time job (used for pre-pings and snoozes)."""
    # Clear any existing job with the same name
    for job in job_queue.get_jobs_by_name(name):
        job.schedule_removal()
    
    # Schedule the one-time job
    job_queue.run_once(
        callback,
        when_dt,
        name=name,
        data=data
    )


def cancel_job(job_queue: JobQueue, name: str):
    """Cancel a job by name."""
    for job in job_queue.get_jobs_by_name(name):
        job.schedule_removal()
