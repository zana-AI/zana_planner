import { useState, useEffect, useCallback } from 'react';
import { useTelegramWebApp, getDevInitData } from './hooks/useTelegramWebApp';
import { apiClient, ApiError } from './api/client';
import { WeeklyReport } from './components/WeeklyReport';
import { UsersPage } from './components/UsersPage';
import { HomePage } from './components/HomePage';
import { AdminPanel } from './components/AdminPanel';
import type { WeeklyReportData } from './types';

type AppState = 'loading' | 'ready' | 'error';

function App() {
  const { user, initData, isReady, hapticFeedback } = useTelegramWebApp();
  const [state, setState] = useState<AppState>('loading');
  const [error, setError] = useState<string>('');
  const [reportData, setReportData] = useState<WeeklyReportData | null>(null);

  const fetchReport = useCallback(async (authData: string, refTime?: string) => {
    setState('loading');
    setError('');

    try {
      // Set auth data for API client
      apiClient.setInitData(authData);

      // Fetch weekly report with optional ref_time
      const data = await apiClient.getWeeklyReport(refTime);
      setReportData(data);
      setState('ready');
      hapticFeedback('success');
    } catch (err) {
      console.error('Failed to fetch report:', err);
      
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setError('Authentication failed. Please reopen the app from Telegram.');
        } else {
          setError(err.message);
        }
      } else {
        setError('Failed to load your weekly report. Please try again.');
      }
      
      setState('error');
      hapticFeedback('error');
    }
  }, [hapticFeedback]);

  useEffect(() => {
    if (!isReady) return;

    // Use Telegram initData if available, otherwise try dev data
    const authData = initData || getDevInitData();

    // Extract route parameter from multiple sources:
    // 1. Telegram's start_param (if available via WebApp SDK)
    // 2. URL hash fragment (e.g., #admin - Telegram preserves these better)
    // 3. URL query parameter (e.g., ?startapp=admin - for backward compatibility)
    // 4. page parameter (for browser testing)
    const urlParams = new URLSearchParams(window.location.search);
    const startappParam = urlParams.get('startapp');
    const pageParam = urlParams.get('page');
    const hash = window.location.hash.slice(1); // Remove the # symbol
    
    // Check Telegram's start_param if available
    const tg = window.Telegram?.WebApp;
    const telegramStartParam = tg?.initDataUnsafe?.start_param;
    
    // Combine all sources - Telegram start_param takes precedence, then hash, then query param
    const effectiveRoute = telegramStartParam || hash || startappParam;
    
    // Debug logging
    console.log('[DEBUG] Current URL:', window.location.href);
    console.log('[DEBUG] URL hash:', hash);
    console.log('[DEBUG] URL search params:', window.location.search);
    console.log('[DEBUG] startapp param (URL):', startappParam);
    console.log('[DEBUG] start_param (Telegram):', telegramStartParam);
    console.log('[DEBUG] effective route:', effectiveRoute);
    
    // If route=community or page=community, don't fetch report (show community page instead)
    if (effectiveRoute === 'community' || pageParam === 'community') {
      setState('ready');
      return;
    }
    
    // If route=admin or page=admin, don't fetch report (show admin panel instead)
    if (effectiveRoute === 'admin' || pageParam === 'admin') {
      setState('ready');
      return;
    }

    if (!authData) {
      // No auth data: show public users page instead of error
      setState('ready');
      return;
    }

    // Extract ref_time from effective route (format: "weekly:ISO_DATE")
    // Fallback to query param for backward compatibility
    let refTime: string | undefined = undefined;
    if (effectiveRoute && effectiveRoute.startsWith('weekly:')) {
      // Extract and decode ISO date after "weekly:"
      const encodedRefTime = effectiveRoute.substring(7);
      refTime = decodeURIComponent(encodedRefTime);
    } else {
      refTime = urlParams.get('ref_time') || undefined;
    }
    
    console.log('[DEBUG] Extracted ref_time:', refTime);

    fetchReport(authData, refTime);
  }, [isReady, initData, fetchReport]);

  const handleRetry = useCallback(() => {
    const authData = initData || getDevInitData();
    if (authData) {
      // Extract ref_time from URL query parameters
      const urlParams = new URLSearchParams(window.location.search);
      const refTime = urlParams.get('ref_time') || undefined;
      fetchReport(authData, refTime);
    }
  }, [initData, fetchReport]);

  // Check if we have authentication
  const authData = initData || getDevInitData();
  const isAuthenticated = !!authData;

  // Check if user wants to see community/admin page (check multiple sources)
  const urlParamsForPage = new URLSearchParams(window.location.search);
  const hashForPage = window.location.hash.slice(1);
  const tgForPage = window.Telegram?.WebApp;
  const telegramStartParamForPage = tgForPage?.initDataUnsafe?.start_param;
  const effectiveRouteForPage = telegramStartParamForPage || hashForPage || urlParamsForPage.get('startapp');
  
  const showCommunity = effectiveRouteForPage === 'community' || urlParamsForPage.get('page') === 'community';
  const showAdmin = effectiveRouteForPage === 'admin' || urlParamsForPage.get('page') === 'admin';

  // Loading state (only for authenticated users loading report, not for community/admin pages)
  if ((state === 'loading' || !isReady) && isAuthenticated && !showCommunity && !showAdmin) {
    return (
      <div className="app">
        <div className="loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading your weekly report...</div>
        </div>
      </div>
    );
  }

  // Error state (only for authenticated users loading report, not for community/admin pages)
  if (state === 'error' && isAuthenticated && !showCommunity && !showAdmin) {
    return (
      <div className="app">
        <div className="error">
          <div className="error-icon">😕</div>
          <h1 className="error-title">Something went wrong</h1>
          <p className="error-message">{error}</p>
          {initData && (
            <button className="retry-button" onClick={handleRetry}>
              Try Again
            </button>
          )}
        </div>
      </div>
    );
  }

  // Show admin panel if requested (admin only, backend will verify)
  if (showAdmin) {
    return (
      <div className="app">
        <AdminPanel />
      </div>
    );
  }

  // Show community page if requested (for both authenticated and unauthenticated users)
  if (showCommunity) {
    return (
      <div className="app">
        <UsersPage />
      </div>
    );
  }

  // Not authenticated: show home page
  if (!isAuthenticated) {
    return (
      <div className="app">
        <HomePage />
      </div>
    );
  }

  // Authenticated: show weekly report
  return (
    <div className="app">
      {/* User greeting if available */}
      {user && (
        <div className="user-greeting">
          Hi, <span className="user-name">{user.first_name}</span>! 👋
        </div>
      )}

      {/* Weekly Report */}
      {reportData && (
        <WeeklyReport 
          data={reportData} 
          onRefresh={() => {
            const urlParams = new URLSearchParams(window.location.search);
            const refTime = urlParams.get('ref_time') || undefined;
            fetchReport(initData || getDevInitData(), refTime);
          }}
        />
      )}
    </div>
  );
}

export default App;
