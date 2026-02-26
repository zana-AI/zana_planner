import type { PublicActivityActor, PublicUser } from '../types';
import { generateUsername, getInitialsFromUsername } from './usernameGenerator';

type PublicIdentity = Pick<
  PublicUser,
  'user_id' | 'first_name' | 'last_name' | 'display_name' | 'username' | 'avatar_path' | 'weekly_activity_count' | 'last_activity_at_utc'
> | Pick<
  PublicActivityActor,
  'user_id' | 'first_name' | 'last_name' | 'display_name' | 'username' | 'avatar_path' | 'weekly_activity_count' | 'last_activity_at_utc'
>;

function daysSince(timestampUtc?: string): number | null {
  if (!timestampUtc) return null;
  const date = new Date(timestampUtc);
  if (Number.isNaN(date.getTime())) return null;
  const diffMs = Date.now() - date.getTime();
  if (diffMs < 0) return 0;
  return Math.floor(diffMs / (24 * 60 * 60 * 1000));
}

export function getPublicDisplayName(user: PublicIdentity): string {
  if (user.display_name) return user.display_name;
  if (user.first_name && user.last_name) return `${user.first_name} ${user.last_name}`;
  if (user.first_name) return user.first_name;
  if (user.username) return `@${user.username}`;
  return generateUsername(user.user_id);
}

export function getPublicInitials(user: PublicIdentity): string {
  if (user.display_name) {
    const parts = user.display_name.trim().split(/\s+/);
    if (parts.length > 1) {
      return `${parts[0][0] ?? ''}${parts[parts.length - 1][0] ?? ''}`.toUpperCase();
    }
    return (parts[0][0] ?? '?').toUpperCase();
  }

  if (user.first_name && user.last_name) {
    return `${user.first_name[0] ?? ''}${user.last_name[0] ?? ''}`.toUpperCase();
  }

  if (user.first_name) {
    return (user.first_name[0] ?? '?').toUpperCase();
  }

  return getInitialsFromUsername(generateUsername(user.user_id));
}

export function getAvatarColor(userId: string): string {
  let hash = 0;
  for (let i = 0; i < userId.length; i += 1) {
    hash = userId.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 65%, 50%)`;
}

export function getActivityState(
  weeklyActivityCount?: number,
  lastActivityAtUtc?: string
): 'active' | 'recent' | 'idle' {
  if ((weeklyActivityCount ?? 0) > 0) return 'active';
  const days = daysSince(lastActivityAtUtc);
  if (days !== null && days <= 7) return 'recent';
  return 'idle';
}

export function getActivityMicroLabel(
  weeklyActivityCount?: number,
  lastActivityAtUtc?: string
): string {
  const weekly = weeklyActivityCount ?? 0;
  if (weekly > 0) return `${weekly}/wk`;
  const days = daysSince(lastActivityAtUtc);
  if (days === null) return 'new';
  if (days <= 1) return 'today';
  if (days <= 7) return `${days}d`;
  return 'idle';
}
