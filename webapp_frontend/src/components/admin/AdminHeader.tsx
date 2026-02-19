import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bot, LogOut, Settings, Shield } from 'lucide-react';
import { apiClient } from '../../api/client';
import type { SessionMode, UserInfo } from '../../types';
import { AppLogo } from '../ui/AppLogo';

interface AdminHeaderProps {
  telegramUser: any;
  userInfo: UserInfo | null;
  botUsername: string | null;
  showProfileMenu: boolean;
  setShowProfileMenu: (show: boolean) => void;
  sessionMode: SessionMode;
}

export function AdminHeader({
  telegramUser,
  userInfo,
  botUsername,
  showProfileMenu,
  setShowProfileMenu,
  sessionMode,
}: AdminHeaderProps) {
  const navigate = useNavigate();
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowProfileMenu(false);
      }
    };

    if (showProfileMenu) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
    return undefined;
  }, [showProfileMenu, setShowProfileMenu]);

  const handleLogout = () => {
    apiClient.clearAuth();
    window.dispatchEvent(new Event('logout'));
    setShowProfileMenu(false);
    navigate('/', { replace: true });
  };

  const displayName =
    userInfo?.first_name || telegramUser?.first_name || telegramUser?.username || userInfo?.user_id?.toString() || 'User';
  const displayInitial = displayName.charAt(0).toUpperCase();

  return (
    <div className="admin-panel-header admin-panel-header-new">
      <div className="admin-header-brand">
        <AppLogo size={22} />
        <h1 className="admin-panel-title">Admin</h1>
      </div>

      <div className="app-shell-profile-wrap" ref={menuRef}>
        <button className="app-shell-avatar" onClick={() => setShowProfileMenu(!showProfileMenu)}>
          {telegramUser?.photo_url ? <img src={telegramUser.photo_url} alt={displayName} /> : <span>{displayInitial}</span>}
        </button>

        {showProfileMenu ? (
          <div className="app-shell-menu">
            <div className="app-shell-menu-user">{displayName}</div>
            <button
              className="app-shell-menu-item"
              onClick={() => {
                navigate('/dashboard');
                setShowProfileMenu(false);
              }}
            >
              <Shield size={16} />
              <span>My Week</span>
            </button>
            <button
              className="app-shell-menu-item"
              onClick={() => {
                navigate('/settings');
                setShowProfileMenu(false);
              }}
            >
              <Settings size={16} />
              <span>Settings</span>
            </button>
            <a
              className="app-shell-menu-item"
              href={botUsername ? `https://t.me/${botUsername}` : 'https://t.me/zana_planner_bot'}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => setShowProfileMenu(false)}
            >
              <Bot size={16} />
              <span>Open Bot</span>
            </a>
            {sessionMode === 'browser_token' ? (
              <button className="app-shell-menu-item app-shell-menu-item-danger" onClick={handleLogout}>
                <LogOut size={16} />
                <span>Logout</span>
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
