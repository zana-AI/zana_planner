"""
Utility functions for generating Google Calendar links.
"""
from datetime import datetime, timedelta
from urllib.parse import quote
from typing import Optional


def generate_google_calendar_link(
    title: str,
    start_time: datetime,
    duration_hours: float,
    description: str = "",
    timezone: str = "UTC"
) -> str:
    """
    Generate a Google Calendar link for an event.
    
    Args:
        title: Event title
        start_time: Start datetime (timezone-aware or naive)
        duration_hours: Duration in hours
        description: Event description
        timezone: Timezone string (e.g., "Europe/Paris", "America/New_York")
    
    Returns:
        Google Calendar URL string
    """
    # Calculate end time
    end_time = start_time + timedelta(hours=duration_hours)
    
    # Format dates in ISO 8601 format: YYYYMMDDTHHmmss
    # If timezone-aware, include offset; otherwise use Z for UTC
    if start_time.tzinfo is not None:
        # Timezone-aware datetime
        start_str = start_time.strftime("%Y%m%dT%H%M%S")
        end_str = end_time.strftime("%Y%m%dT%H%M%S")
        
        # Get timezone offset
        offset = start_time.strftime("%z")
        if offset:
            # Format: +0100 or -0500
            start_str += offset
            end_str += offset
        else:
            start_str += "Z"
            end_str += "Z"
    else:
        # Naive datetime - treat as UTC
        start_str = start_time.strftime("%Y%m%dT%H%M%SZ")
        end_str = end_time.strftime("%Y%m%dT%H%M%SZ")
    
    # URL encode parameters
    encoded_title = quote(title)
    encoded_description = quote(description)
    
    # Build Google Calendar URL
    url = (
        f"https://calendar.google.com/calendar/render?action=TEMPLATE"
        f"&text={encoded_title}"
        f"&dates={start_str}/{end_str}"
        f"&details={encoded_description}"
    )
    
    return url


def suggest_time_slot(
    duration_hours: float,
    preferred_hour: int = 9,
    preferred_minute: int = 0,
    base_date: Optional[datetime] = None
) -> datetime:
    """
    Suggest a time slot for scheduling content.
    
    Args:
        duration_hours: Duration of the content in hours
        preferred_hour: Preferred hour of day (0-23)
        preferred_minute: Preferred minute (0-59)
        base_date: Base date to use (defaults to today)
    
    Returns:
        Suggested start datetime
    """
    if base_date is None:
        base_date = datetime.now()
    
    # Create suggested time on the base date
    suggested = base_date.replace(
        hour=preferred_hour,
        minute=preferred_minute,
        second=0,
        microsecond=0
    )
    
    # If the suggested time is in the past, move to next day
    if suggested < datetime.now():
        suggested += timedelta(days=1)
    
    return suggested
