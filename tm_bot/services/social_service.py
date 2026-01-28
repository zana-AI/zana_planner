"""
Service for social/community features (followers, following, etc.).
"""
from typing import Optional

from repositories.follows_repo import FollowsRepository
from repositories.settings_repo import SettingsRepository
from db.postgres_db import get_db_session
from sqlalchemy import text
from utils.logger import get_logger

logger = get_logger(__name__)


class SocialService:
    """Service for managing social/community relationships."""
    
    def __init__(self, follows_repo: FollowsRepository, settings_repo: SettingsRepository):
        self.follows_repo = follows_repo
        self.settings_repo = settings_repo
    
    def get_followers(self, user_id: int) -> str:
        """
        Get list of users who follow you.
        
        Returns your followers with their display names. Only shows public profile
        information (username, first name) - no sensitive data is exposed.
        
        Returns:
            Formatted list of followers with display names, or message if no followers.
        """
        try:
            follower_ids = self.follows_repo.get_followers(user_id)
            
            if not follower_ids:
                return "You don't have any followers yet. Share your profile or promises to grow your community!"
            
            # Get display info for each follower (privacy-safe: only public info)
            followers_info = []
            for fid in follower_ids:
                try:
                    settings = self.settings_repo.get_settings(int(fid))
                    # Only include public info: username or first_name
                    display_name = None
                    if settings.username:
                        display_name = f"@{settings.username}"
                    elif settings.first_name:
                        display_name = settings.first_name
                    else:
                        display_name = f"User #{fid[-4:]}"  # Show only last 4 digits for privacy
                    
                    followers_info.append({
                        "display_name": display_name,
                        "has_username": bool(settings.username),
                    })
                except Exception:
                    # If we can't get settings, use anonymized identifier
                    followers_info.append({
                        "display_name": f"User #{fid[-4:]}",
                        "has_username": False,
                    })
            
            # Format response
            count = len(followers_info)
            result_lines = [f"👥 **You have {count} follower{'s' if count != 1 else ''}:**\n"]
            
            for i, f in enumerate(followers_info, 1):
                result_lines.append(f"{i}. {f['display_name']}")
            
            return "\n".join(result_lines)
        
        except Exception as e:
            logger.error(f"Error getting followers for user {user_id}: {str(e)}")
            return f"Error retrieving followers: {str(e)}"
    
    def get_following(self, user_id: int) -> str:
        """
        Get list of users you follow.
        
        Returns the users you're following with their display names. Only shows
        public profile information (username, first name) - no sensitive data.
        
        Returns:
            Formatted list of users you follow, or message if not following anyone.
        """
        try:
            following_ids = self.follows_repo.get_following(user_id)
            
            if not following_ids:
                return "You're not following anyone yet. Explore the community to find inspiring people!"
            
            # Get display info for each user (privacy-safe: only public info)
            following_info = []
            for fid in following_ids:
                try:
                    settings = self.settings_repo.get_settings(int(fid))
                    display_name = None
                    if settings.username:
                        display_name = f"@{settings.username}"
                    elif settings.first_name:
                        display_name = settings.first_name
                    else:
                        display_name = f"User #{fid[-4:]}"
                    
                    following_info.append({
                        "display_name": display_name,
                        "has_username": bool(settings.username),
                    })
                except Exception:
                    following_info.append({
                        "display_name": f"User #{fid[-4:]}",
                        "has_username": False,
                    })
            
            # Format response
            count = len(following_info)
            result_lines = [f"👤 **You're following {count} user{'s' if count != 1 else ''}:**\n"]
            
            for i, f in enumerate(following_info, 1):
                result_lines.append(f"{i}. {f['display_name']}")
            
            return "\n".join(result_lines)
        
        except Exception as e:
            logger.error(f"Error getting following for user {user_id}: {str(e)}")
            return f"Error retrieving following list: {str(e)}"
    
    def get_community_stats(self, user_id: int) -> str:
        """
        Get your community statistics (follower and following counts).
        
        Returns a summary of your social connections in the community.
        
        Returns:
            Formatted community stats summary.
        """
        try:
            follower_count = self.follows_repo.get_follower_count(user_id)
            following_count = self.follows_repo.get_following_count(user_id)
            
            result = [
                "📊 **Your Community Stats:**\n",
                f"👥 Followers: **{follower_count}**",
                f"👤 Following: **{following_count}**",
            ]
            
            # Add contextual message
            if follower_count == 0 and following_count == 0:
                result.append("\n💡 Tip: Start by following others who share your interests!")
            elif follower_count > following_count * 2:
                result.append("\n🌟 You have a great following! Keep sharing your progress.")
            elif following_count > 0 and follower_count == 0:
                result.append("\n💪 Great start! Stay active and others will notice you.")
            
            return "\n".join(result)
        
        except Exception as e:
            logger.error(f"Error getting community stats for user {user_id}: {str(e)}")
            return f"Error retrieving community stats: {str(e)}"
    
    def follow_user(self, user_id: int, target_username: str) -> str:
        """
        Follow another user by their username.
        
        You can only follow users who have a public username. This creates a
        one-way follow relationship - they won't automatically follow you back.
        
        Args:
            target_username: The username of the user to follow (without @ symbol).
        
        Returns:
            Success or error message.
        """
        try:
            if not target_username or not target_username.strip():
                return "Please provide a username to follow."
            
            # Clean username (remove @ if present)
            clean_username = target_username.strip().lstrip("@").lower()
            
            if not clean_username:
                return "Please provide a valid username."
            
            # Look up user by username (privacy: only find users with public usernames)
            target_user_id = self._find_user_by_username(clean_username)
            
            if not target_user_id:
                return f"User '@{clean_username}' not found. Make sure you have the correct username."
            
            # Check if trying to follow self
            if str(target_user_id) == str(user_id):
                return "You can't follow yourself! 😄"
            
            # Check if already following
            if self.follows_repo.is_following(user_id, int(target_user_id)):
                return f"You're already following @{clean_username}."
            
            # Create follow relationship
            success = self.follows_repo.follow(user_id, int(target_user_id))
            
            if success:
                return f"✅ You're now following @{clean_username}! You'll see their public activity in your feed."
            else:
                return f"You're already following @{clean_username}."
        
        except ValueError as e:
            return str(e)
        except Exception as e:
            logger.error(f"Error following user for {user_id}: {str(e)}")
            return f"Error following user: {str(e)}"
    
    def unfollow_user(self, user_id: int, target_username: str) -> str:
        """
        Unfollow a user by their username.
        
        Removes your follow relationship with the specified user. They won't
        be notified that you unfollowed them.
        
        Args:
            target_username: The username of the user to unfollow (without @ symbol).
        
        Returns:
            Success or error message.
        """
        try:
            if not target_username or not target_username.strip():
                return "Please provide a username to unfollow."
            
            # Clean username (remove @ if present)
            clean_username = target_username.strip().lstrip("@").lower()
            
            if not clean_username:
                return "Please provide a valid username."
            
            # Look up user by username
            target_user_id = self._find_user_by_username(clean_username)
            
            if not target_user_id:
                return f"User '@{clean_username}' not found."
            
            # Check if actually following
            if not self.follows_repo.is_following(user_id, int(target_user_id)):
                return f"You're not following @{clean_username}."
            
            # Remove follow relationship
            success = self.follows_repo.unfollow(user_id, int(target_user_id))
            
            if success:
                return f"✅ You've unfollowed @{clean_username}."
            else:
                return f"You're not following @{clean_username}."
        
        except Exception as e:
            logger.error(f"Error unfollowing user for {user_id}: {str(e)}")
            return f"Error unfollowing user: {str(e)}"
    
    def _find_user_by_username(self, username: str) -> Optional[str]:
        """
        Find a user ID by their username (internal helper).
        
        Privacy: Only returns users who have set a public username.
        """
        try:
            with get_db_session() as session:
                # Case-insensitive username lookup
                row = session.execute(
                    text("""
                        SELECT user_id FROM users
                        WHERE LOWER(username) = LOWER(:username)
                        LIMIT 1;
                    """),
                    {"username": username},
                ).fetchone()
                
                if row:
                    return str(row[0])
                return None
        except Exception as e:
            logger.error(f"Error finding user by username: {str(e)}")
            return None
