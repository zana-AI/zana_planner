import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
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
  /** Key under `shell.*` in the locale catalogs. */
  key: string;
  hasSubtitle?: boolean;
  showBack?: boolean;
  fallbackRoute?: string;
}

function getShellPageMeta(pathname: string): ShellPageMeta {
  if (pathname === '/dashboard') {
    return { key: 'dashboard', hasSubtitle: true };
  }
  if (pathname === '/community') {
    return { key: 'community', hasSubtitle: true };
  }
  if (pathname === '/templates') {
    return { key: 'explore', hasSubtitle: true };
  }
  if (pathname === '/challenges') {
    return { key: 'challenges', hasSubtitle: true };
  }
  if (pathname === '/flashcards') {
    return { key: 'flashcards', hasSubtitle: true, showBack: true, fallbackRoute: '/dashboard' };
  }
  if (pathname.startsWith('/challenges/')) {
    return { key: 'challengeDetail', showBack: true, fallbackRoute: '/templates' };
  }
  if (pathname === '/my-contents') {
    // A primary tab now, so no back button — there is nothing to go back to.
    return { key: 'myContents', hasSubtitle: true };
  }
  if (pathname === '/admin') {
    return { key: 'admin', showBack: true, fallbackRoute: '/dashboard' };
  }
  if (pathname === '/focus') {
    return { key: 'focus', showBack: true, fallbackRoute: '/dashboard' };
  }
  if (pathname === '/settings') {
    return { key: 'settings', showBack: true, fallbackRoute: '/dashboard' };
  }
  if (pathname === '/timezone') {
    return { key: 'timezone', hasSubtitle: true, showBack: true, fallbackRoute: '/settings' };
  }
  if (pathname.startsWith('/templates/')) {
    return { key: 'addPromise', showBack: true, fallbackRoute: '/templates' };
  }
  if (pathname.startsWith('/users/')) {
    return { key: 'profile', showBack: true, fallbackRoute: '/community' };
  }
  if (pathname.startsWith('/clubs/')) {
    return { key: 'club', showBack: true, fallbackRoute: '/community' };
  }
  return { key: 'fallback' };
}

interface NavigationProps {}

export function Navigation(_props: NavigationProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const navigationType = useNavigationType();
  const isScreenshotRoute = location.pathname.startsWith('/__home-screenshots');
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
      { key: 'today', label: t('nav.myWeek'), to: '/dashboard' },
      { key: 'community', label: t('nav.community'), to: '/community' },
      { key: 'content', label: t('nav.content'), to: '/my-contents' },
      { key: 'explore', label: t('nav.explore'), to: '/templates' },
    ],
    [t],
  );

  useEffect(() => {
    if (hasToken && !authData) {
      apiClient.getUserInfo().then(setUserInfo).catch(() => undefined);
    }
  }, [hasToken, authData]);

  useEffect(() => {
    const checkAdmin = async () => {
      if (isScreenshotRoute || !isAuthenticated) {
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
  }, [authData, isAuthenticated, isScreenshotRoute]);

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

  // `/c/*` is the public club landing page — a standalone page with its own
  // header, shown to visitors who may not have an account. App chrome there
  // would frame it as an app screen and distract from its single CTA.
  const isPublicClubPage = location.pathname.startsWith('/c/');

  if (!isAuthenticated || location.pathname === '/' || isScreenshotRoute || isPublicClubPage) return null;

  const displayName =
    userInfo?.first_name ||
    telegramUser?.first_name ||
    telegramUser?.username ||
    userInfo?.user_id?.toString() ||
    'User';
  const displayInitial = displayName.charAt(0).toUpperCase();

  return (
    <>
      <header className="app-header-v2">
        <button type="button" className="brand" onClick={() => navigate('/dashboard')} aria-label={t('nav.goToMyWeek')} />
        {shouldShowBack ? (
          <IconButton label={t('common.back')} icon={<ArrowLeft size={18} className="icon-directional" />} onClick={handleBack} />
        ) : null}
        <div className="titles">
          <h1>{t(`shell.${shellPage.key}.title`)}</h1>
          {shellPage.hasSubtitle ? <p>{t(`shell.${shellPage.key}.subtitle`)}</p> : null}
        </div>
        {isDashboard ? (
          <button type="button" className="icon-btn-v2" onClick={() => navigate('/focus')} aria-label={t('nav.startFocus')}>
            <Timer size={18} />
          </button>
        ) : null}
        <div style={{ position: 'relative' }} ref={menuRef}>
          <button type="button" className="avatar" onClick={() => setShowProfileMenu((prev) => !prev)} aria-label={t('nav.openProfileMenu')}>
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
                {t('menu.myContents')}
              </button>
              <button type="button" onClick={() => { navigate('/settings'); setShowProfileMenu(false); }}>
                <Settings size={16} />
                {t('menu.settings')}
              </button>
              {isAdmin ? (
                <button type="button" onClick={() => { navigate('/admin'); setShowProfileMenu(false); }}>
                  <Shield size={16} />
                  {t('menu.adminPanel')}
                </button>
              ) : null}
              {sessionMode === 'browser_token' ? (
                <button type="button" onClick={handleLogout}>
                  <LogOut size={16} />
                  {t('menu.logout')}
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      </header>
      {!isAdminRoute ? <BottomNav items={navItems} /> : null}
    </>
  );
}
