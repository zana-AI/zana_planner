import { useEffect, useState, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTelegramWebApp, getDevInitData } from '../hooks/useTelegramWebApp';
import { apiClient, ApiError } from '../api/client';
import { WeeklyReport } from '../components/WeeklyReport';
import type { WeeklyReportData, UserInfo } from '../types';

export function DashboardPage() {
  const navigate = useNavigate();
  const { user, initData, isReady, hapticFeedback } = useTelegramWebApp();
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [reportData, setReportData] = useState<WeeklyReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');

  const fetchReport = useCallback(async (authData: string) => {
    setLoading(true);
    setError('');

    try {
      // Set auth data for API client (only if we have initData)
      if (authData) {
        apiClient.setInitData(authData);
      }
      // Otherwise, API client will use token from localStorage

      // Fetch weekly report
      const data = await apiClient.getWeeklyReport();
      setReportData(data);
      hapticFeedback('success');
    } catch (err) {
      console.error('Failed to fetch report:', err);
      
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setError('Authentication failed. Please log in again.');
          apiClient.clearAuth();
          window.dispatchEvent(new Event('logout'));
          navigate('/', { replace: true });
        } else {
          setError(err.message);
        }
      } else {
        setError('Failed to load your dashboard. Please try again.');
      }
      hapticFeedback('error');
    } finally {
      setLoading(false);
    }
  }, [hapticFeedback, navigate]);

  useEffect(() => {
    if (!isReady) return;

    // Check for auth
    const authData = initData || getDevInitData();
    const token = localStorage.getItem('telegram_auth_token');
    
    if (!authData && !token) {
      navigate('/', { replace: true });
      return;
    }

    // Fetch user info and weekly report
    const loadData = async () => {
      try {
        // Set auth for API client
        if (authData) {
          apiClient.setInitData(authData);
        }

        // Fetch user info (optional)
        const info = await apiClient.getUserInfo().catch(() => null);
        setUserInfo(info);
      } catch (error) {
        console.error('Failed to load user info:', error);
      }
    };

    loadData();
    fetchReport(authData || '');
  }, [isReady, initData, navigate, fetchReport]);

  // Filter data into promises (recurring) and tasks (one-time)
  // IMPORTANT: This hook must be called before any conditional returns
  const { promisesData, tasksData } = useMemo(() => {
    if (!reportData) {
      return { promisesData: null, tasksData: null };
    }

    const promises: Record<string, typeof reportData.promises[string]> = {};
    const tasks: Record<string, typeof reportData.promises[string]> = {};
    let promisesTotalPromised = 0;
    let promisesTotalSpent = 0;
    let tasksTotalPromised = 0;
    let tasksTotalSpent = 0;

    for (const [id, promiseData] of Object.entries(reportData.promises)) {
      // Recurring promises (recurring === true)
      if (promiseData.recurring === true) {
        promises[id] = promiseData;
        promisesTotalPromised += promiseData.hours_promised || 0;
        promisesTotalSpent += promiseData.hours_spent || 0;
      } else {
        // One-time tasks (recurring === false or undefined)
        tasks[id] = promiseData;
        tasksTotalPromised += promiseData.hours_promised || 0;
        tasksTotalSpent += promiseData.hours_spent || 0;
      }
    }

    return {
      promisesData: promisesTotalPromised > 0 || Object.keys(promises).length > 0 ? {
        ...reportData,
        promises,
        total_promised: promisesTotalPromised,
        total_spent: promisesTotalSpent,
      } : null,
      tasksData: tasksTotalPromised > 0 || Object.keys(tasks).length > 0 ? {
        ...reportData,
        promises: tasks,
        total_promised: tasksTotalPromised,
        total_spent: tasksTotalSpent,
      } : null,
    };
  }, [reportData]);

  const handleRefresh = useCallback(() => {
    const authData = initData || getDevInitData();
    fetchReport(authData || '');
  }, [initData, fetchReport]);

  const displayName = user?.first_name || userInfo?.user_id?.toString() || 'User';

  // Loading state - must come after all hooks
  if (!isReady || loading) {
    return (
      <div className="app">
        <div className="loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading your workspace...</div>
        </div>
      </div>
    );
  }

  // Error state
  if (error && !loading) {
    return (
      <div className="app">
        <div className="error">
          <div className="error-icon">😕</div>
          <h1 className="error-title">Something went wrong</h1>
          <p className="error-message">{error}</p>
          <button className="retry-button" onClick={handleRefresh}>
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="app" style={{ padding: '1rem', maxWidth: '1200px', margin: '0 auto' }}>
      {/* Welcome Header */}
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.8rem', marginBottom: '0.25rem', color: '#fff' }}>
          Welcome back, {displayName}! 👋
        </h1>
      </div>

      {/* Promises Section */}
      {promisesData && (
        <div style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1.3rem', marginBottom: '1rem', color: '#fff' }}>Promises</h2>
          <WeeklyReport data={promisesData} onRefresh={handleRefresh} />
        </div>
      )}

      {/* Tasks Section */}
      {tasksData && (
        <div style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1.3rem', marginBottom: '1rem', color: '#fff' }}>One-time Tasks</h2>
          <WeeklyReport data={tasksData} onRefresh={handleRefresh} />
        </div>
      )}

      {/* Empty State */}
      {!loading && !promisesData && !tasksData && (
        <div className="empty-state">
          <h2 className="empty-title">No promises or tasks yet</h2>
          <p className="empty-subtitle">
            Start tracking your promises in the Telegram bot to see your progress here.
          </p>
          <button
            onClick={() => navigate('/templates')}
            style={{
              marginTop: '1rem',
              padding: '0.75rem 1.5rem',
              backgroundColor: '#4CAF50',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '1rem',
              fontWeight: '500'
            }}
          >
            📋 Browse Templates
          </button>
        </div>
      )}
    </div>
  );
}

