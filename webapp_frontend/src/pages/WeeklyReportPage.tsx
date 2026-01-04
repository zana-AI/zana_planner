import { useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams, useNavigate, useLocation } from 'react-router-dom';
import { useTelegramWebApp, getDevInitData } from '../hooks/useTelegramWebApp';
import { apiClient, ApiError } from '../api/client';
import { WeeklyReport } from '../components/WeeklyReport';
import type { WeeklyReportData } from '../types';

export function WeeklyReportPage() {
  const { user, initData, isReady, hapticFeedback } = useTelegramWebApp();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState<string>('');
  const [reportData, setReportData] = useState<WeeklyReportData | null>(null);
  
  // Determine if we're on the tasks route (one-time only)
  const isTasksView = location.pathname === '/tasks';

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

    if (!authData) {
      // No auth data: redirect to home (shouldn't happen due to route guard, but safety check)
      navigate('/', { replace: true });
      return;
    }

    // Extract ref_time from query params
    const refTime = searchParams.get('ref_time') || undefined;
    
    fetchReport(authData, refTime);
  }, [isReady, initData, fetchReport, searchParams, navigate]);

  const handleRetry = useCallback(() => {
    const authData = initData || getDevInitData();
    if (authData) {
      const refTime = searchParams.get('ref_time') || undefined;
      fetchReport(authData, refTime);
    }
  }, [initData, fetchReport, searchParams]);

  const handleRefresh = useCallback(() => {
    const authData = initData || getDevInitData();
    const refTime = searchParams.get('ref_time') || undefined;
    fetchReport(authData, refTime);
  }, [initData, fetchReport, searchParams]);

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

  // Filter and recompute totals for tasks view
  const filteredData = useMemo(() => {
    if (!reportData) return null;
    
    if (!isTasksView) {
      // Return all promises for /weekly route
      return reportData;
    }
    
    // Filter to only one-time tasks (recurring === false)
    const filteredPromises: Record<string, typeof reportData.promises[string]> = {};
    let filteredTotalPromised = 0;
    let filteredTotalSpent = 0;
    
    for (const [id, promiseData] of Object.entries(reportData.promises)) {
      // Include if recurring is explicitly false or undefined (treat undefined as one-time for safety)
      if (promiseData.recurring === false || promiseData.recurring === undefined) {
        filteredPromises[id] = promiseData;
        filteredTotalPromised += promiseData.hours_promised || 0;
        filteredTotalSpent += promiseData.hours_spent || 0;
      }
    }
    
    return {
      ...reportData,
      promises: filteredPromises,
      total_promised: filteredTotalPromised,
      total_spent: filteredTotalSpent,
    };
  }, [reportData, isTasksView]);

  // Show weekly report
  // If state is ready but no reportData, show loading (shouldn't happen, but safety check)
  if (!reportData || !filteredData) {
    return (
      <div className="app">
        <div className="loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading your weekly report...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      {/* User greeting if available */}
      {user && (
        <div className="user-greeting">
          Hi, <span className="user-name">{user.first_name}</span>! 👋
        </div>
      )}

      {/* Navigation header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', padding: '0 1rem' }}>
        <h1 style={{ margin: 0, fontSize: '1.5rem' }}>
          {isTasksView ? 'One-time Tasks' : 'Weekly Report'}
        </h1>
        <button
          onClick={() => navigate('/templates')}
          style={{
            padding: '0.5rem 1rem',
            backgroundColor: '#4CAF50',
            color: 'white',
            border: 'none',
            borderRadius: '8px',
            cursor: 'pointer',
            fontSize: '0.9rem',
            fontWeight: '500'
          }}
        >
          📋 Browse Templates
        </button>
      </div>

      {/* Weekly Report */}
      <WeeklyReport 
        data={filteredData} 
        onRefresh={handleRefresh}
      />
    </div>
  );
}

