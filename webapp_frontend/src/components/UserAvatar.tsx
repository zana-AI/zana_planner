import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import { apiClient } from '../api/client';
import { useState, useEffect } from 'react';
import type { UserInfo } from '../types';

interface UserAvatarProps {
  size?: number;
  showMenu?: boolean;
  onMenuClick?: () => void;
}

export function UserAvatar({ size = 40, showMenu = false, onMenuClick }: UserAvatarProps) {
  const { user: telegramUser, initData } = useTelegramWebApp();
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const hasToken = !!localStorage.getItem('telegram_auth_token');

  // Fetch user info for browser login users
  useEffect(() => {
    if (hasToken && !initData) {
      apiClient.getUserInfo()
        .then(setUserInfo)
        .catch(() => {
          console.error('Failed to fetch user info');
        });
    }
  }, [hasToken, initData]);

  const displayName = userInfo?.first_name || telegramUser?.first_name || telegramUser?.username || userInfo?.user_id?.toString() || 'User';
  const displayInitial = (userInfo?.first_name || telegramUser?.first_name || telegramUser?.username || 'U').charAt(0).toUpperCase();

  return (
    <button
      onClick={onMenuClick}
      style={{
        background: 'rgba(255, 255, 255, 0.1)',
        border: '1px solid rgba(255, 255, 255, 0.2)',
        borderRadius: '50%',
        width: `${size}px`,
        height: `${size}px`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#fff',
        fontSize: `${size * 0.4}px`,
        fontWeight: 'bold',
        cursor: showMenu ? 'pointer' : 'default',
        transition: 'all 0.2s',
        padding: 0,
        overflow: 'hidden'
      }}
      onMouseEnter={(e) => {
        if (showMenu) {
          e.currentTarget.style.background = 'rgba(255, 255, 255, 0.2)';
        }
      }}
      onMouseLeave={(e) => {
        if (showMenu) {
          e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
        }
      }}
    >
      {telegramUser?.photo_url ? (
        <img
          src={telegramUser.photo_url}
          alt={displayName}
          style={{
            width: '100%',
            height: '100%',
            borderRadius: '50%',
            objectFit: 'cover'
          }}
        />
      ) : (
        displayInitial
      )}
    </button>
  );
}

