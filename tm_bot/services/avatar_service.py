"""
Avatar service for fetching, storing, and managing user profile pictures.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from db.sqlite_db import connection_for_root, utc_now_iso, dt_from_utc_iso
from utils.logger import get_logger

logger = get_logger(__name__)


class AvatarService:
    """Service for managing user avatar/profile pictures."""
    
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.avatars_dir = os.path.join(root_dir, "media", "avatars")
        # Ensure avatars directory exists
        os.makedirs(self.avatars_dir, exist_ok=True)
    
    def get_avatar_path(self, user_id: int) -> str:
        """Get local file path for user's avatar."""
        return os.path.join(self.avatars_dir, f"{user_id}.jpg")
    
    def should_refresh_avatar(self, user_id: int) -> bool:
        """
        Check if avatar needs refresh.
        Returns True if avatar hasn't been checked in the last 24 hours.
        """
        user = str(user_id)
        with connection_for_root(self.root_dir) as conn:
            row = conn.execute(
                "SELECT avatar_checked_at_utc FROM users WHERE user_id = ? LIMIT 1;",
                (user,),
            ).fetchone()
            
            if not row or not row["avatar_checked_at_utc"]:
                return True  # Never checked, should refresh
            
            checked_at = dt_from_utc_iso(row["avatar_checked_at_utc"])
            if not checked_at:
                return True
            
            # Check if more than 24 hours have passed
            now = datetime.now(timezone.utc)
            time_diff = now - checked_at
            return time_diff > timedelta(hours=24)
    
    async def fetch_user_avatar(self, bot, user_id: int) -> Optional[str]:
        """
        Fetch user's profile photo from Telegram.
        Returns file_id of the largest photo, or None if no photo exists.
        """
        try:
            photos = await bot.get_user_profile_photos(user_id=user_id, limit=1)
            
            if not photos or not getattr(photos, "total_count", 0):
                logger.debug(f"No profile photos found for user {user_id}")
                return None
            
            if not getattr(photos, "photos", None) or not photos.photos:
                logger.debug(f"Profile photos list is empty for user {user_id}")
                return None
            
            # photos.photos is a list of photo-size lists; pick the largest size (last one)
            photo_sizes = photos.photos[0]
            if not photo_sizes:
                return None
            
            largest_photo = photo_sizes[-1]
            return largest_photo.file_id
            
        except Exception as e:
            logger.warning(f"Failed to fetch profile photos for user {user_id}: {e}")
            return None
    
    async def download_avatar(self, bot, file_id: str, user_id: int) -> Optional[str]:
        """
        Download avatar file from Telegram and save to local storage.
        Returns local file path if successful, None otherwise.
        """
        try:
            file = await bot.get_file(file_id)
            if not file:
                logger.warning(f"Failed to get file object for file_id {file_id}")
                return None
            
            avatar_path = self.get_avatar_path(user_id)
            
            # Download file
            await file.download_to_drive(avatar_path)
            
            # Verify file exists and has content
            if os.path.exists(avatar_path) and os.path.getsize(avatar_path) > 0:
                logger.info(f"Downloaded avatar for user {user_id} to {avatar_path}")
                return avatar_path
            else:
                logger.warning(f"Downloaded file is empty or missing for user {user_id}")
                return None
                
        except Exception as e:
            logger.warning(f"Failed to download avatar for user {user_id}: {e}")
            return None
    
    def update_user_avatar(
        self, 
        user_id: int, 
        file_path: Optional[str], 
        file_id: Optional[str] = None,
        file_unique_id: Optional[str] = None
    ) -> None:
        """
        Update database with avatar information.
        
        Args:
            user_id: User ID
            file_path: Local file path to avatar (relative to root_dir or absolute)
            file_id: Telegram file_id (optional)
            file_unique_id: Telegram file_unique_id (optional)
        """
        user = str(user_id)
        now = utc_now_iso()
        
        # Convert absolute path to relative path if it's within root_dir
        relative_path = None
        if file_path:
            abs_path = os.path.abspath(file_path)
            abs_root = os.path.abspath(self.root_dir)
            if abs_path.startswith(abs_root):
                relative_path = os.path.relpath(abs_path, abs_root)
                # Normalize path separators
                relative_path = relative_path.replace("\\", "/")
            else:
                # If outside root_dir, store as absolute path
                relative_path = abs_path
        
        with connection_for_root(self.root_dir) as conn:
            # Get current avatar_file_unique_id to check if it changed
            current_row = conn.execute(
                "SELECT avatar_file_unique_id FROM users WHERE user_id = ? LIMIT 1;",
                (user,),
            ).fetchone()
            
            current_unique_id = current_row["avatar_file_unique_id"] if current_row else None
            avatar_changed = (file_unique_id and file_unique_id != current_unique_id)
            
            conn.execute(
                """
                UPDATE users 
                SET avatar_file_id = ?,
                    avatar_file_unique_id = ?,
                    avatar_path = ?,
                    avatar_updated_at_utc = ?,
                    avatar_checked_at_utc = ?,
                    updated_at_utc = ?
                WHERE user_id = ?;
                """,
                (
                    file_id,
                    file_unique_id,
                    relative_path,
                    now if avatar_changed else None,  # Only update avatar_updated_at if changed
                    now,  # Always update checked_at
                    now,
                    user,
                ),
            )
            conn.commit()
            logger.debug(f"Updated avatar info for user {user_id}")
    
    async def fetch_and_store_avatar(self, bot, user_id: int) -> bool:
        """
        Fetch and store user's avatar if needed.
        Returns True if avatar was fetched/stored, False otherwise.
        
        This method:
        1. Checks if avatar needs refresh (24 hour check)
        2. Fetches profile photo from Telegram
        3. Downloads and stores locally
        4. Updates database
        """
        try:
            # Check if we need to refresh
            if not self.should_refresh_avatar(user_id):
                logger.debug(f"Avatar for user {user_id} was recently checked, skipping")
                return False
            
            # Fetch profile photo
            file_id = await self.fetch_user_avatar(bot, user_id)
            if not file_id:
                # No photo available, but still update checked_at to avoid checking too frequently
                self.update_user_avatar(user_id, None, None, None)
                return False
            
            # Get file info to get file_unique_id
            try:
                file = await bot.get_file(file_id)
                file_unique_id = file.file_unique_id if file else None
            except Exception as e:
                logger.warning(f"Failed to get file info for {file_id}: {e}")
                file_unique_id = None
            
            # Download avatar
            avatar_path = await self.download_avatar(bot, file_id, user_id)
            if not avatar_path:
                # Download failed, but still update checked_at
                self.update_user_avatar(user_id, None, file_id, file_unique_id)
                return False
            
            # Update database
            self.update_user_avatar(user_id, avatar_path, file_id, file_unique_id)
            return True
            
        except Exception as e:
            logger.error(f"Error in fetch_and_store_avatar for user {user_id}: {e}")
            # Still update checked_at to avoid repeated failures
            try:
                self.update_user_avatar(user_id, None, None, None)
            except:
                pass
            return False

