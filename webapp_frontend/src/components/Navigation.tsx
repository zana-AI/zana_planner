import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate, useNavigationType } from 'react-router-dom';
import { ArrowLeft, Library, LogOut, Settings, Shield } from 'lucide-react';
import { apiClient } from '../api/client';
import { getDevInitData, useTelegramWebApp } from '../hooks/useTelegramWebApp';
import { useTelegramBackButton } from '../hooks/useTelegramBackButton';
import { useSessionMode } from '../hooks/useSessionMode';
import type { AppNavItem, UserInfo } from '../types';
import { AppLogo } from './ui/AppLogo';
import { BottomNav } from './ui/BottomNav';
import { Button } from './ui/Button';
import { IconButton } from './ui/IconButton';

interface ShellPageMeta {
  title: string;
  subtitle?: string;
  showBack?: boolean;
  fallbackRoute?: string;
}

function getShellPageMeta(pathname: string): ShellPageMeta {
  if (pathname === '/dashboard') {
    return {
      title: 'My Week',
      subtitle: 'Your weekly promises and progress',
    };
  }

  if (pathname === '/community') {
    return {
      title: 'Community',
      subtitle: 'Recent public activity and people you follow',
    };
  }

  if (pathname === '/templates') {
    return {
      title: 'Explore',
      subtitle: 'Promise library and marketplace',
    };
  }

  if (pathname === '/my-contents') {
    return {
      title: 'My Contents',
      subtitle: 'Saved videos, articles, and podcasts',
      showBack: true,
      fallbackRoute: '/templates',
    };
  }

  if (pathname === '/admin') {
    return {
      title: 'Admin',
      showBack: true,
      fallbackRoute: '/dashboard',
    };
  }

  if (pathname === '/focus') {
    return {
      title: 'Start Focus Session',
      showBack: true,
      fallbackRoute: '/dashboard',
    };
  }

  if (pathname === '/settings') {
    return {
      title: 'Settings',
      showBack: true,
      fallbackRoute: '/dashboard',
    };
  }

  if (pathname === '/timezone') {
    return {
      title: 'Timezone',
      subtitle: 'Select your timezone',
      showBack: true,
      fallbackRoute: '/settings',
    };
  }

  if (pathname.startsWith('/templates/')) {
    return {
      title: 'Add Promise',
      showBack: true,
      fallbackRoute: '/templates',
    };
  }

  if (pathname.startsWith('/users/')) {
    return {
      title: 'Profile',
      showBack: true,
      fallbackRoute: '/community',
    };
  }

  if (pathname.startsWith('/clubs/')) {
    return {
      title: 'Club',
      showBack: true,
      fallbackRoute: '/community',
    };
  }

  return {
    title: 'Xaana',
  };
}

export function Navigation() {
  const navigate = useNavigate();
  const location = useLocation();
  const navigationType = useNavigationType();
  const { initData, user: telegramUser } = useTelegramWebApp();
  const sessionMode = useSessionMode();
  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [canGoBack, setCanGoBack] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const routeStackRef = useRef<string[]>([]);
  const lastRouteRef = useRef<string | null>(null);

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

  const currentRoute = `${location.pathname}${location.search}${location.hash}`;

  useEffect(() => {
    const lastRoute = lastRouteRef.current;

    if (!lastRoute) {
      lastRouteRef.current = currentRoute;
      setCanGoBack(false);
      return;
    }

    if (lastRoute === currentRoute) {
      return;
    }

    if (navigationType === 'POP') {
      routeStackRef.current.pop();
    } else if (navigationType === 'PUSH') {
      routeStackRef.current.push(lastRoute);
    }

    lastRouteRef.current = currentRoute;
    setCanGoBack(routeStackRef.current.length > 0);
  }, [currentRoute, navigationType]);

  // NOTE: handleBack (useCallback) and useTelegramBackButton (useEffect) must be
  // called BEFORE the early return to satisfy React rules of hooks.
  const shellPage = getShellPageMeta(location.pathname);
  const isDashboard = location.pathname === '/dashboard';
  const isAdminRoute = location.pathname === '/admin';
  const shouldShowBack = canGoBack || !!shellPage.showBack;

  const handleLogout = () => {
    apiClient.clearAuth();
    window.dispatchEvent(new Event('logout'));
    setShowProfileMenu(false);
    navigate('/', { replace: true });
  };

  const handleBack = useCallback(() => {
    if (canGoBack && window.history.length > 1) {
      navigate(-1);
      return;
    }
    navigate(shellPage.fallbackRoute || '/dashboard', { replace: true });
  }, [canGoBack, navigate, shellPage.fallbackRoute]);

  useTelegramBackButton({ enabled: shouldShowBack, onClick: handleBack });

  if (!isAuthenticated || location.pathname === '/') {
    return null;
  }
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
        <div className="app-shell-left">
          <button className="app-shell-brand" onClick={() => navigate('/dashboard')} aria-label="Go to My Week">
            <AppLogo size={40} />
          </button>

          {shouldShowBack ? (
            <IconButton
              className="app-shell-back-button"
              variant="soft"
              label="Back"
              icon={<ArrowLeft size={18} />}
              onClick={handleBack}
            />
          ) : null}

          <div className="app-shell-page-title">
            <h1>{shellPage.title}</h1>
            {shellPage.subtitle ? <p>{shellPage.subtitle}</p> : null}
          </div>
        </div>

        <div className="app-shell-right">
          {isDashboard ? (
            <Button size="sm" onClick={() => navigate('/focus')}>
              Start Focus
            </Button>
          ) : null}

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
        </div>
      </header>

      {!isAdminRoute ? (
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
      ) : null}
    </>
  );
}
