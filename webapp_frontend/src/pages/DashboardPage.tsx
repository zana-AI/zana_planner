import { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { ChevronLeft, ChevronRight, Plus, Timer } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTelegramWebApp, getDevInitData } from '../hooks/useTelegramWebApp';
import { apiClient, ApiError } from '../api/client';
import { WeeklyReport } from '../components/WeeklyReport';
import { UserCard } from '../components/UserCard';
import { SuggestPromiseModal } from '../components/SuggestPromiseModal';
import { SuggestionsInbox } from '../components/SuggestionsInbox';
import { FocusBar } from '../components/FocusBar';
import { CreatePromiseModal } from '../components/CreatePromiseModal';
import { CheckinSheet } from '../components/sheets/CheckinSheet';
import { EditPromiseSheet } from '../components/sheets/EditPromiseSheet';
import { FocusPickerSheet } from '../components/sheets/FocusPickerSheet';
import { FocusSheet } from '../components/sheets/FocusSheet';
import { LogTimeSheet } from '../components/sheets/LogTimeSheet';
import { PromiseDetailSheet } from '../components/sheets/PromiseDetailSheet';
import { ScheduleSheet } from '../components/sheets/ScheduleSheet';
import { Toast } from '../components/ui/Toast';
import { useToast } from '../hooks/useToast';
import { getMockCommunityUsers, getMockWeeklyReport, shouldUseLocalMockData } from '../api/mockData';
import type { PromiseData, WeeklyReportData, PublicUser, UserInfo } from '../types';

type ActivePromise = { id: string; data: PromiseData };

function normalizeDateKey(date?: string): string {
  return (date || '').split(/[T\s]/)[0];
}

function toLocalDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function getWeekDays(weekStart: string): string[] {
  const [year, month, day] = weekStart.split('-').map(Number);
  const start = new Date(year, month - 1, day);
  const days: string[] = [];
  for (let i = 0; i < 7; i += 1) {
    const date = new Date(start);
    date.setDate(start.getDate() + i);
    days.push(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`);
  }
  return days;
}

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
  // Single source of truth: derive ref_time from URL
  const currentRefTime = searchParams.get('ref_time') || undefined;
  const [showSuggestModal, setShowSuggestModal] = useState(false);
  const [suggestToUserId, setSuggestToUserId] = useState<string>('');
  const [suggestToUserName, setSuggestToUserName] = useState<string>('');
  const [showSuggestionsInbox, setShowSuggestionsInbox] = useState(false);
  const [showCreatePromiseModal, setShowCreatePromiseModal] = useState(false);
  const [detailPromise, setDetailPromise] = useState<ActivePromise | null>(null);
  const [editPromise, setEditPromise] = useState<ActivePromise | null>(null);
  const [logPromise, setLogPromise] = useState<ActivePromise | null>(null);
  const [checkinPromise, setCheckinPromise] = useState<ActivePromise | null>(null);
  const [schedulePromise, setSchedulePromise] = useState<ActivePromise | null>(null);
  const [focusPickOpen, setFocusPickOpen] = useState(false);
  const [focusPromise, setFocusPromise] = useState<ActivePromise | null>(null);
  const [showOlderPromises, setShowOlderPromises] = useState(false);
  const { message: toastMessage, showToast } = useToast();
  const abortRef = useRef<AbortController | null>(null);
  const allowLocalMockData = shouldUseLocalMockData();
  const isLocalMockSession = allowLocalMockData && !(initData || getDevInitData() || localStorage.getItem('telegram_auth_token'));

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

  const fetchReport = useCallback(async (
    authData: string,
    refTime?: string,
    signal?: AbortSignal
  ) => {
    setLoading(true);
    setError('');

    try {
      if (authData) {
        apiClient.setInitData(authData);
      }
      if (!authData && !localStorage.getItem('telegram_auth_token') && allowLocalMockData) {
        setReportData(getMockWeeklyReport(refTime));
        return;
      }
      const data = await apiClient.getWeeklyReport(refTime, signal);
      if (signal?.aborted) return;
      setReportData(data);
      hapticFeedback('success');
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      console.error('Failed to fetch report:', err);

      if (err instanceof ApiError) {
        if (err.status === 401) {
          apiClient.clearAuth();
          window.dispatchEvent(new Event('logout'));
          if (allowLocalMockData) {
            setReportData(getMockWeeklyReport(refTime));
          } else {
            setError('Authentication failed. Please log in again.');
            navigate('/', { replace: true });
          }
        } else {
          if (allowLocalMockData) {
            setReportData(getMockWeeklyReport(refTime));
          } else {
            setError(err.message);
          }
        }
      } else {
        if (allowLocalMockData) {
          setReportData(getMockWeeklyReport(refTime));
        } else {
          setError('Failed to load your dashboard. Please try again.');
        }
      }
      hapticFeedback('error');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [allowLocalMockData, hapticFeedback, navigate]);

  useEffect(() => {
    if (!isReady) return;

    const authData = initData || getDevInitData();
    const token = localStorage.getItem('telegram_auth_token');

    if (!authData && !token && !allowLocalMockData) {
      navigate('/', { replace: true });
      return;
    }

    if (authData) {
      apiClient.setInitData(authData);
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    fetchReport(authData || '', currentRefTime, controller.signal);

    return () => {
      controller.abort();
    };
  }, [allowLocalMockData, isReady, initData, navigate, fetchReport, currentRefTime]);

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
        if (!authData && !localStorage.getItem('telegram_auth_token') && allowLocalMockData) {
          setCommunityUsers(getMockCommunityUsers());
          return;
        }
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
        if (allowLocalMockData) {
          setCommunityUsers(getMockCommunityUsers());
        }
      } finally {
        setCommunityLoading(false);
      }
    };

    if (isReady && (initData || localStorage.getItem('telegram_auth_token') || allowLocalMockData)) {
      fetchCommunityUsers();
    }
  }, [allowLocalMockData, isReady, initData, user, userInfo]);

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

  useEffect(() => {
    setShowOlderPromises(false);
  }, [reportData?.week_start]);

  // Filter data into promises (recurring, non-budget), tasks (one-time, non-budget), and distractions (budget templates)
  // IMPORTANT: This hook must be called before any conditional returns
  const { promisesData, olderPromisesData, tasksData, distractionsPromisesData, currentReportData } = useMemo(() => {
    if (!reportData) {
      return { promisesData: null, olderPromisesData: null, tasksData: null, distractionsPromisesData: null, currentReportData: null };
    }

    const promises: Record<string, typeof reportData.promises[string]> = {};
    const olderPromises: Record<string, typeof reportData.promises[string]> = {};
    const tasks: Record<string, typeof reportData.promises[string]> = {};
    const distractions: Record<string, typeof reportData.promises[string]> = {};
    const currentPromises: Record<string, typeof reportData.promises[string]> = {};
    let promisesTotalPromised = 0;
    let promisesTotalSpent = 0;
    let olderPromisesTotalPromised = 0;
    let olderPromisesTotalSpent = 0;
    let tasksTotalPromised = 0;
    let tasksTotalSpent = 0;
    let distractionsTotalPromised = 0;
    let distractionsTotalSpent = 0;
    let currentTotalPromised = 0;
    let currentTotalSpent = 0;

    const todayKey = toLocalDateKey(new Date());
    const olderCutoff = isCurrentWeek ? todayKey : reportData.week_start;

    const addToCurrentReport = (id: string, promiseData: typeof reportData.promises[string]) => {
      currentPromises[id] = promiseData;
      currentTotalPromised += promiseData.hours_promised || 0;
      currentTotalSpent += promiseData.hours_spent || 0;
    };

    for (const [id, promiseData] of Object.entries(reportData.promises)) {
      const endDate = normalizeDateKey(promiseData.end_date);
      const isOlderPromise = !!endDate && endDate < olderCutoff;

      if (isOlderPromise && promiseData.template_kind !== 'budget') {
        olderPromises[id] = promiseData;
        olderPromisesTotalPromised += promiseData.hours_promised || 0;
        olderPromisesTotalSpent += promiseData.hours_spent || 0;
        continue;
      }

      // Budget templates (distractions) - separate from regular promises
      if (promiseData.template_kind === 'budget') {
        distractions[id] = promiseData;
        distractionsTotalPromised += promiseData.hours_promised || 0;
        distractionsTotalSpent += promiseData.hours_spent || 0;
        addToCurrentReport(id, promiseData);
      } else if (promiseData.recurring === true) {
        // Recurring promises (recurring === true, non-budget)
        promises[id] = promiseData;
        promisesTotalPromised += promiseData.hours_promised || 0;
        promisesTotalSpent += promiseData.hours_spent || 0;
        addToCurrentReport(id, promiseData);
      } else {
        // One-time tasks (recurring === false or undefined, non-budget)
        tasks[id] = promiseData;
        tasksTotalPromised += promiseData.hours_promised || 0;
        tasksTotalSpent += promiseData.hours_spent || 0;
        addToCurrentReport(id, promiseData);
      }
    }

    return {
      promisesData: promisesTotalPromised > 0 || Object.keys(promises).length > 0 ? {
        ...reportData,
        promises,
        total_promised: promisesTotalPromised,
        total_spent: promisesTotalSpent,
      } : null,
      olderPromisesData: olderPromisesTotalPromised > 0 || Object.keys(olderPromises).length > 0 ? {
        ...reportData,
        promises: olderPromises,
        total_promised: olderPromisesTotalPromised,
        total_spent: olderPromisesTotalSpent,
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
      currentReportData: currentTotalPromised > 0 || Object.keys(currentPromises).length > 0 ? {
        ...reportData,
        promises: currentPromises,
        total_promised: currentTotalPromised,
        total_spent: currentTotalSpent,
      } : null,
    };
  }, [isCurrentWeek, reportData]);

  const handleRefresh = useCallback(() => {
    const authData = initData || getDevInitData();
    fetchReport(authData || '', currentRefTime);
  }, [initData, fetchReport, currentRefTime]);

  const emptyPromisesData = useMemo(() => {
    if (!reportData) return null;
    return {
      ...reportData,
      promises: {},
      total_promised: 0,
      total_spent: 0,
    };
  }, [reportData]);

  const overallProgress = useMemo(() => {
    if (!currentReportData) {
      return { cappedTotal: 0, cappedPct: 0, spentPct: 0 };
    }

    const cappedTotal = Object.values(currentReportData.promises).reduce((sum, promiseData) => {
      const achieved = promiseData.achieved_value ?? promiseData.hours_spent;
      const target = promiseData.target_value ?? promiseData.hours_promised;
      return sum + Math.min(Math.max(achieved, 0), Math.max(target, 0));
    }, 0);

    const totalPromised = currentReportData.total_promised;
    return {
      cappedTotal,
      cappedPct: totalPromised > 0 ? Math.min((cappedTotal / totalPromised) * 100, 100) : 0,
      spentPct: totalPromised > 0 ? Math.min((currentReportData.total_spent / totalPromised) * 100, 100) : 0,
    };
  }, [currentReportData]);

  const handlePreviousWeek = useCallback(() => {
    if (!reportData) return;
    const currentStart = new Date(reportData.week_start);
    const previousMonday = new Date(currentStart);
    previousMonday.setDate(previousMonday.getDate() - 7);
    const newParams = new URLSearchParams(searchParams);
    newParams.set('ref_time', previousMonday.toISOString());
    setSearchParams(newParams, { replace: true });
  }, [reportData, searchParams, setSearchParams]);

  const handleNextWeek = useCallback(() => {
    if (!reportData || isCurrentWeek) return;
    const currentStart = new Date(reportData.week_start);
    const nextMonday = new Date(currentStart);
    nextMonday.setDate(nextMonday.getDate() + 7);
    const currentWeekMonday = new Date(getCurrentWeekMonday());
    const newParams = new URLSearchParams(searchParams);
    if (nextMonday >= currentWeekMonday) {
      newParams.delete('ref_time');
    } else {
      newParams.set('ref_time', nextMonday.toISOString());
    }
    setSearchParams(newParams, { replace: true });
  }, [reportData, isCurrentWeek, searchParams, setSearchParams, getCurrentWeekMonday]);

  const weekDays = useMemo(() => (reportData ? getWeekDays(reportData.week_start) : []), [reportData]);

  const promiseCount = promisesData ? Object.keys(promisesData.promises).length : 0;
  const olderPromiseCount = olderPromisesData ? Object.keys(olderPromisesData.promises).length : 0;
  const taskCount = tasksData ? Object.keys(tasksData.promises).length : 0;
  const distractionCount = distractionsPromisesData
    ? Object.keys(distractionsPromisesData.promises).length
    : 0;

  const focusCandidates = useMemo(() => {
    if (!currentReportData) return [] as ActivePromise[];
    return Object.entries(currentReportData.promises)
      .filter(([, data]) => data.metric_type !== 'count' && (data.hours_promised || 0) > 0)
      .map(([id, data]) => ({ id, data }));
  }, [currentReportData]);

  const handleOpenDetail = useCallback((id: string, data: PromiseData) => {
    setDetailPromise({ id, data });
  }, []);

  // Deep link from Telegram DM: /dashboard?promise=<id> opens the promise detail sheet.
  const openPromiseId = searchParams.get('promise');
  useEffect(() => {
    if (!openPromiseId || !reportData) return;
    const promiseData =
      reportData.promises[openPromiseId]
      ?? olderPromisesData?.promises[openPromiseId];
    if (!promiseData) return;
    setDetailPromise({ id: openPromiseId, data: promiseData });
    const next = new URLSearchParams(searchParams);
    next.delete('promise');
    setSearchParams(next, { replace: true });
  }, [openPromiseId, reportData, olderPromisesData, searchParams, setSearchParams]);

  // Keep the open detail sheet in sync with refreshed report data, so logging
  // a session updates its badge/grids live instead of showing a stale snapshot.
  useEffect(() => {
    setDetailPromise((current) => {
      if (!current || !reportData) return current;
      const fresh = reportData.promises[current.id];
      if (!fresh || fresh === current.data) return current;
      return { id: current.id, data: fresh };
    });
  }, [reportData]);

  const handleSheetSuccess = useCallback((message: string) => {
    showToast(message);
    handleRefresh();
  }, [handleRefresh, showToast]);

  const handleEditSuccess = useCallback((result: { updates?: Partial<PromiseData>; deleted?: boolean; message: string }) => {
    showToast(result.message);

    if (!isLocalMockSession) {
      handleRefresh();
      return;
    }

    setReportData((current) => {
      if (!current || !editPromise) return current;
      const promises = { ...current.promises };
      if (result.deleted) {
        delete promises[editPromise.id];
      } else if (result.updates) {
        promises[editPromise.id] = {
          ...promises[editPromise.id],
          ...result.updates,
        };
      }

      const totals = Object.values(promises).reduce(
        (acc, promiseData) => ({
          total_promised: acc.total_promised + (promiseData.target_value ?? promiseData.hours_promised ?? 0),
          total_spent: acc.total_spent + (promiseData.achieved_value ?? promiseData.hours_spent ?? 0),
        }),
        { total_promised: 0, total_spent: 0 },
      );

      return {
        ...current,
        ...totals,
        promises,
      };
    });
  }, [editPromise, handleRefresh, isLocalMockSession, showToast]);

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
          <div className="error-icon">!</div>
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
  const isAuthenticated = !!(initData || getDevInitData() || localStorage.getItem('telegram_auth_token') || allowLocalMockData);
  const shouldShowOlderPromises = !!olderPromisesData && (showOlderPromises || promiseCount === 0);

  return (
    <div className="dashboard app">
      <main className="app-shell-main-v2 dashboard-main">
        <div className="week-strip">
          <button
            type="button"
            onClick={handlePreviousWeek}
            disabled={loading}
            aria-label="Previous week"
          >
            <ChevronLeft size={16} aria-hidden />
          </button>
          <div className="range">{weekRangeDisplay || 'Loading...'}</div>
          <button
            type="button"
            onClick={handleNextWeek}
            disabled={loading || isCurrentWeek}
            aria-label="Next week"
          >
            <ChevronRight size={16} aria-hidden />
          </button>
        </div>

        {currentReportData && currentReportData.total_promised > 0 && (
          <div className="overall">
            <div className="row">
              <span className="label">Overall progress</span>
              <span className="sub">
                {overallProgress.cappedTotal.toFixed(1)}h / {currentReportData.total_promised.toFixed(1)}h
              </span>
            </div>
            <div className="row overall-actions">
              <span className="value">{Math.round(overallProgress.cappedPct)}%</span>
              {focusCandidates.length > 0 ? (
                <button
                  type="button"
                  className="btn btn-sm btn-secondary"
                  onClick={() => setFocusPickOpen(true)}
                >
                  <Timer size={14} aria-hidden />
                  Start focus
                </button>
              ) : null}
            </div>
            <div className="track" aria-hidden="true">
              <div className="fill" style={{ width: `${overallProgress.cappedPct}%` }} />
            </div>
          </div>
        )}

        {(promisesData || (isCurrentWeek && emptyPromisesData && olderPromiseCount === 0)) && (
          <>
            <div className="section-head">
              <h2>Promises</h2>
              <span className="meta">
                {promiseCount > 0 ? `${promiseCount} active` : 'None yet'}
              </span>
            </div>
            <WeeklyReport
              data={promisesData || emptyPromisesData!}
              onRefresh={handleRefresh}
              hideHeader
              hideProgress
              useV2Cards
              onOpenDetail={handleOpenDetail}
            />
            {olderPromiseCount > 0 ? (
              <button
                type="button"
                className={`older-promises-toggle${showOlderPromises ? ' is-open' : ''}`}
                onClick={() => setShowOlderPromises((value) => !value)}
              >
                <span>{showOlderPromises ? 'Hide older promises' : `Show ${olderPromiseCount} older ${olderPromiseCount === 1 ? 'promise' : 'promises'}`}</span>
              </button>
            ) : null}
          </>
        )}

        {shouldShowOlderPromises && olderPromisesData ? (
          <>
            <div className="section-head section-head--older">
              <h2>Older promises</h2>
              <span className="meta">{olderPromiseCount} ended</span>
            </div>
            <WeeklyReport
              data={olderPromisesData}
              onRefresh={handleRefresh}
              hideHeader
              hideProgress
              useV2Cards
              onOpenDetail={handleOpenDetail}
            />
          </>
        ) : null}

        {tasksData && (
          <>
            <div className="section-head">
              <h2>One-time tasks</h2>
              <span className="meta">{taskCount} this week</span>
            </div>
            <WeeklyReport
              data={tasksData}
              onRefresh={handleRefresh}
              hideHeader
              hideProgress
              useV2Cards
              onOpenDetail={handleOpenDetail}
            />
          </>
        )}

        {distractionsPromisesData && (
          <>
            <div className="section-head">
              <h2>Distractions</h2>
              <span className="meta">Stay under budget</span>
            </div>
            <WeeklyReport
              data={distractionsPromisesData}
              onRefresh={handleRefresh}
              hideHeader
              hideProgress
              useV2Cards
              onOpenDetail={handleOpenDetail}
            />
          </>
        )}

        {!loading && !isCurrentWeek && !promisesData && !olderPromisesData && !tasksData && !distractionsPromisesData && (
          <div className="empty-state">
            <h2 className="empty-title">No promises or tasks yet</h2>
            <p className="empty-subtitle">
              Start tracking your promises in the Telegram bot to see your progress here.
            </p>
            <button type="button" className="btn btn-primary" onClick={() => navigate('/templates')}>
              Explore Promise Library
            </button>
          </div>
        )}
      </main>

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
            Community
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
                    View Suggestions
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
                    Explore Community
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

      {showCreatePromiseModal && (
        <CreatePromiseModal
          onClose={() => setShowCreatePromiseModal(false)}
          onSuccess={() => {
            hapticFeedback('success');
            handleRefresh();
          }}
        />
      )}

      {isCurrentWeek ? (
        <button type="button" className="fab" aria-label="Create promise" onClick={() => setShowCreatePromiseModal(true)}>
          <Plus size={22} />
        </button>
      ) : null}

      {detailPromise ? (
        <PromiseDetailSheet
          open
          promiseId={detailPromise.id}
          data={detailPromise.data}
          weekDays={weekDays}
          onClose={() => setDetailPromise(null)}
          onLogTime={() => {
            setLogPromise(detailPromise);
            setDetailPromise(null);
          }}
          onCheckin={() => {
            setCheckinPromise(detailPromise);
            setDetailPromise(null);
          }}
          onSchedule={() => {
            setSchedulePromise(detailPromise);
            setDetailPromise(null);
          }}
          onFocus={() => {
            setFocusPromise(detailPromise);
            setDetailPromise(null);
          }}
          onEdit={() => {
            setEditPromise(detailPromise);
            setDetailPromise(null);
          }}
          onLogged={handleRefresh}
        />
      ) : null}

      {editPromise ? (
        <EditPromiseSheet
          open
          promiseId={editPromise.id}
          data={editPromise.data}
          mockMode={isLocalMockSession}
          onClose={() => setEditPromise(null)}
          onSaved={handleEditSuccess}
        />
      ) : null}

      <LogTimeSheet
        open={!!logPromise}
        promiseId={logPromise?.id ?? ''}
        promiseText={logPromise?.data.text ?? ''}
        onClose={() => setLogPromise(null)}
        onSuccess={handleSheetSuccess}
      />

      <CheckinSheet
        open={!!checkinPromise}
        promiseId={checkinPromise?.id ?? ''}
        promiseText={checkinPromise?.data.text ?? ''}
        onClose={() => setCheckinPromise(null)}
        onSuccess={handleSheetSuccess}
      />

      <ScheduleSheet
        open={!!schedulePromise}
        promiseId={schedulePromise?.id ?? ''}
        promiseText={schedulePromise?.data.text ?? ''}
        weekDays={weekDays}
        onClose={() => setSchedulePromise(null)}
        onSuccess={handleSheetSuccess}
      />

      <FocusPickerSheet
        open={focusPickOpen}
        promises={focusCandidates}
        onClose={() => setFocusPickOpen(false)}
        onStart={(id, text) => {
          setFocusPickOpen(false);
          setFocusPromise({ id, data: { text } as PromiseData });
        }}
      />

      <FocusSheet
        open={!!focusPromise}
        promiseId={focusPromise?.id ?? ''}
        promiseText={focusPromise?.data.text ?? ''}
        onClose={() => setFocusPromise(null)}
        onComplete={handleSheetSuccess}
      />

      <Toast message={toastMessage} />

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
