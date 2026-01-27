import { useState, useEffect } from 'react';
import { apiClient, ApiError } from '../api/client';
import { useTelegramWebApp, getDevInitData } from '../hooks/useTelegramWebApp';
import { UserAvatar } from './UserAvatar';
import type { AdminUser, Broadcast, PromiseTemplate, UserInfo } from '../types';
import {
  AdminHeader,
  AdminTabs,
  type TabType,
  StatsTab,
  BroadcastTab,
  ScheduledTab,
  TemplatesTab,
  PromoteTab,
  DevToolsTab,
  CreatePromiseTab,
  ConversationsTab,
  TestsTab,
} from './admin';

export function AdminPanel() {
  const { initData, user: telegramUser } = useTelegramWebApp();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [broadcasts, setBroadcasts] = useState<Broadcast[]>([]);
  const [loadingBroadcasts, setLoadingBroadcasts] = useState(false);
  const [activeTab, setActiveTab] = useState<TabType>('stats');
  const [stats, setStats] = useState<{ total_users: number; active_users: number; total_promises: number } | null>(null);
  const [loadingStats, setLoadingStats] = useState(false);
  const [statsError, setStatsError] = useState<string>('');
  const [templates, setTemplates] = useState<PromiseTemplate[]>([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<PromiseTemplate | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(null);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');
  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [botUsername, setBotUsername] = useState<string | null>(null);

  // Check for authentication (initData or browser token)
  const authData = initData || getDevInitData();
  const hasToken = !!localStorage.getItem('telegram_auth_token');
  const isAuthenticated = !!authData || hasToken;

  // Set initData for API client
  useEffect(() => {
    if (initData) {
      apiClient.setInitData(initData);
    }
  }, [initData]);

  // Fetch user info for browser login users
  useEffect(() => {
    if (hasToken && !authData) {
      apiClient.getUserInfo()
        .then(setUserInfo)
        .catch(() => {
          console.error('Failed to fetch user info');
        });
    }
  }, [hasToken, authData]);

  // Fetch bot username for Telegram links
  useEffect(() => {
    const fetchBotUsername = async () => {
      try {
        const response = await fetch('/api/auth/bot-username');
        if (response.ok) {
          const data = await response.json();
          if (data.bot_username) {
            setBotUsername(data.bot_username.trim());
          }
        }
      } catch (error) {
        console.error('Failed to fetch bot username:', error);
      }
    };
    
    if (isAuthenticated) {
      fetchBotUsername();
    }
  }, [isAuthenticated]);

  // Fetch stats when Stats tab is active
  useEffect(() => {
    if (activeTab === 'stats' && isAuthenticated) {
      const fetchStats = async () => {
        setLoadingStats(true);
        setStatsError('');
        try {
          const statsData = await apiClient.getAdminStats();
          setStats(statsData);
        } catch (err) {
          console.error('Failed to fetch stats:', err);
          if (err instanceof ApiError) {
            if (err.status === 403) {
              setStatsError('Access denied. Admin privileges required.');
            } else {
              setStatsError(err.message || 'Failed to load statistics');
            }
          } else {
            setStatsError('Failed to load statistics');
          }
          setStats(null);
        } finally {
          setLoadingStats(false);
        }
      };
      fetchStats();
    }
  }, [activeTab, isAuthenticated]);

  // Fetch users - wait for authentication to be available
  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }

    const fetchUsers = async () => {
      setLoading(true);
      setError('');
      
      try {
        const response = await apiClient.getAdminUsers(10000);
        setUsers(response.users);
      } catch (err) {
        console.error('Failed to fetch users:', err);
        
        if (err instanceof ApiError) {
          if (err.status === 403) {
            setError('Access denied. Admin privileges required.');
          } else if (err.status === 401) {
            setError('Authentication failed. Please reopen the app from Telegram.');
          } else {
            setError(err.message);
          }
        } else {
          setError('Failed to load users. Please try again.');
        }
      } finally {
        setLoading(false);
      }
    };

    fetchUsers();
  }, [isAuthenticated]);

  // Fetch broadcasts
  const fetchBroadcasts = async () => {
    if (!isAuthenticated) {
      return;
    }
    
    setLoadingBroadcasts(true);
    try {
      const broadcastsList = await apiClient.getBroadcasts('pending', 100);
      setBroadcasts(broadcastsList);
    } catch (err) {
      console.error('Failed to fetch broadcasts:', err);
    } finally {
      setLoadingBroadcasts(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'scheduled' && isAuthenticated) {
      fetchBroadcasts();
    }
  }, [activeTab, isAuthenticated]);

  // Fetch templates when Templates tab is active
  useEffect(() => {
    if (activeTab === 'templates' && isAuthenticated) {
      const fetchTemplates = async () => {
        setLoadingTemplates(true);
        try {
          const response = await apiClient.getAdminTemplates();
          setTemplates(response.templates);
        } catch (err) {
          console.error('Failed to fetch templates:', err);
          if (err instanceof ApiError && err.status === 403) {
            setError('Access denied. Admin privileges required.');
          }
        } finally {
          setLoadingTemplates(false);
        }
      };
      fetchTemplates();
    }
  }, [activeTab, isAuthenticated]);

  const handleRetryStats = () => {
    setStatsError('');
    setActiveTab('compose');
    setTimeout(() => setActiveTab('stats'), 100);
  };

  if (loading) {
    return (
      <div className="admin-panel">
        <div className="admin-panel-header" style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '1rem'
        }}>
          <h1 className="admin-panel-title" style={{ margin: 0 }}>Admin Panel</h1>
          <UserAvatar size={40} showMenu={false} />
        </div>
        <div className="admin-panel-loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading users...</div>
        </div>
      </div>
    );
  }

  if (error && error.includes('Access denied')) {
    return (
      <div className="admin-panel">
        <div className="admin-panel-header" style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '1rem'
        }}>
          <h1 className="admin-panel-title" style={{ margin: 0 }}>Admin Panel</h1>
          <UserAvatar size={40} showMenu={false} />
        </div>
        <div className="admin-panel-error">
          <div className="error-icon">🔒</div>
          <p className="error-message">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-panel">
      <AdminHeader
        telegramUser={telegramUser}
        userInfo={userInfo}
        botUsername={botUsername}
        showProfileMenu={showProfileMenu}
        setShowProfileMenu={setShowProfileMenu}
      />
      <AdminTabs
        activeTab={activeTab}
        onTabChange={setActiveTab}
        scheduledCount={broadcasts.length}
      />

      {error && !error.includes('Access denied') && (
        <div className="admin-panel-error-banner">
          <p>{error}</p>
          <button onClick={() => setError('')}>×</button>
        </div>
      )}

      {activeTab === 'stats' && (
        <StatsTab
          stats={stats}
          loadingStats={loadingStats}
          statsError={statsError}
          onRetry={handleRetryStats}
        />
      )}

      {activeTab === 'compose' && (
        <BroadcastTab
          users={users}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          setError={setError}
          onTabChange={setActiveTab}
          onRefreshBroadcasts={fetchBroadcasts}
        />
      )}

      {activeTab === 'scheduled' && (
        <ScheduledTab
          broadcasts={broadcasts}
          loadingBroadcasts={loadingBroadcasts}
          onRefresh={fetchBroadcasts}
        />
      )}

      {activeTab === 'templates' && (
        <TemplatesTab
          templates={templates}
          loadingTemplates={loadingTemplates}
          editingTemplate={editingTemplate}
          showDeleteConfirm={showDeleteConfirm}
          deleteConfirmText={deleteConfirmText}
          onSetEditingTemplate={setEditingTemplate}
          onSetShowDeleteConfirm={setShowDeleteConfirm}
          onSetDeleteConfirmText={setDeleteConfirmText}
          onSetTemplates={setTemplates}
          onError={setError}
        />
      )}

      {activeTab === 'promote' && (
        <PromoteTab onError={setError} />
      )}

      {activeTab === 'devtools' && (
        <DevToolsTab />
      )}

      {activeTab === 'createPromise' && (
        <CreatePromiseTab
          users={users}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          error={error}
          setError={setError}
        />
      )}

      {activeTab === 'conversations' && (
        <ConversationsTab
          users={users}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
        />
      )}

      {activeTab === 'tests' && (
        <TestsTab />
      )}
    </div>
  );
}
