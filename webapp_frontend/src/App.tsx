import { useState, useEffect, useCallback } from 'react';
import { useTelegramWebApp, getDevInitData } from './hooks/useTelegramWebApp';
import { apiClient, ApiError } from './api/client';
import { WeeklyReport } from './components/WeeklyReport';
import type { WeeklyReportData } from './types';

type AppState = 'loading' | 'ready' | 'error';

function App() {
  const { user, initData, isReady, hapticFeedback } = useTelegramWebApp();
  const [state, setState] = useState<AppState>('loading');
  const [error, setError] = useState<string>('');
  const [reportData, setReportData] = useState<WeeklyReportData | null>(null);

  const fetchReport = useCallback(async (authData: string) => {
    setState('loading');
    setError('');

    try {
      // Set auth data for API client
      apiClient.setInitData(authData);

      // Fetch weekly report
      const data = await apiClient.getWeeklyReport();
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

    if (!authData) {
      // In development without auth data, show a friendly message
      if (import.meta.env.DEV) {
        setError(
          'No Telegram authentication data found. ' +
          'To test locally, set dev_init_data in localStorage or open from Telegram.'
        );
        setState('error');
        return;
      }
      
      setError('Please open this app from Telegram.');
      setState('error');
      return;
    }

    fetchReport(authData);
  }, [isReady, initData, fetchReport]);

  const handleRetry = useCallback(() => {
    const authData = initData || getDevInitData();
    if (authData) {
      fetchReport(authData);
    }
  }, [initData, fetchReport]);

  // Loading state
  if (state === 'loading' || !isReady) {
    return (
      <div className="app">
        <div className="loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading your weekly report...</div>
        </div>
      </div>
    );
  }

  // Error state
  if (state === 'error') {
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

  // Ready state with data
  return (
    <div className="app">
      {/* User greeting if available */}
      {user && (
        <div className="user-greeting">
          Hi, <span className="user-name">{user.first_name}</span>! 👋
        </div>
      )}

      {/* Weekly Report */}
      {reportData && <WeeklyReport data={reportData} />}

      {/* Refresh hint */}
      <div className="refresh-hint">
        Pull down to refresh
      </div>
    </div>
  );
}

export default App;
