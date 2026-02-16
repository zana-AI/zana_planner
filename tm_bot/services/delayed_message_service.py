"""
Delayed message service for queuing messages to be sent after user inactivity.

This service allows queuing messages that will be sent to users after a period
of inactivity (default: 2 minutes). If the user becomes active before the
message is sent, the queued message is cancelled.

This is a generic service that can be reused for various scenarios beyond
timezone detection.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Callable, Optional, Dict
from zoneinfo import ZoneInfo

from platforms.interfaces import IJobScheduler
from repositories.settings_repo import SettingsRepository
from utils.logger import get_logger

logger = get_logger(__name__)

# Module-level registry for delayed message service instance
# This allows access from both FastAPI app and Telegram bot contexts
_delayed_service_instance: Optional['DelayedMessageService'] = None


def get_delayed_message_service() -> Optional['DelayedMessageService']:
    """Get the global delayed message service instance."""
    return _delayed_service_instance


def set_delayed_message_service(service: 'DelayedMessageService') -> None:
    """Set the global delayed message service instance."""
    global _delayed_service_instance
    _delayed_service_instance = service


class DelayedMessageService:
    """Service for managing delayed messages based on user inactivity."""
    
    def __init__(self, scheduler: IJobScheduler) -> None:
        """
        Initialize delayed message service.

        Args:
            scheduler: Job scheduler instance for scheduling delayed messages
        """
        self.scheduler = scheduler
        self.settings_repo = SettingsRepository()
        self._pending_messages: Dict[str, str] = {}  # message_id -> job_name
        
        # Register this instance globally
        set_delayed_message_service(self)
    
    def get_last_activity(self, user_id: int) -> Optional[datetime]:
        """
        Get user's last activity timestamp from last_seen_utc.
        
        Args:
            user_id: User ID
            
        Returns:
            Last activity datetime or None if never active
        """
        settings = self.settings_repo.get_settings(user_id)
        return settings.last_seen if settings else None
    
    def is_user_active(self, user_id: int, delay_minutes: int = 2) -> bool:
        """
        Check if user was active recently (within delay period).
        
        Args:
            user_id: User ID
            delay_minutes: Delay period in minutes
            
        Returns:
            True if user was active within delay period, False otherwise
        """
        last_activity = self.get_last_activity(user_id)
        if not last_activity:
            return False
        
        # Make timezone-aware if needed
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=ZoneInfo("UTC"))
        
        now = datetime.now(ZoneInfo("UTC"))
        time_since_activity = (now - last_activity).total_seconds()
        delay_seconds = delay_minutes * 60
        
        return time_since_activity < delay_seconds
    
    def queue_message(
        self,
        user_id: int,
        message_func: Callable,
        delay_minutes: int = 2,
        message_id: Optional[str] = None,
    ) -> str:
        """
        Queue a message to be sent after user inactivity.
        
        Args:
            user_id: User ID to send message to
            message_func: Async function to call when sending the message
            delay_minutes: Delay in minutes before sending (default: 2)
            message_id: Optional unique message ID (for cancelling specific messages)
            
        Returns:
            Job name for the scheduled message
        """
        # Generate message_id if not provided
        if not message_id:
            message_id = f"delayed_msg_{user_id}_{int(datetime.now().timestamp())}"
        
        job_name = f"delayed-msg-{message_id}"
        
        # Cancel any existing message with same message_id
        if message_id in self._pending_messages:
            existing_job = self._pending_messages[message_id]
            try:
                self.scheduler.cancel_job(existing_job)
            except Exception as e:
                logger.warning(f"Error cancelling existing job {existing_job}: {e}")
        
        # Calculate when to send the message
        now = datetime.now(ZoneInfo("UTC"))
        send_time = now + timedelta(minutes=delay_minutes)
        
        # Create callback that checks if user is still inactive before sending
        async def send_if_inactive(context):
            """Send message only if user is still inactive."""
            # Check if user became active since message was queued
            if self.is_user_active(user_id, delay_minutes):
                logger.info(f"Cancelling delayed message {message_id} for user {user_id} - user became active")
                if message_id in self._pending_messages:
                    del self._pending_messages[message_id]
                return
            
            # User is still inactive, send the message
            try:
                logger.info(f"Sending delayed message {message_id} to user {user_id}")
                if callable(message_func):
                    if asyncio.iscoroutinefunction(message_func):
                        await message_func()
                    else:
                        message_func()
            except Exception as e:
                logger.error(f"Error sending delayed message {message_id} to user {user_id}: {e}", exc_info=True)
            finally:
                # Clean up
                if message_id in self._pending_messages:
                    del self._pending_messages[message_id]
        
        # Schedule the message
        self.scheduler.schedule_once(
            name=job_name,
            callback=send_if_inactive,
            when_dt=send_time,
            data={"user_id": user_id, "message_id": message_id}
        )
        
        self._pending_messages[message_id] = job_name
        logger.info(f"Queued delayed message {message_id} for user {user_id}, will send in {delay_minutes} minutes if inactive")
        
        return job_name
    
    def cancel_pending(self, user_id: int, message_id: Optional[str] = None) -> int:
        """
        Cancel pending messages for a user.
        
        Args:
            user_id: User ID
            message_id: Optional specific message ID to cancel, or None to cancel all
            
        Returns:
            Number of messages cancelled
        """
        cancelled = 0
        
        if message_id:
            # Cancel specific message
            if message_id in self._pending_messages:
                job_name = self._pending_messages[message_id]
                try:
                    self.scheduler.cancel_job(job_name)
                    del self._pending_messages[message_id]
                    cancelled = 1
                    logger.info(f"Cancelled delayed message {message_id} for user {user_id}")
                except Exception as e:
                    logger.warning(f"Error cancelling message {message_id}: {e}")
        else:
            # Cancel all messages for this user (messages with user_id in message_id)
            user_prefix = f"delayed_msg_{user_id}_"
            to_cancel = [
                (msg_id, job_name)
                for msg_id, job_name in list(self._pending_messages.items())
                if msg_id.startswith(user_prefix)
            ]
            
            for msg_id, job_name in to_cancel:
                try:
                    self.scheduler.cancel_job(job_name)
                    del self._pending_messages[msg_id]
                    cancelled += 1
                except Exception as e:
                    logger.warning(f"Error cancelling message {msg_id}: {e}")
            
            if cancelled > 0:
                logger.info(f"Cancelled {cancelled} delayed message(s) for user {user_id}")
        
        return cancelled
