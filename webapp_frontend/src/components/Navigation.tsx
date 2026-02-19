import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Bot, Library, LogOut, Settings, Shield, User, Users } from 'lucide-react';
import { apiClient } from '../api/client';
import { getDevInitData, useTelegramWebApp } from '../hooks/useTelegramWebApp';
import { useSessionMode } from '../hooks/useSessionMode';
import type { AppNavItem, UserInfo } from '../types';
import { AppLogo } from './ui/AppLogo';
import { BottomNav } from './ui/BottomNav';

export function Navigation() {
  const navigate = useNavigate();
  const location = useLocation();
  const { initData, user: telegramUser } = useTelegramWebApp();
  const sessionMode = useSessionMode();
  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [botUsername, setBotUsername] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const authData = initData || getDevInitData();
  const hasToken = !!localStorage.getItem('telegram_auth_token');
  const isAuthenticated = !!authData || hasToken;

  const navItems = useMemo<AppNavItem[]>(
    () => [
      { key: 'today', label: 'My Week', to: '/dashboard' },
      { key: 'community', label: 'Community', to: '/community' },
      { key: 'explore', label: 'Explore', to: '/templates' },
    ],
    []
  );

  useEffect(() => {
    if (hasToken && !authData) {
      apiClient.getUserInfo().then(setUserInfo).catch(() => console.error('Failed to fetch user info'));
    }
  }, [hasToken, authData]);

  useEffect(() => {
    const fetchBotUsername = async () => {
      try {
        const response = await fetch('/api/auth/bot-username');
        if (!response.ok) return;
        const data = await response.json();
        if (data.bot_username) {
          setBotUsername(data.bot_username.trim());
        }
      } catch (error) {
        console.error('Failed to fetch bot username:', error);
      }
    };

    if (isAuthenticated) {
      fetchBotUsername();
    }
  }, [isAuthenticated]);

  useEffect(() => {
    const checkAdmin = async () => {
      if (!isAuthenticated) {
        setIsAdmin(false);
        return;
      }

      try {
        if (authData) {
          apiClient.setInitData(authData);
        }
        const result = await apiClient.checkAdminStatus();
        setIsAdmin(result.is_admin);
      } catch (error) {
        console.error('Failed to check admin status:', error);
        setIsAdmin(false);
      }
    };

    checkAdmin();
  }, [authData, isAuthenticated]);

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
  }, [showProfileMenu]);

  if (!isAuthenticated || location.pathname === '/' || location.pathname === '/admin') {
    return null;
  }

  const handleLogout = () => {
    apiClient.clearAuth();
    window.dispatchEvent(new Event('logout'));
    setShowProfileMenu(false);
    navigate('/', { replace: true });
  };

  const displayName =
    userInfo?.first_name ||
    telegramUser?.first_name ||
    telegramUser?.username ||
    userInfo?.user_id?.toString() ||
    'User';
  const displayInitial = displayName.charAt(0).toUpperCase();

  const isExploreActive = location.pathname.startsWith('/templates') || location.pathname === '/my-contents';

  return (
    <>
      <header className="app-shell-header">
        <button className="app-shell-brand" onClick={() => navigate('/dashboard')}>
          <AppLogo size={24} />
        </button>

        <div className="app-shell-profile-wrap" ref={menuRef}>
          <button
            className="app-shell-avatar"
            onClick={() => setShowProfileMenu((prev) => !prev)}
            aria-label="Open profile menu"
          >
            {telegramUser?.photo_url ? (
              <img src={telegramUser.photo_url} alt={displayName} />
            ) : (
              <span>{displayInitial}</span>
            )}
          </button>

          {showProfileMenu && (
            <div className="app-shell-menu">
              <div className="app-shell-menu-user">{displayName}</div>
              <button
                className="app-shell-menu-item"
                onClick={() => {
                  navigate('/dashboard');
                  setShowProfileMenu(false);
                }}
              >
                <User size={16} />
                <span>My Week</span>
              </button>
              <button
                className="app-shell-menu-item"
                onClick={() => {
                  navigate('/community');
                  setShowProfileMenu(false);
                }}
              >
                <Users size={16} />
                <span>Community</span>
              </button>
              <button
                className="app-shell-menu-item"
                onClick={() => {
                  navigate('/templates');
                  setShowProfileMenu(false);
                }}
              >
                <Library size={16} />
                <span>Explore</span>
              </button>
              <button
                className="app-shell-menu-item"
                onClick={() => {
                  navigate('/my-contents');
                  setShowProfileMenu(false);
                }}
              >
                <Library size={16} />
                <span>My Contents</span>
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
                href={botUsername ? `https://t.me/${botUsername}` : 'https://t.me/zana_planner_bot'}
                target="_blank"
                rel="noopener noreferrer"
                className="app-shell-menu-item"
                onClick={() => setShowProfileMenu(false)}
              >
                <Bot size={16} />
                <span>Open Bot</span>
              </a>
              {isAdmin && (
                <button
                  className="app-shell-menu-item app-shell-menu-item-admin"
                  onClick={() => {
                    navigate('/admin');
                    setShowProfileMenu(false);
                  }}
                >
                  <Shield size={16} />
                  <span>Admin Panel</span>
                </button>
              )}
              {sessionMode === 'browser_token' && (
                <button className="app-shell-menu-item app-shell-menu-item-danger" onClick={handleLogout}>
                  <LogOut size={16} />
                  <span>Logout</span>
                </button>
              )}
            </div>
          )}
        </div>
      </header>

      <BottomNav
        items={navItems.map((item) =>
          item.key === 'explore'
            ? {
                ...item,
                to: isExploreActive ? location.pathname : item.to,
              }
            : item
        )}
      />
    </>
  );
}
