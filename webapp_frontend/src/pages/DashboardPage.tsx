import { useEffect, useState, useMemo, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTelegramWebApp, getDevInitData } from '../hooks/useTelegramWebApp';
import { apiClient, ApiError } from '../api/client';
import { WeeklyReport } from '../components/WeeklyReport';
import { UserCard } from '../components/UserCard';
import { SuggestPromiseModal } from '../components/SuggestPromiseModal';
import { SuggestionsInbox } from '../components/SuggestionsInbox';
import { FocusBar } from '../components/FocusBar';
import type { WeeklyReportData, PublicUser, UserInfo } from '../types';

export function DashboardPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user, initData, isReady, hapticFeedback } = useTelegramWebApp();
  const [reportData, setReportData] = useState<WeeklyReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [communityUsers, setCommunityUsers] = useState<PublicUser[]>([]);
  const [communityLoading, setCommunityLoading] = useState(false);
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [currentRefTime, setCurrentRefTime] = useState<string | undefined>(() => {
    // Get ref_time from URL params if present
    return searchParams.get('ref_time') || undefined;
  });
  const [showSuggestModal, setShowSuggestModal] = useState(false);
  const [suggestToUserId, setSuggestToUserId] = useState<string>('');
  const [suggestToUserName, setSuggestToUserName] = useState<string>('');
  const [showSuggestionsInbox, setShowSuggestionsInbox] = useState(false);

  // Get current week's Monday for comparison
  const getCurrentWeekMonday = useCallback(() => {
    const today = new Date();
    const day = today.getDay();
    const diff = today.getDate() - day + (day === 0 ? -6 : 1); // Adjust when day is Sunday
    const monday = new Date(today.setDate(diff));
    monday.setHours(0, 0, 0, 0);
    return monday.toISOString().split('T')[0] + 'T00:00:00';
  }, []);

  // Check if current week is the selected week
  const isCurrentWeek = useMemo(() => {
    if (!currentRefTime) return true;
    const currentWeekMonday = getCurrentWeekMonday();
    // Compare just the date part (YYYY-MM-DD)
    return currentRefTime.split('T')[0] === currentWeekMonday.split('T')[0];
  }, [currentRefTime, getCurrentWeekMonday]);

  // Format week range for display
  const weekRangeDisplay = useMemo(() => {
    if (!reportData) return '';
    const start = new Date(reportData.week_start);
    const end = new Date(reportData.week_end);
    const startStr = start.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    const endStr = end.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    return `${startStr} - ${endStr}`;
  }, [reportData]);

  const fetchReport = useCallback(async (authData: string, refTime?: string) => {
    setLoading(true);
    setError('');

    try {
      // Set auth data for API client (only if we have initData)
      if (authData) {
        apiClient.setInitData(authData);
      }
      // Otherwise, API client will use token from localStorage

      // Fetch weekly report with optional ref_time
      const data = await apiClient.getWeeklyReport(refTime);
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

  // Handle URL params on mount and when they change
  useEffect(() => {
    const refTimeParam = searchParams.get('ref_time');
    if (refTimeParam !== currentRefTime) {
      setCurrentRefTime(refTimeParam || undefined);
    }
  }, [searchParams, currentRefTime]);

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
    fetchReport(authData || '', currentRefTime);
  }, [isReady, initData, navigate, fetchReport, currentRefTime]);

  // Fetch userInfo for browser login users
  useEffect(() => {
    const hasToken = !!localStorage.getItem('telegram_auth_token');
    if (hasToken && !initData) {
      // Browser login - fetch user info to get user_id
      apiClient.getUserInfo()
        .then(setUserInfo)
        .catch(() => {
          console.error('Failed to fetch user info');
        });
    }
  }, [initData]);

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
        // Filter out current user from the list
        // Use user?.id for Telegram Mini App, or userInfo?.user_id for browser login
        const currentUserId = user?.id?.toString() || userInfo?.user_id?.toString();
        const filteredUsers = response.users.filter(
          u => u.user_id !== currentUserId
        );
        setCommunityUsers(filteredUsers);
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
  }, [isReady, initData, user, userInfo]);

  // Expose suggest promise handler globally for UserCard
  useEffect(() => {
    (window as any).onSuggestPromise = (userId: string, userName: string) => {
      setSuggestToUserId(userId);
      setSuggestToUserName(userName);
      setShowSuggestModal(true);
    };
    return () => {
      delete (window as any).onSuggestPromise;
    };
  }, []);

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
    fetchReport(authData || '', currentRefTime);
  }, [initData, fetchReport, currentRefTime]);

  const handlePreviousWeek = useCallback(() => {
    if (!reportData) return;
    
    const currentStart = new Date(reportData.week_start);
    const previousMonday = new Date(currentStart);
    previousMonday.setDate(previousMonday.getDate() - 7);
    
    const refTime = previousMonday.toISOString();
    setCurrentRefTime(refTime);
    
    // Update URL
    const newParams = new URLSearchParams(searchParams);
    newParams.set('ref_time', refTime);
    setSearchParams(newParams, { replace: true });
    
    // Fetch new report
    const authData = initData || getDevInitData();
    fetchReport(authData || '', refTime);
  }, [reportData, initData, fetchReport, searchParams, setSearchParams]);

  const handleNextWeek = useCallback(() => {
    if (!reportData || isCurrentWeek) return;
    
    const currentStart = new Date(reportData.week_start);
    const nextMonday = new Date(currentStart);
    nextMonday.setDate(nextMonday.getDate() + 7);
    
    // Check if next week would be current week
    const currentWeekMonday = new Date(getCurrentWeekMonday());
    if (nextMonday >= currentWeekMonday) {
      // Go to current week
      setCurrentRefTime(undefined);
      const newParams = new URLSearchParams(searchParams);
      newParams.delete('ref_time');
      setSearchParams(newParams, { replace: true });
      const authData = initData || getDevInitData();
      fetchReport(authData || '');
    } else {
      const refTime = nextMonday.toISOString();
      setCurrentRefTime(refTime);
      const newParams = new URLSearchParams(searchParams);
      newParams.set('ref_time', refTime);
      setSearchParams(newParams, { replace: true });
      const authData = initData || getDevInitData();
      fetchReport(authData || '', refTime);
    }
  }, [reportData, isCurrentWeek, initData, fetchReport, searchParams, setSearchParams, getCurrentWeekMonday]);

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
  
  // Determine if user is authenticated
  const isAuthenticated = !!(initData || getDevInitData() || localStorage.getItem('telegram_auth_token'));

  return (
    <div className="app dashboard" style={{ 
      padding: '1rem', 
      paddingBottom: '180px', // Add bottom padding for navigation bar + FocusBar
      maxWidth: '1400px', 
      margin: '0 auto',
      display: 'flex',
      gap: '1.5rem',
      alignItems: 'flex-start'
    }}>
      {/* Main Content */}
      <div style={{ 
        flex: '1 1 0',
        minWidth: 0 // Allow flex item to shrink below content size
      }}>
        {/* Week Navigation Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '1.5rem',
          padding: '12px 16px',
          background: 'rgba(15, 23, 48, 0.5)',
          border: '1px solid rgba(232, 238, 252, 0.1)',
          borderRadius: '12px'
        }}>
          <button
            onClick={handlePreviousWeek}
            disabled={loading}
            style={{
              padding: '8px 16px',
              background: 'rgba(232, 238, 252, 0.1)',
              border: '1px solid rgba(232, 238, 252, 0.2)',
              borderRadius: '8px',
              color: 'rgba(232, 238, 252, 0.9)',
              fontSize: '0.9rem',
              fontWeight: '600',
              cursor: loading ? 'not-allowed' : 'pointer',
              transition: 'all 0.2s',
              opacity: loading ? 0.6 : 1,
              display: 'flex',
              alignItems: 'center',
              gap: '4px'
            }}
            onMouseEnter={(e) => {
              if (!loading) {
                e.currentTarget.style.background = 'rgba(232, 238, 252, 0.2)';
              }
            }}
            onMouseLeave={(e) => {
              if (!loading) {
                e.currentTarget.style.background = 'rgba(232, 238, 252, 0.1)';
              }
            }}
          >
            ← Previous
          </button>
          
          <div style={{
            fontSize: '1rem',
            fontWeight: '700',
            color: '#fff',
            textAlign: 'center'
          }}>
            {weekRangeDisplay || 'Loading...'}
          </div>
          
          <button
            onClick={handleNextWeek}
            disabled={loading || isCurrentWeek}
            style={{
              padding: '8px 16px',
              background: isCurrentWeek ? 'rgba(232, 238, 252, 0.05)' : 'rgba(232, 238, 252, 0.1)',
              border: '1px solid rgba(232, 238, 252, 0.2)',
              borderRadius: '8px',
              color: isCurrentWeek ? 'rgba(232, 238, 252, 0.4)' : 'rgba(232, 238, 252, 0.9)',
              fontSize: '0.9rem',
              fontWeight: '600',
              cursor: (loading || isCurrentWeek) ? 'not-allowed' : 'pointer',
              transition: 'all 0.2s',
              opacity: (loading || isCurrentWeek) ? 0.6 : 1,
              display: 'flex',
              alignItems: 'center',
              gap: '4px'
            }}
            onMouseEnter={(e) => {
              if (!loading && !isCurrentWeek) {
                e.currentTarget.style.background = 'rgba(232, 238, 252, 0.2)';
              }
            }}
            onMouseLeave={(e) => {
              if (!loading && !isCurrentWeek) {
                e.currentTarget.style.background = 'rgba(232, 238, 252, 0.1)';
              }
            }}
          >
            Next →
          </button>
        </div>
        
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
            {!showSuggestionsInbox ? (
              <>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {communityUsers.map((communityUser) => (
                    <UserCard 
                      key={communityUser.user_id} 
                      user={communityUser} 
                      currentUserId={currentUserId}
                      showFollowButton={true}
                    />
                  ))}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: '1rem' }}>
                  <button
                    onClick={() => setShowSuggestionsInbox(true)}
                    style={{
                      width: '100%',
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
                    📬 View Suggestions
                  </button>
                  <button
                    onClick={() => navigate('/community')}
                    style={{
                      width: '100%',
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
                </div>
              </>
            ) : (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                  <h4 style={{ color: '#fff', margin: 0 }}>Promise Suggestions</h4>
                  <button
                    className="button-secondary"
                    onClick={() => setShowSuggestionsInbox(false)}
                    style={{ fontSize: '0.85rem', padding: '0.4rem 0.8rem' }}
                  >
                    Back
                  </button>
                </div>
                <SuggestionsInbox />
              </div>
            )}
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

      {showSuggestModal && (
        <SuggestPromiseModal
          toUserId={suggestToUserId}
          toUserName={suggestToUserName}
          onClose={() => {
            setShowSuggestModal(false);
            setSuggestToUserId('');
            setSuggestToUserName('');
          }}
          onSuccess={() => {
            hapticFeedback('success');
          }}
        />
      )}

      {/* Focus Bar - Global Pomodoro Timer */}
      {isAuthenticated && (
        <FocusBar
          promisesData={promisesData}
          onSessionComplete={() => {
            // Refresh data when session completes, but don't force immediate refresh
            // The backend sweeper will send Telegram notification
            // Only refresh if user is still on the page after a delay
            setTimeout(() => {
              handleRefresh();
            }, 500);
          }}
        />
      )}
    </div>
  );
}

