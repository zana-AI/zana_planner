import { useState } from 'react';
import type { PublicUser } from '../types';

interface UserCardProps {
  user: PublicUser;
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
  
  return '?';
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
  return 'User';
}

export function UserCard({ user }: UserCardProps) {
  const [imageError, setImageError] = useState(false);
  const initials = getInitials(user);
  const displayName = getDisplayName(user);
  const avatarColor = getAvatarColor(user.user_id);
  
  // Construct avatar URL from avatar_path
  // If avatar_path is a full URL, use it directly
  // If avatar_path is a relative path or just exists, use API endpoint
  // Otherwise, fall back to initials
  const avatarUrl = user.avatar_path && !imageError 
    ? (user.avatar_path.startsWith('http')
        ? user.avatar_path  // Full URL (external)
        : `/api/media/avatars/${user.user_id}`)  // Use API endpoint for local avatars
    : null;

  return (
    <div className="user-card">
      <div className="user-card-avatar">
        {avatarUrl && !imageError ? (
          <img
            src={avatarUrl}
            alt={displayName}
            onError={() => setImageError(true)}
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
        {user.username && (
          <div className="user-card-username">@{user.username}</div>
        )}
        {user.activity_count > 0 && (
          <div className="user-card-activity">
            {user.activity_count} {user.activity_count === 1 ? 'activity' : 'activities'}
          </div>
        )}
      </div>
    </div>
  );
}

