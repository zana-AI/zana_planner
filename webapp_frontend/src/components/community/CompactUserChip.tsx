import { useState, type KeyboardEvent, type MouseEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import type { PublicUser } from '../../types';
import { getDicebearUrl } from '../../utils/dicebearAvatar';
import {
  getActivityMicroLabel,
  getActivityState,
  getAvatarColor,
  getPublicDisplayName,
  getPublicInitials,
} from '../../utils/publicUserDisplay';

interface CompactUserChipProps {
  user: PublicUser;
  currentUserId?: string;
  showFollowButton?: boolean;
  isFollowing?: boolean;
  followPending?: boolean;
  onFollowToggle?: (targetUserId: string) => void;
}

export function CompactUserChip({
  user,
  currentUserId,
  showFollowButton = false,
  isFollowing = false,
  followPending = false,
  onFollowToggle,
}: CompactUserChipProps) {
  const navigate = useNavigate();
  const [imageError, setImageError] = useState(false);
  const [dicebearError, setDicebearError] = useState(false);

  const displayName = getPublicDisplayName(user);
  const initials = getPublicInitials(user);
  const avatarColor = getAvatarColor(user.user_id);
  const dicebearUrl = getDicebearUrl(user.user_id);
  const activityState = getActivityState(user.weekly_activity_count, user.last_activity_at_utc);
  const activityLabel = getActivityMicroLabel(user.weekly_activity_count, user.last_activity_at_utc);
  const isOwnCard = !!currentUserId && currentUserId === user.user_id;
  const canFollow = showFollowButton && !isOwnCard && !!onFollowToggle;

  const avatarUrl = !imageError && user.avatar_path
    ? (user.avatar_path.startsWith('http') ? user.avatar_path : `/api/media/avatars/${user.user_id}`)
    : null;

  const openProfile = () => {
    navigate(`/users/${user.user_id}`);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      openProfile();
    }
  };

  const onFollowClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (!onFollowToggle || followPending) return;
    onFollowToggle(user.user_id);
  };

  return (
    <div
      className={`compact-user-chip compact-user-chip-${activityState}`}
      onClick={openProfile}
      onKeyDown={onKeyDown}
      role="button"
      tabIndex={0}
      aria-label={`Open ${displayName} profile`}
    >
      <div className="compact-user-avatar-wrap">
        <div className="compact-user-avatar">
          {avatarUrl ? (
            <img
              src={avatarUrl}
              alt={displayName}
              onError={() => setImageError(true)}
              className="compact-user-avatar-img"
            />
          ) : !dicebearError ? (
            <img
              src={dicebearUrl}
              alt={displayName}
              onError={() => setDicebearError(true)}
              className="compact-user-avatar-img"
            />
          ) : (
            <div className="compact-user-avatar-initials" style={{ backgroundColor: avatarColor }}>
              {initials}
            </div>
          )}
        </div>
        <span className={`compact-user-status compact-user-status-${activityState}`} />
      </div>

      <div className="compact-user-main">
        <div className="compact-user-name">{displayName}</div>
        <div className="compact-user-meta">
          <span>{activityLabel}</span>
          {(user.weekly_activity_count ?? 0) >= 5 ? <span className="compact-user-flame">hot</span> : null}
        </div>
      </div>

      {canFollow ? (
        <button
          type="button"
          className={`compact-user-follow-btn ${isFollowing ? 'following' : ''}`}
          onClick={onFollowClick}
          disabled={followPending}
        >
          {followPending ? '...' : isFollowing ? 'Following' : 'Follow'}
        </button>
      ) : null}
    </div>
  );
}
