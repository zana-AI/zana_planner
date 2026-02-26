import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { PublicUser } from '../types';
import { generateUsername, getInitialsFromUsername } from '../utils/usernameGenerator';
import { buildActivitySummaryText } from '../utils/activitySummary';
import { getDicebearUrl } from '../utils/dicebearAvatar';
import { apiClient } from '../api/client';

interface UserCardProps {
  user: PublicUser;
  currentUserId?: string; // Current authenticated user ID (if available)
  showFollowButton?: boolean; // Whether to show follow button
  onFollowChange?: () => void; // Callback when follow status changes
  onClick?: () => void; // Callback when card is clicked
}

/**
 * Generate initials from user's name.
 */
function getInitials(user: PublicUser): string {
  if (user.display_name) {
    const parts = user.display_name.trim().split(/\s+/);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }
    return parts[0][0]?.toUpperCase() || '?';
  }
  
  if (user.first_name) {
    if (user.last_name) {
      return (user.first_name[0] + user.last_name[0]).toUpperCase();
    }
    return user.first_name[0]?.toUpperCase() || '?';
  }
  
  // If no name available, generate username and extract initials
  const generatedUsername = generateUsername(user.user_id);
  return getInitialsFromUsername(generatedUsername);
}

/**
 * Generate a color based on user_id hash for consistent avatar colors.
 */
function getAvatarColor(userId: string): string {
  // Simple hash function
  let hash = 0;
  for (let i = 0; i < userId.length; i++) {
    hash = userId.charCodeAt(i) + ((hash << 5) - hash);
  }
  
  // Generate a color from the hash
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 65%, 50%)`;
}

/**
 * Get display name for the user.
 */
function getDisplayName(user: PublicUser): string {
  if (user.display_name) {
    return user.display_name;
  }
  if (user.first_name && user.last_name) {
    return `${user.first_name} ${user.last_name}`;
  }
  if (user.first_name) {
    return user.first_name;
  }
  if (user.username) {
    return `@${user.username}`;
  }
  // Generate deterministic username when no name is available
  return generateUsername(user.user_id);
}

export function UserCard({ user, currentUserId, showFollowButton = false, onFollowChange, onClick }: UserCardProps) {
  const navigate = useNavigate();
  const [imageError, setImageError] = useState(false);
  const [dicebearError, setDicebearError] = useState(false);
  const [isFollowing, setIsFollowing] = useState(false);
  const [isLoadingFollow, setIsLoadingFollow] = useState(false);
  const [followStatusChecked, setFollowStatusChecked] = useState(false);

  const handleCardClick = () => {
    if (onClick) {
      onClick();
    } else {
      // Default: navigate to user detail page
      navigate(`/users/${user.user_id}`);
    }
  };
  
  const initials = getInitials(user);
  const displayName = getDisplayName(user);
  const avatarColor = getAvatarColor(user.user_id);
  const activitySummary = buildActivitySummaryText(user.weekly_activity_count, user.last_activity_at_utc);
  
  // Generate DiceBear avatar URL (deterministic based on user_id)
  const dicebearUrl = getDicebearUrl(user.user_id);
  
  // Check if this is the current user's own card
  const isOwnCard = currentUserId && currentUserId === user.user_id;
  
  // NOTE: We intentionally do NOT fetch public promises in the list card.
  // Public promises are shown on the user detail page.
  
  // Check follow status on mount if authenticated and not own card
  useEffect(() => {
    if (showFollowButton && currentUserId && !isOwnCard && !followStatusChecked) {
      const checkFollowStatus = async () => {
        try {
          const status = await apiClient.getFollowStatus(user.user_id);
          setIsFollowing(status.is_following);
          setFollowStatusChecked(true);
        } catch (err) {
          console.error('Failed to check follow status:', err);
          // Don't show follow button if we can't check status
        }
      };
      checkFollowStatus();
    }
  }, [showFollowButton, currentUserId, user.user_id, isOwnCard, followStatusChecked]);
  
  const handleFollowToggle = async (e?: React.MouseEvent) => {
    if (!currentUserId || isOwnCard || isLoadingFollow) return;
    
    // Stop event propagation to prevent card click
    if (e) {
      e.stopPropagation();
    }
    
    setIsLoadingFollow(true);
    try {
      if (isFollowing) {
        await apiClient.unfollowUser(user.user_id);
        setIsFollowing(false);
      } else {
        await apiClient.followUser(user.user_id);
        setIsFollowing(true);
      }
      // Notify parent component of follow change
      if (onFollowChange) {
        onFollowChange();
      }
    } catch (err) {
      console.error('Failed to toggle follow:', err);
      // Could show error toast here
    } finally {
      setIsLoadingFollow(false);
    }
  };
  
  // Construct avatar URL
  // Only try API endpoint if user has an avatar_path (indicates avatar exists)
  // If avatar_path is a full URL, use it directly
  // If avatar_path exists but is not a URL, use API endpoint
  // Otherwise, skip API endpoint and go straight to fallback (DiceBear/initials)
  const avatarUrl = !imageError && user.avatar_path
    ? (user.avatar_path.startsWith('http')
        ? user.avatar_path  // Full URL (external)
        : `/api/media/avatars/${user.user_id}`)  // Use API endpoint for local avatars
    : null;

  return (
    <div 
      className="user-card" 
      onClick={handleCardClick}
      style={{ cursor: 'pointer' }}
    >
      <div className="user-card-avatar">
        {avatarUrl && !imageError ? (
          <img
            src={avatarUrl}
            alt={displayName}
            onError={() => setImageError(true)}
            className="user-card-avatar-img"
          />
        ) : !dicebearError ? (
          <img
            src={dicebearUrl}
            alt={displayName}
            onError={() => setDicebearError(true)}
            className="user-card-avatar-img"
          />
        ) : (
          <div 
            className="user-card-avatar-initials"
            style={{ backgroundColor: avatarColor }}
          >
            {initials}
          </div>
        )}
      </div>
      
      <div className="user-card-info">
        <div className="user-card-name">{displayName}</div>
        <div className="user-card-activity">{activitySummary}</div>
        {showFollowButton && currentUserId && !isOwnCard && (
          <button
            className={`user-card-follow-btn ${isFollowing ? 'following' : ''}`}
            onClick={handleFollowToggle}
            disabled={isLoadingFollow || !followStatusChecked}
            style={{ marginTop: '0.5rem' }}
          >
            {isLoadingFollow ? '...' : isFollowing ? 'Following' : 'Follow'}
          </button>
        )}
      </div>
    </div>
  );
}

