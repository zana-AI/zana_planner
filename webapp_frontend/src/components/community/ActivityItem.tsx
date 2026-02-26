import { useState, type MouseEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import type { PublicActivityItem } from '../../types';
import { getDicebearUrl } from '../../utils/dicebearAvatar';
import {
  getActivityState,
  getAvatarColor,
  getPublicDisplayName,
  getPublicInitials,
} from '../../utils/publicUserDisplay';
import {
  buildActivitySummary,
  formatDurationMinutes,
  formatRelativeTimestamp,
} from '../../utils/activityFormat';

interface ActivityItemProps {
  item: PublicActivityItem;
  currentUserId?: string;
  isFollowing: boolean;
  followPending?: boolean;
  onToggleFollow?: (targetUserId: string) => void;
}

export function ActivityItem({
  item,
  currentUserId,
  isFollowing,
  followPending = false,
  onToggleFollow,
}: ActivityItemProps) {
  const navigate = useNavigate();
  const actor = item.actor;
  const [imageError, setImageError] = useState(false);
  const [dicebearError, setDicebearError] = useState(false);

  const displayName = getPublicDisplayName(actor);
  const initials = getPublicInitials(actor);
  const avatarColor = getAvatarColor(actor.user_id);
  const activityState = getActivityState(actor.weekly_activity_count, actor.last_activity_at_utc);
  const actionText = buildActivitySummary(item);
  const relativeTime = formatRelativeTimestamp(item.timestamp_utc);
  const durationText = formatDurationMinutes(item.duration_minutes);
  const canToggleFollow = !!currentUserId && actor.user_id !== currentUserId && !!onToggleFollow;

  const avatarUrl = !imageError && actor.avatar_path
    ? (actor.avatar_path.startsWith('http') ? actor.avatar_path : `/api/media/avatars/${actor.user_id}`)
    : null;

  const openProfile = () => {
    navigate(`/users/${actor.user_id}`);
  };

  const onToggleFollowClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (!onToggleFollow || followPending) return;
    onToggleFollow(actor.user_id);
  };

  return (
    <article className="community-activity-item">
      <button
        type="button"
        className="community-activity-avatar-wrap"
        onClick={openProfile}
        aria-label={`Open ${displayName} profile`}
      >
        <div className="community-activity-avatar">
          {avatarUrl ? (
            <img
              src={avatarUrl}
              alt={displayName}
              className="community-activity-avatar-img"
              onError={() => setImageError(true)}
            />
          ) : !dicebearError ? (
            <img
              src={getDicebearUrl(actor.user_id)}
              alt={displayName}
              className="community-activity-avatar-img"
              onError={() => setDicebearError(true)}
            />
          ) : (
            <div className="community-activity-avatar-initials" style={{ backgroundColor: avatarColor }}>
              {initials}
            </div>
          )}
        </div>
        <span className={`community-activity-status community-activity-status-${activityState}`} />
      </button>

      <div className="community-activity-main">
        <div className="community-activity-line">
          <button type="button" className="community-activity-name" onClick={openProfile}>
            {displayName}
          </button>
          <span className="community-activity-text">{actionText}</span>
        </div>
        <div className="community-activity-meta">
          {durationText ? <span className="community-activity-duration">{durationText}</span> : null}
          <span className="community-activity-time">{relativeTime}</span>
        </div>
      </div>

      <div className="community-activity-actions">
        <button type="button" className="community-activity-btn" onClick={openProfile}>Profile</button>
        {canToggleFollow ? (
          <button
            type="button"
            className={`community-activity-btn ${isFollowing ? 'following' : ''}`}
            onClick={onToggleFollowClick}
            disabled={followPending}
          >
            {followPending ? '...' : isFollowing ? 'Following' : 'Follow'}
          </button>
        ) : null}
      </div>
    </article>
  );
}
