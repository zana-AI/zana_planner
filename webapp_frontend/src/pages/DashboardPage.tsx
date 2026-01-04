import { useEffect, useState, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTelegramWebApp, getDevInitData } from '../hooks/useTelegramWebApp';
import { apiClient, ApiError } from '../api/client';
import { WeeklyReport } from '../components/WeeklyReport';
import { UserCard } from '../components/UserCard';
import type { WeeklyReportData, PublicUser } from '../types';

export function DashboardPage() {
  const navigate = useNavigate();
  const { user, initData, isReady, hapticFeedback } = useTelegramWebApp();
  const [reportData, setReportData] = useState<WeeklyReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [communityUsers, setCommunityUsers] = useState<PublicUser[]>([]);
  const [communityLoading, setCommunityLoading] = useState(false);

  const fetchReport = useCallback(async (authData: string) => {
    setLoading(true);
    setError('');

    try {
      // Set auth data for API client (only if we have initData)
      if (authData) {
        apiClient.setInitData(authData);
      }
      // Otherwise, API client will use token from localStorage

      // Fetch weekly report (distractions are included in promises as budget templates)
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

    // Set auth for API client
    if (authData) {
      apiClient.setInitData(authData);
    }
    fetchReport(authData || '');
  }, [isReady, initData, navigate, fetchReport]);

  // Fetch community users for sidebar
  useEffect(() => {
    const fetchCommunityUsers = async () => {
      setCommunityLoading(true);
      try {
        const authData = initData || getDevInitData();
        if (authData) {
          apiClient.setInitData(authData);
        }
        const response = await apiClient.getPublicUsers(8); // Top 8 users
        setCommunityUsers(response.users);
      } catch (err) {
        console.error('Failed to fetch community users:', err);
        // Don't show error, just leave empty
      } finally {
        setCommunityLoading(false);
      }
    };

    if (isReady && (initData || localStorage.getItem('telegram_auth_token'))) {
      fetchCommunityUsers();
    }
  }, [isReady, initData]);

  // Filter data into promises (recurring, non-budget), tasks (one-time, non-budget), and distractions (budget templates)
  // IMPORTANT: This hook must be called before any conditional returns
  const { promisesData, tasksData, distractionsPromisesData } = useMemo(() => {
    if (!reportData) {
      return { promisesData: null, tasksData: null, distractionsPromisesData: null };
    }

    const promises: Record<string, typeof reportData.promises[string]> = {};
    const tasks: Record<string, typeof reportData.promises[string]> = {};
    const distractions: Record<string, typeof reportData.promises[string]> = {};
    let promisesTotalPromised = 0;
    let promisesTotalSpent = 0;
    let tasksTotalPromised = 0;
    let tasksTotalSpent = 0;
    let distractionsTotalPromised = 0;
    let distractionsTotalSpent = 0;

    for (const [id, promiseData] of Object.entries(reportData.promises)) {
      // Budget templates (distractions) - separate from regular promises
      if (promiseData.template_kind === 'budget') {
        distractions[id] = promiseData;
        distractionsTotalPromised += promiseData.hours_promised || 0;
        distractionsTotalSpent += promiseData.hours_spent || 0;
      } else if (promiseData.recurring === true) {
        // Recurring promises (recurring === true, non-budget)
        promises[id] = promiseData;
        promisesTotalPromised += promiseData.hours_promised || 0;
        promisesTotalSpent += promiseData.hours_spent || 0;
      } else {
        // One-time tasks (recurring === false or undefined, non-budget)
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
      distractionsPromisesData: distractionsTotalPromised > 0 || Object.keys(distractions).length > 0 ? {
        ...reportData,
        promises: distractions,
        total_promised: distractionsTotalPromised,
        total_spent: distractionsTotalSpent,
      } : null,
    };
  }, [reportData]);

  const handleRefresh = useCallback(() => {
    const authData = initData || getDevInitData();
    fetchReport(authData || '');
  }, [initData, fetchReport]);

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

  const currentUserId = user?.id?.toString();

  return (
    <div className="app dashboard" style={{ 
      padding: '1rem', 
      maxWidth: '1400px', 
      margin: '0 auto',
      paddingBottom: '100px', // Add bottom padding for navigation bar
      display: 'flex',
      gap: '1.5rem',
      alignItems: 'flex-start'
    }}>
      {/* Main Content */}
      <div style={{ 
        flex: '1 1 0',
        minWidth: 0 // Allow flex item to shrink below content size
      }}>
        {/* Tasks Section - First */}
        {tasksData && (
          <div style={{ marginBottom: '2rem' }}>
            <h2 style={{ fontSize: '1.3rem', marginBottom: '1rem', color: '#fff' }}>One-time Tasks</h2>
            <WeeklyReport data={tasksData} onRefresh={handleRefresh} hideHeader={true} />
          </div>
        )}

        {/* Promises Section - Second */}
        {promisesData && (
          <div style={{ marginBottom: '2rem' }}>
            <h2 style={{ fontSize: '1.3rem', marginBottom: '1rem', color: '#fff' }}>Promises</h2>
            <WeeklyReport data={promisesData} onRefresh={handleRefresh} hideHeader={true} />
          </div>
        )}

        {/* Distractions Section - Third */}
        {distractionsPromisesData && (
          <div style={{ marginBottom: '2rem' }}>
            <h2 style={{ fontSize: '1.3rem', marginBottom: '1rem', color: '#fff' }}>Distractions</h2>
            <WeeklyReport data={distractionsPromisesData} onRefresh={handleRefresh} hideHeader={true} />
          </div>
        )}

        {/* Empty State */}
        {!loading && !promisesData && !tasksData && !distractionsPromisesData && (
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
              📋 Browse Promise Marketplace
            </button>
          </div>
        )}
      </div>

      {/* Right Sidebar - Community */}
      <aside style={{
        flex: '0 0 280px',
        display: 'block',
        position: 'sticky',
        top: '1rem',
        maxHeight: 'calc(100vh - 2rem)',
        overflowY: 'auto',
        overflowX: 'hidden',
        padding: '1rem',
        background: 'rgba(15, 23, 48, 0.5)',
        border: '1px solid rgba(232, 238, 252, 0.1)',
        borderRadius: '12px'
      }}
      className="community-sidebar"
      >
        <div style={{ marginBottom: '1rem' }}>
          <h3 style={{ 
            fontSize: '1.1rem', 
            fontWeight: '700', 
            color: '#fff', 
            marginBottom: '0.5rem' 
          }}>
            👥 Community
          </h3>
          <p style={{ 
            fontSize: '0.8rem', 
            color: 'rgba(232, 238, 252, 0.6)',
            marginBottom: '1rem'
          }}>
            Active users on Xaana
          </p>
        </div>

        {communityLoading ? (
          <div style={{ 
            padding: '2rem', 
            textAlign: 'center',
            color: 'rgba(232, 238, 252, 0.6)',
            fontSize: '0.9rem'
          }}>
            Loading...
          </div>
        ) : communityUsers.length > 0 ? (
          <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {communityUsers.map((communityUser) => (
                <UserCard 
                  key={communityUser.user_id} 
                  user={communityUser} 
                  currentUserId={currentUserId}
                  showFollowButton={false}
                />
              ))}
            </div>
            <button
              onClick={() => navigate('/community')}
              style={{
                width: '100%',
                marginTop: '1rem',
                padding: '0.75rem',
                background: 'rgba(91, 163, 245, 0.1)',
                border: '1px solid rgba(91, 163, 245, 0.3)',
                borderRadius: '8px',
                color: '#5ba3f5',
                fontSize: '0.9rem',
                fontWeight: '600',
                cursor: 'pointer',
                transition: 'all 0.2s'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(91, 163, 245, 0.2)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'rgba(91, 163, 245, 0.1)';
              }}
            >
              Explore Community →
            </button>
          </>
        ) : (
          <div style={{ 
            padding: '1rem', 
            textAlign: 'center',
            color: 'rgba(232, 238, 252, 0.6)',
            fontSize: '0.85rem'
          }}>
            No users found
          </div>
        )}
      </aside>
    </div>
  );
}

