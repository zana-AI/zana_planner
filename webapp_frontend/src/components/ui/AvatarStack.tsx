import { getAvatarColor } from '../../utils/publicUserDisplay';

export interface AvatarStackUser {
  user_id: string;
  first_name?: string;
  username?: string;
  avatar_path?: string;
}

interface AvatarStackProps {
  users: AvatarStackUser[];
  /** Diameter of each circle in px (default 22) */
  size?: number;
  /** Max visible avatars before "+N" indicator (default 3) */
  max?: number;
}

export function AvatarStack({ users, size = 22, max = 3 }: AvatarStackProps) {
  if (users.length === 0) return null;

  const visible = users.slice(0, max);
  const rest = users.length - visible.length;
  const step = Math.round(size * 0.58); // overlap step
  const totalWidth = size + (visible.length - 1 + (rest > 0 ? 1 : 0)) * step;

  return (
    <div
      className="avatar-stack"
      style={{ width: `${totalWidth}px`, height: `${size}px` }}
    >
      {visible.map((user, i) => {
        const initial = (user.first_name || user.username || 'U').charAt(0).toUpperCase();
        const bg = getAvatarColor(user.user_id);
        const avatarSrc = user.avatar_path
          ? user.avatar_path.startsWith('http')
            ? user.avatar_path
            : `/api/media/avatars/${user.user_id}`
          : null;

        return (
          <div
            key={user.user_id}
            className="avatar-stack-circle"
            style={{
              width: `${size}px`,
              height: `${size}px`,
              left: `${i * step}px`,
              zIndex: max - i,
              backgroundColor: avatarSrc ? undefined : bg,
              fontSize: `${Math.max(8, Math.round(size * 0.42))}px`,
            }}
            title={user.first_name || user.username || user.user_id}
          >
            {avatarSrc ? (
              <img
                src={avatarSrc}
                alt={initial}
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
            ) : (
              initial
            )}
          </div>
        );
      })}

      {rest > 0 && (
        <div
          className="avatar-stack-circle avatar-stack-overflow"
          style={{
            width: `${size}px`,
            height: `${size}px`,
            left: `${visible.length * step}px`,
            zIndex: 0,
            fontSize: `${Math.max(7, Math.round(size * 0.38))}px`,
          }}
          title={`+${rest} more`}
        >
          +{rest}
        </div>
      )}
    </div>
  );
}
