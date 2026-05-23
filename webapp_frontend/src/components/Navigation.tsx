import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate, useNavigationType } from 'react-router-dom';
import { ArrowLeft, Library, LogOut, Settings, Shield, Timer } from 'lucide-react';
import { apiClient } from '../api/client';
import { shouldUseLocalMockData } from '../api/mockData';
import { getDevInitData, useTelegramWebApp } from '../hooks/useTelegramWebApp';
import { useTelegramBackButton } from '../hooks/useTelegramBackButton';
import { useSessionMode } from '../hooks/useSessionMode';
import type { AppNavItem, UserInfo } from '../types';
import { BottomNav } from './ui/BottomNav';
import { IconButton } from './ui/IconButton';

interface ShellPageMeta {
  title: string;
  subtitle?: string;
  showBack?: boolean;
  fallbackRoute?: string;
}

function getShellPageMeta(pathname: string): ShellPageMeta {
  if (pathname === '/dashboard') {
    return { title: 'My Week', subtitle: 'Your weekly promises and progress' };
  }
  if (pathname === '/community') {
    return { title: 'Community', subtitle: 'Recent public activity and people you follow' };
  }
  if (pathname === '/templates') {
    return { title: 'Explore', subtitle: 'Promise library and marketplace' };
  }
  if (pathname === '/my-contents') {
    return { title: 'My Contents', subtitle: 'Saved videos, articles, and podcasts', showBack: true, fallbackRoute: '/templates' };
  }
  if (pathname === '/admin') {
    return { title: 'Admin', showBack: true, fallbackRoute: '/dashboard' };
  }
  if (pathname === '/focus') {
    return { title: 'Start Focus Session', showBack: true, fallbackRoute: '/dashboard' };
  }
  if (pathname === '/settings') {
    return { title: 'Settings', showBack: true, fallbackRoute: '/dashboard' };
  }
  if (pathname === '/timezone') {
    return { title: 'Timezone', subtitle: 'Select your timezone', showBack: true, fallbackRoute: '/settings' };
  }
  if (pathname.startsWith('/templates/')) {
    return { title: 'Add Promise', showBack: true, fallbackRoute: '/templates' };
  }
  if (pathname.startsWith('/users/')) {
    return { title: 'Profile', showBack: true, fallbackRoute: '/community' };
  }
  if (pathname.startsWith('/clubs/')) {
    return { title: 'Club', showBack: true, fallbackRoute: '/community' };
  }
  return { title: 'Xaana' };
}

interface NavigationProps {}

export function Navigation(_props: NavigationProps) {
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
  const isAuthenticated = !!authData || hasToken || shouldUseLocalMockData();

  const navItems = useMemo<AppNavItem[]>(
    () => [
      { key: 'today', label: 'My Week', to: '/dashboard' },
      { key: 'community', label: 'Community', to: '/community' },
      { key: 'explore', label: 'Explore', to: '/templates' },
    ],
    [],
  );

  useEffect(() => {
    if (hasToken && !authData) {
      apiClient.getUserInfo().then(setUserInfo).catch(() => undefined);
    }
  }, [hasToken, authData]);

  useEffect(() => {
    const checkAdmin = async () => {
      if (!isAuthenticated) {
        setIsAdmin(false);
        return;
      }
      try {
        if (authData) apiClient.setInitData(authData);
        const result = await apiClient.checkAdminStatus();
        setIsAdmin(result.is_admin);
      } catch {
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
    if (lastRoute === currentRoute) return;
    if (navigationType === 'POP') routeStackRef.current.pop();
    else if (navigationType === 'PUSH') routeStackRef.current.push(lastRoute);
    lastRouteRef.current = currentRoute;
    setCanGoBack(routeStackRef.current.length > 0);
  }, [currentRoute, navigationType]);

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

  if (!isAuthenticated || location.pathname === '/') return null;

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
      <header className="app-header-v2">
        <button type="button" className="brand" onClick={() => navigate('/dashboard')} aria-label="Go to My Week" />
        {shouldShowBack ? (
          <IconButton label="Back" icon={<ArrowLeft size={18} />} onClick={handleBack} />
        ) : null}
        <div className="titles">
          <h1>{shellPage.title}</h1>
          {shellPage.subtitle ? <p>{shellPage.subtitle}</p> : null}
        </div>
        {isDashboard ? (
          <button type="button" className="icon-btn-v2" onClick={() => navigate('/focus')} aria-label="Start focus">
            <Timer size={18} />
          </button>
        ) : null}
        <div style={{ position: 'relative' }} ref={menuRef}>
          <button type="button" className="avatar" onClick={() => setShowProfileMenu((prev) => !prev)} aria-label="Open profile menu">
            {telegramUser?.photo_url ? (
              <img src={telegramUser.photo_url} alt={displayName} style={{ width: '100%', height: '100%', borderRadius: '999px', objectFit: 'cover' }} />
            ) : (
              displayInitial
            )}
          </button>
          {showProfileMenu ? (
            <div className="profile-menu-v2">
              <button type="button" onClick={() => { navigate('/my-contents'); setShowProfileMenu(false); }}>
                <Library size={16} />
                My Contents
              </button>
              <button type="button" onClick={() => { navigate('/settings'); setShowProfileMenu(false); }}>
                <Settings size={16} />
                Settings
              </button>
              {isAdmin ? (
                <button type="button" onClick={() => { navigate('/admin'); setShowProfileMenu(false); }}>
                  <Shield size={16} />
                  Admin Panel
                </button>
              ) : null}
              {sessionMode === 'browser_token' ? (
                <button type="button" onClick={handleLogout}>
                  <LogOut size={16} />
                  Logout
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      </header>
      {!isAdminRoute ? (
        <BottomNav
          items={navItems.map((item) =>
            item.key === 'explore'
              ? { ...item, to: isExploreActive ? location.pathname : item.to }
              : item,
          )}
        />
      ) : null}
    </>
  );
}
