"""
Broadcast service for sending messages to all users.
"""
import os
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from zoneinfo import ZoneInfo

from platforms.interfaces import IResponseService
from repositories.broadcasts_repo import BroadcastsRepository
from utils.logger import get_logger

logger = get_logger(__name__)

# Try to import dateparser for natural language parsing
try:
    import dateparser
    DATEPARSER_AVAILABLE = True
except ImportError:
    DATEPARSER_AVAILABLE = False
    logger.info("dateparser not available, using simple time parser")


def is_user_dir(name: str) -> bool:
    """Check if a directory name represents a user ID (numeric)."""
    return name.isdigit()


def get_all_users(root_dir: str) -> List[int]:
    """
    Get all user IDs from the root directory.
    
    Args:
        root_dir: Root directory containing user directories
        
    Returns:
        List of user IDs (integers)
    """
    user_ids = []
    try:
        for entry in os.listdir(root_dir):
            user_path = os.path.join(root_dir, entry)
            if os.path.isdir(user_path) and is_user_dir(entry):
                try:
                    user_ids.append(int(entry))
                except ValueError:
                    # Skip invalid user IDs
                    continue
    except FileNotFoundError:
        logger.warning(f"Root directory not found: {root_dir}")
    except Exception as e:
        logger.error(f"Error reading user directories: {str(e)}")
    
    return sorted(user_ids)


async def send_broadcast(
    response_service: IResponseService,
    user_ids: List[int],
    message: str,
    rate_limit_delay: float = 0.05
) -> Dict[str, int]:
    """
    Send a broadcast message to all users with rate limiting.
    
    Args:
        response_service: Platform-agnostic response service
        user_ids: List of user IDs to send to
        message: Message text to send
        rate_limit_delay: Delay between messages in seconds (default 0.05 = 20 msg/sec)
        
    Returns:
        Dictionary with 'success' and 'failed' counts
    """
    success_count = 0
    failed_count = 0
    
    logger.info(f"Starting broadcast to {len(user_ids)} users")
    
    for user_id in user_ids:
        try:
            await response_service.send_text(
                user_id=user_id,
                chat_id=user_id,  # For Telegram, chat_id == user_id for private chats
                text=message,
                parse_mode='Markdown'
            )
            success_count += 1
            
            # Rate limiting: delay between messages
            if rate_limit_delay > 0:
                await asyncio.sleep(rate_limit_delay)
                
        except Exception as e:
            failed_count += 1
            # Log specific error types
            error_msg = str(e)
            if "blocked" in error_msg.lower() or "chat not found" in error_msg.lower():
                logger.debug(f"User {user_id} blocked bot or chat not found")
            elif "forbidden" in error_msg.lower():
                logger.debug(f"User {user_id} forbidden")
            else:
                logger.warning(f"Error sending to user {user_id}: {error_msg}")
    
    logger.info(f"Broadcast completed: {success_count} sent, {failed_count} failed")
    return {"success": success_count, "failed": failed_count}


async def execute_broadcast_from_db(
    response_service: IResponseService,
    root_dir: str,
    broadcast_id: str,
) -> Dict[str, int]:
    """
    Execute a broadcast from the database by ID.
    Marks the broadcast as completed after execution.
    
    Args:
        response_service: Platform-agnostic response service
        root_dir: Root directory for database access
        broadcast_id: Broadcast ID from database
        
    Returns:
        Dictionary with 'success' and 'failed' counts
    """
    broadcasts_repo = BroadcastsRepository(root_dir)
    broadcast = broadcasts_repo.get_broadcast(broadcast_id)
    
    if not broadcast:
        logger.error(f"Broadcast {broadcast_id} not found in database")
        return {"success": 0, "failed": 0}
    
    if broadcast.status != "pending":
        logger.warning(f"Broadcast {broadcast_id} is not pending (status: {broadcast.status})")
        return {"success": 0, "failed": 0}
    
    # Execute the broadcast
    results = await send_broadcast(
        response_service,
        broadcast.target_user_ids,
        broadcast.message,
    )
    
    # Mark as completed
    broadcasts_repo.mark_broadcast_completed(broadcast_id)
    logger.info(f"Broadcast {broadcast_id} marked as completed")
    
    return results


def parse_broadcast_time(time_str: str, admin_tz: str) -> Optional[datetime]:
    """
    Parse broadcast time from string input.
    Supports ISO format (YYYY-MM-DD HH:MM) and natural language.
    
    Args:
        time_str: Time string to parse
        admin_tz: Admin's timezone (e.g., "Europe/Paris")
        
    Returns:
        Parsed datetime in admin's timezone, or None if parsing fails
    """
    time_str = time_str.strip()
    
    if not time_str:
        return None
    
    # Try natural language parsing first (if dateparser is available)
    if DATEPARSER_AVAILABLE:
        try:
            # Parse in admin's timezone
            parsed = dateparser.parse(
                time_str,
                settings={
                    'TIMEZONE': admin_tz,
                    'RETURN_AS_TIMEZONE_AWARE': True,
                    'RELATIVE_BASE': datetime.now(ZoneInfo(admin_tz))
                }
            )
            if parsed:
                # Ensure timezone is set
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=ZoneInfo(admin_tz))
                return parsed
        except Exception as e:
            logger.debug(f"dateparser failed for '{time_str}': {str(e)}")
    
    # Try ISO format: YYYY-MM-DD HH:MM
    try:
        # Try with date and time
        if len(time_str) >= 16:
            dt = datetime.strptime(time_str[:16], "%Y-%m-%d %H:%M")
            # Set timezone
            dt = dt.replace(tzinfo=ZoneInfo(admin_tz))
            return dt
    except ValueError:
        pass
    
    # Try simple natural language patterns (fallback)
    now = datetime.now(ZoneInfo(admin_tz))
    time_str_lower = time_str.lower()
    
    # "now" or "immediately"
    if time_str_lower in ["now", "immediately", "immediate"]:
        return now
    
    # "in X minutes/hours"
    if time_str_lower.startswith("in "):
        try:
            parts = time_str_lower[3:].split()
            if len(parts) >= 2:
                amount = int(parts[0])
                unit = parts[1]
                
                if "minute" in unit:
                    return now + timedelta(minutes=amount)
                elif "hour" in unit:
                    return now + timedelta(hours=amount)
                elif "day" in unit:
                    return now + timedelta(days=amount)
        except (ValueError, IndexError):
            pass
    
    # "tomorrow" or "tomorrow HH:MM"
    if time_str_lower.startswith("tomorrow"):
        tomorrow = now + timedelta(days=1)
        remaining = time_str_lower[8:].strip()
        if remaining:
            # Try to parse time like "14:30"
            try:
                time_parts = remaining.split(":")
                if len(time_parts) == 2:
                    hour = int(time_parts[0])
                    minute = int(time_parts[1])
                    return tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
            except (ValueError, IndexError):
                pass
        # Default to same time tomorrow
        return tomorrow.replace(hour=now.hour, minute=now.minute, second=0, microsecond=0)
    
    # If all parsing fails, return None
    logger.warning(f"Could not parse time string: '{time_str}'")
    return None
