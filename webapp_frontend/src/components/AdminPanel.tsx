import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient, ApiError } from '../api/client';
import { useTelegramWebApp, getDevInitData } from '../hooks/useTelegramWebApp';
import { UserAvatar } from './UserAvatar';
import type { AdminUser, Broadcast, CreateBroadcastRequest, PromiseTemplate, UserInfo, BotToken } from '../types';

export function AdminPanel() {
  const navigate = useNavigate();
  const { initData, user: telegramUser } = useTelegramWebApp();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [selectedUserIds, setSelectedUserIds] = useState<Set<number>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  const [message, setMessage] = useState('');
  const [scheduledTime, setScheduledTime] = useState('');
  const [broadcasts, setBroadcasts] = useState<Broadcast[]>([]);
  const [loadingBroadcasts, setLoadingBroadcasts] = useState(false);
  const [sending, setSending] = useState(false);
  const [activeTab, setActiveTab] = useState<'stats' | 'compose' | 'scheduled' | 'templates' | 'promote' | 'devtools'>('stats');
  const [promoting, setPromoting] = useState(false);
  const [promoteConfirmText, setPromoteConfirmText] = useState('');
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
  const [botTokens, setBotTokens] = useState<BotToken[]>([]);
  const [selectedBotTokenId, setSelectedBotTokenId] = useState<string>('');
  const [loadingBotTokens, setLoadingBotTokens] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

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

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowProfileMenu(false);
      }
    };

    if (showProfileMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showProfileMenu]);

  const handleLogout = () => {
    apiClient.clearAuth();
    window.dispatchEvent(new Event('logout'));
    setShowProfileMenu(false);
    navigate('/', { replace: true });
  };

  const displayName = userInfo?.first_name || telegramUser?.first_name || telegramUser?.username || userInfo?.user_id?.toString() || 'User';
  const displayInitial = (userInfo?.first_name || telegramUser?.first_name || telegramUser?.username || 'U').charAt(0).toUpperCase();

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
    // Don't fetch if not authenticated yet
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
  }, [isAuthenticated]); // Wait for authentication (initData or token)

  // Fetch broadcasts
  const fetchBroadcasts = async () => {
    // Don't fetch if not authenticated
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
  }, [activeTab, isAuthenticated]); // Also depend on isAuthenticated

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

  // Fetch bot tokens when compose tab is active
  useEffect(() => {
    if (activeTab === 'compose' && isAuthenticated) {
      const fetchBotTokens = async () => {
        setLoadingBotTokens(true);
        try {
          const tokens = await apiClient.getBotTokens(true); // Only fetch active tokens
          setBotTokens(tokens);
        } catch (err) {
          console.error('Failed to fetch bot tokens:', err);
        } finally {
          setLoadingBotTokens(false);
        }
      };
      fetchBotTokens();
    }
  }, [activeTab, isAuthenticated]);

  // Filter users based on search query
  const filteredUsers = users.filter(user => {
    const query = searchQuery.toLowerCase();
    const firstName = user.first_name?.toLowerCase() || '';
    const lastName = user.last_name?.toLowerCase() || '';
    const username = user.username?.toLowerCase() || '';
    const userId = user.user_id.toLowerCase();
    
    return firstName.includes(query) || 
           lastName.includes(query) || 
           username.includes(query) || 
           userId.includes(query);
  });

  // Toggle user selection
  const toggleUser = (userId: number) => {
    const newSelected = new Set(selectedUserIds);
    if (newSelected.has(userId)) {
      newSelected.delete(userId);
    } else {
      newSelected.add(userId);
    }
    setSelectedUserIds(newSelected);
  };

  // Select all/none
  const toggleSelectAll = () => {
    if (selectedUserIds.size === filteredUsers.length) {
      setSelectedUserIds(new Set());
    } else {
      setSelectedUserIds(new Set(filteredUsers.map(u => parseInt(u.user_id))));
    }
  };

  // Send broadcast
  const sendBroadcast = async (immediate: boolean = false) => {
    if (!message.trim()) {
      setError('Please enter a message');
      return;
    }

    if (selectedUserIds.size === 0) {
      setError('Please select at least one user');
      return;
    }

    setSending(true);
    setError('');

    try {
      const request: CreateBroadcastRequest = {
        message: message.trim(),
        target_user_ids: Array.from(selectedUserIds),
        scheduled_time_utc: immediate ? undefined : scheduledTime || undefined,
        bot_token_id: selectedBotTokenId || undefined,
      };

      await apiClient.createBroadcast(request);
      
      // Reset form
      setMessage('');
      setScheduledTime('');
      setSelectedUserIds(new Set());
      
      // Refresh broadcasts if on scheduled tab
      if (activeTab === 'scheduled') {
        await fetchBroadcasts();
      }
      
      // Switch to scheduled tab to see the new broadcast
      setActiveTab('scheduled');
    } catch (err) {
      console.error('Failed to send broadcast:', err);
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to send broadcast. Please try again.');
      }
    } finally {
      setSending(false);
    }
  };

  // Cancel broadcast
  const cancelBroadcast = async (broadcastId: string) => {
    if (!confirm('Are you sure you want to cancel this broadcast?')) {
      return;
    }

    try {
      await apiClient.cancelBroadcast(broadcastId);
      await fetchBroadcasts();
    } catch (err) {
      console.error('Failed to cancel broadcast:', err);
      if (err instanceof ApiError) {
        alert(err.message);
      } else {
        alert('Failed to cancel broadcast. Please try again.');
      }
    }
  };

  // Format datetime for input
  const getCurrentDateTime = () => {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    return now.toISOString().slice(0, 16);
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
      <div className="admin-panel-header" style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '1rem'
      }}>
        <h1 className="admin-panel-title" style={{ margin: 0 }}>Admin Panel</h1>
        <div style={{ position: 'relative' }} ref={menuRef}>
          <button
            onClick={() => setShowProfileMenu(!showProfileMenu)}
            style={{
              background: 'rgba(255, 255, 255, 0.1)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              borderRadius: '50%',
              width: '40px',
              height: '40px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fff',
              fontSize: '1rem',
              fontWeight: 'bold',
              cursor: 'pointer',
              transition: 'all 0.2s',
              padding: 0
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.2)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
            }}
          >
            {telegramUser?.photo_url ? (
              <img
                src={telegramUser.photo_url}
                alt={displayName}
                style={{
                  width: '100%',
                  height: '100%',
                  borderRadius: '50%',
                  objectFit: 'cover'
                }}
              />
            ) : (
              displayInitial
            )}
          </button>

          {/* Dropdown Menu */}
          {showProfileMenu && (
            <div style={{
              position: 'absolute',
              top: 'calc(100% + 0.5rem)',
              right: 0,
              background: 'rgba(11, 16, 32, 0.98)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              borderRadius: '8px',
              padding: '0.5rem',
              minWidth: '180px',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
              zIndex: 1000
            }}>
              <div style={{
                padding: '0.75rem 1rem',
                borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
                color: '#fff',
                fontSize: '0.9rem',
                fontWeight: '500'
              }}>
                {displayName}
              </div>
              <button
                onClick={() => {
                  navigate('/dashboard');
                  setShowProfileMenu(false);
                }}
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  background: 'none',
                  border: 'none',
                  color: '#fff',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontSize: '0.9rem',
                  borderRadius: '4px',
                  transition: 'background 0.2s'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'none';
                }}
              >
                👤 Profile / Dashboard
              </button>
              <a
                href={botUsername ? `https://t.me/${botUsername}` : 'https://t.me/zana_planner_bot'}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => setShowProfileMenu(false)}
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  background: 'none',
                  border: 'none',
                  color: '#fff',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontSize: '0.9rem',
                  borderRadius: '4px',
                  transition: 'background 0.2s',
                  textDecoration: 'none',
                  display: 'block',
                  marginTop: '0.25rem'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'none';
                }}
              >
                🤖 Open Bot
              </a>
              <button
                onClick={() => {
                  navigate('/community');
                  setShowProfileMenu(false);
                }}
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  background: 'none',
                  border: 'none',
                  color: '#fff',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontSize: '0.9rem',
                  borderRadius: '4px',
                  transition: 'background 0.2s',
                  marginTop: '0.25rem'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'none';
                }}
              >
                👥 Community
              </button>
              <button
                onClick={() => {
                  navigate('/templates');
                  setShowProfileMenu(false);
                }}
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  background: 'none',
                  border: 'none',
                  color: '#fff',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontSize: '0.9rem',
                  borderRadius: '4px',
                  transition: 'background 0.2s',
                  marginTop: '0.25rem'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'none';
                }}
              >
                📋 Promise Marketplace
              </button>
              <button
                onClick={() => {
                  navigate('/admin');
                  setShowProfileMenu(false);
                }}
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  background: 'none',
                  border: 'none',
                  color: '#5ba3f5',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontSize: '0.9rem',
                  borderRadius: '4px',
                  transition: 'background 0.2s',
                  marginTop: '0.25rem'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(91, 163, 245, 0.1)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'none';
                }}
              >
                🔐 Admin Panel
              </button>
              <div style={{
                marginTop: '0.5rem',
                paddingTop: '0.5rem',
                borderTop: '1px solid rgba(255, 255, 255, 0.1)'
              }}>
                <button
                  onClick={handleLogout}
                  style={{
                    width: '100%',
                    padding: '0.75rem 1rem',
                    background: 'none',
                    border: 'none',
                    color: '#ff6b6b',
                    textAlign: 'left',
                    cursor: 'pointer',
                    fontSize: '0.9rem',
                    borderRadius: '4px',
                    transition: 'background 0.2s'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = 'rgba(255, 107, 107, 0.1)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'none';
                  }}
                >
                  🚪 Logout
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
      <div className="admin-panel-tabs">
        <button
          className={`admin-tab ${activeTab === 'stats' ? 'active' : ''}`}
          onClick={() => setActiveTab('stats')}
        >
          Stats
        </button>
          <button
            className={`admin-tab ${activeTab === 'compose' ? 'active' : ''}`}
            onClick={() => setActiveTab('compose')}
          >
            Broadcast
          </button>
          <button
            className={`admin-tab ${activeTab === 'scheduled' ? 'active' : ''}`}
            onClick={() => setActiveTab('scheduled')}
          >
            Scheduled ({broadcasts.length})
          </button>
          <button
            className={`admin-tab ${activeTab === 'templates' ? 'active' : ''}`}
            onClick={() => setActiveTab('templates')}
          >
            Promise Marketplace
          </button>
          <button
            className={`admin-tab ${activeTab === 'promote' ? 'active' : ''}`}
            onClick={() => setActiveTab('promote')}
          >
            Promote
          </button>
          <button
            className={`admin-tab ${activeTab === 'devtools' ? 'active' : ''}`}
            onClick={() => setActiveTab('devtools')}
          >
            Dev Tools
          </button>
        </div>

      {error && !error.includes('Access denied') && (
        <div className="admin-panel-error-banner">
          <p>{error}</p>
          <button onClick={() => setError('')}>×</button>
        </div>
      )}

      {activeTab === 'stats' && (
        <div className="admin-panel-stats">
          {loadingStats ? (
            <div className="admin-loading">
              <div className="loading-spinner" />
              <div className="loading-text">Loading statistics...</div>
            </div>
          ) : stats ? (
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', 
              gap: '1.5rem',
              padding: '1.5rem 0'
            }}>
              <div style={{
                background: 'rgba(15, 23, 48, 0.6)',
                border: '1px solid rgba(232, 238, 252, 0.1)',
                borderRadius: '12px',
                padding: '1.5rem',
                textAlign: 'center'
              }}>
                <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>👥</div>
                <div style={{ fontSize: '0.9rem', color: 'rgba(232, 238, 252, 0.6)', marginBottom: '0.5rem' }}>
                  Total Users
                </div>
                <div style={{ fontSize: '2rem', fontWeight: '700', color: '#fff' }}>
                  {stats.total_users.toLocaleString()}
                </div>
              </div>
              
              <div style={{
                background: 'rgba(15, 23, 48, 0.6)',
                border: '1px solid rgba(232, 238, 252, 0.1)',
                borderRadius: '12px',
                padding: '1.5rem',
                textAlign: 'center'
              }}>
                <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>🔥</div>
                <div style={{ fontSize: '0.9rem', color: 'rgba(232, 238, 252, 0.6)', marginBottom: '0.5rem' }}>
                  Active Users (7d)
                </div>
                <div style={{ fontSize: '2rem', fontWeight: '700', color: '#fff' }}>
                  {stats.active_users.toLocaleString()}
                </div>
              </div>
              
              <div style={{
                background: 'rgba(15, 23, 48, 0.6)',
                border: '1px solid rgba(232, 238, 252, 0.1)',
                borderRadius: '12px',
                padding: '1.5rem',
                textAlign: 'center'
              }}>
                <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>🎯</div>
                <div style={{ fontSize: '0.9rem', color: 'rgba(232, 238, 252, 0.6)', marginBottom: '0.5rem' }}>
                  Users with Promises
                </div>
                <div style={{ fontSize: '2rem', fontWeight: '700', color: '#fff' }}>
                  {stats.total_promises.toLocaleString()}
                </div>
              </div>
            </div>
          ) : statsError ? (
            <div className="admin-no-stats">
              <div className="empty-icon">⚠️</div>
              <p>{statsError}</p>
              <button
                onClick={() => {
                  setStatsError('');
                  // Trigger refetch by toggling tab
                  setActiveTab('compose');
                  setTimeout(() => setActiveTab('stats'), 100);
                }}
                style={{
                  marginTop: '1rem',
                  padding: '0.5rem 1rem',
                  background: 'rgba(91, 163, 245, 0.2)',
                  border: '1px solid rgba(91, 163, 245, 0.4)',
                  borderRadius: '6px',
                  color: '#5ba3f5',
                  cursor: 'pointer',
                  fontSize: '0.9rem'
                }}
              >
                Retry
              </button>
            </div>
          ) : (
            <div className="admin-no-stats">
              <div className="empty-icon">📊</div>
              <p>No statistics available</p>
            </div>
          )}
        </div>
      )}

      {activeTab === 'compose' && (
        <div className="admin-panel-compose">
          <div className="admin-section">
            <h2 className="admin-section-title">Message</h2>
            <textarea
              className="admin-message-input"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Enter your broadcast message..."
              rows={5}
            />
          </div>

          <div className="admin-section">
            <h2 className="admin-section-title">
              Select Users ({selectedUserIds.size} selected)
            </h2>
            <div className="admin-user-controls">
              <input
                type="text"
                className="admin-search-input"
                placeholder="Search users..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              <button
                className="admin-select-all-btn"
                onClick={toggleSelectAll}
              >
                {selectedUserIds.size === filteredUsers.length ? 'Deselect All' : 'Select All'}
              </button>
            </div>
            <div className="admin-users-list">
              {filteredUsers.map((user) => {
                const userId = parseInt(user.user_id);
                const isSelected = selectedUserIds.has(userId);
                return (
                  <label key={user.user_id} className="admin-user-item">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleUser(userId)}
                    />
                    <span className="admin-user-name">
                      {user.first_name || ''} {user.last_name || ''} {user.username ? `(@${user.username})` : ''}
                    </span>
                    <span className="admin-user-id">ID: {user.user_id}</span>
                  </label>
                );
              })}
              {filteredUsers.length === 0 && (
                <div className="admin-no-users">No users found</div>
              )}
            </div>
          </div>

          <div className="admin-section">
            <h2 className="admin-section-title">Bot Token (Optional)</h2>
            {loadingBotTokens ? (
              <div className="admin-loading">
                <div className="loading-spinner" />
                <div className="loading-text">Loading bot tokens...</div>
              </div>
            ) : (
              <>
                <select
                  className="admin-select-input"
                  value={selectedBotTokenId}
                  onChange={(e) => setSelectedBotTokenId(e.target.value)}
                >
                  <option value="">Use default bot token</option>
                  {botTokens.map((token) => (
                    <option key={token.bot_token_id} value={token.bot_token_id}>
                      {token.bot_username || 'Unknown'} {token.description ? `- ${token.description}` : ''}
                    </option>
                  ))}
                </select>
                <p className="admin-hint">
                  Select a bot token to send through a different bot instance (e.g., old bot for users who only interacted with it)
                </p>
              </>
            )}
          </div>

          <div className="admin-section">
            <h2 className="admin-section-title">Schedule (Optional)</h2>
            <input
              type="datetime-local"
              className="admin-datetime-input"
              value={scheduledTime}
              onChange={(e) => setScheduledTime(e.target.value)}
              min={getCurrentDateTime()}
            />
            <p className="admin-hint">
              Leave empty to send immediately, or select a future date/time
            </p>
          </div>

          <div className="admin-actions">
            <button
              className="admin-send-btn"
              onClick={() => sendBroadcast(true)}
              disabled={sending || !message.trim() || selectedUserIds.size === 0}
            >
              {sending ? 'Sending...' : 'Send Now'}
            </button>
            <button
              className="admin-schedule-btn"
              onClick={() => sendBroadcast(false)}
              disabled={sending || !message.trim() || selectedUserIds.size === 0}
            >
              {sending ? 'Scheduling...' : scheduledTime ? 'Schedule' : 'Schedule for Later'}
            </button>
          </div>
        </div>
      )}

      {activeTab === 'scheduled' && (
        <div className="admin-panel-scheduled">
          {loadingBroadcasts ? (
            <div className="admin-loading">
              <div className="loading-spinner" />
              <div className="loading-text">Loading broadcasts...</div>
            </div>
          ) : broadcasts.length === 0 ? (
            <div className="admin-no-broadcasts">
              <div className="empty-icon">📭</div>
              <p>No scheduled broadcasts</p>
            </div>
          ) : (
            <div className="admin-broadcasts-list">
              {broadcasts.map((broadcast) => (
                <div key={broadcast.broadcast_id} className="admin-broadcast-item">
                  <div className="admin-broadcast-header">
                    <span className="admin-broadcast-status">{broadcast.status}</span>
                    <span className="admin-broadcast-time">
                      {new Date(broadcast.scheduled_time_utc).toLocaleString()}
                    </span>
                  </div>
                  <div className="admin-broadcast-message">{broadcast.message}</div>
                  <div className="admin-broadcast-meta">
                    To {broadcast.target_user_ids.length} user(s)
                  </div>
                  {broadcast.status === 'pending' && (
                    <button
                      className="admin-cancel-btn"
                      onClick={() => cancelBroadcast(broadcast.broadcast_id)}
                    >
                      Cancel
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'templates' && (
        <div className="admin-panel-templates">
          {loadingTemplates ? (
            <div className="admin-loading">
              <div className="loading-spinner" />
              <div className="loading-text">Loading templates...</div>
            </div>
          ) : (
            <>
              <div style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h2 style={{ margin: 0, color: '#fff' }}>Promise Marketplace Templates</h2>
                <button
                  onClick={() => setEditingTemplate({} as PromiseTemplate)}
                  style={{
                    padding: '0.5rem 1rem',
                    background: 'linear-gradient(135deg, #667eea, #764ba2)',
                    border: 'none',
                    borderRadius: '6px',
                    color: '#fff',
                    cursor: 'pointer',
                    fontSize: '0.9rem',
                    fontWeight: '500'
                  }}
                >
                  + Create Template
                </button>
              </div>

              {editingTemplate !== null && (
                <TemplateForm
                  template={editingTemplate}
                  onSave={async (data) => {
                    try {
                      if (editingTemplate.template_id) {
                        await apiClient.updateTemplate(editingTemplate.template_id, data);
                      } else {
                        await apiClient.createTemplate(data);
                      }
                      setEditingTemplate(null);
                      // Refresh templates
                      const response = await apiClient.getAdminTemplates();
                      setTemplates(response.templates);
                    } catch (err) {
                      console.error('Failed to save template:', err);
                      if (err instanceof ApiError) {
                        setError(err.message);
                      }
                    }
                  }}
                  onCancel={() => setEditingTemplate(null)}
                />
              )}

              {showDeleteConfirm && (
                <DeleteConfirmModal
                  templateId={showDeleteConfirm}
                  templateTitle={templates.find(t => t.template_id === showDeleteConfirm)?.title || ''}
                  onConfirm={async () => {
                    try {
                      await apiClient.deleteTemplate(showDeleteConfirm);
                      setShowDeleteConfirm(null);
                      setDeleteConfirmText('');
                      // Refresh templates
                      const response = await apiClient.getAdminTemplates();
                      setTemplates(response.templates);
                    } catch (err) {
                      console.error('Failed to delete template:', err);
                      if (err instanceof ApiError) {
                        if (err.status === 409) {
                          // Try to parse error message for structured error details
                          try {
                            const errorData = JSON.parse(err.message);
                            if (errorData.message || errorData.reasons) {
                              setError(errorData.message || 'Template cannot be deleted: ' + (Array.isArray(errorData.reasons) ? errorData.reasons.join(', ') : 'Template is in use'));
                            } else {
                              setError(err.message);
                            }
                          } catch {
                            // If parsing fails, use the message as-is
                            setError(err.message || 'Template cannot be deleted because it is in use');
                          }
                        } else {
                          setError(err.message);
                        }
                      } else {
                        setError('Failed to delete template');
                      }
                      setShowDeleteConfirm(null);
                      setDeleteConfirmText('');
                    }
                  }}
                  onCancel={() => {
                    setShowDeleteConfirm(null);
                    setDeleteConfirmText('');
                  }}
                  confirmText={deleteConfirmText}
                  onConfirmTextChange={setDeleteConfirmText}
                />
              )}

              <div style={{ display: 'grid', gap: '1rem' }}>
                {templates.map((template) => (
                  <div
                    key={template.template_id}
                    style={{
                      background: 'rgba(15, 23, 48, 0.6)',
                      border: '1px solid rgba(232, 238, 252, 0.1)',
                      borderRadius: '8px',
                      padding: '1rem',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flex: 1 }}>
                      <span style={{ fontSize: '1.5rem' }}>{template.emoji || '🎯'}</span>
                      <div>
                        <div style={{ fontSize: '1.05rem', fontWeight: '600', color: '#fff', marginBottom: '0.15rem' }}>
                          {template.title}
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'rgba(232, 238, 252, 0.5)' }}>
                          {template.target_value} {template.metric_type === 'hours' ? 'hrs' : '×'}/week • {template.category} • {template.is_active ? '✓ Active' : '○ Inactive'}
                        </div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <button
                        onClick={() => setEditingTemplate(template)}
                        style={{
                          padding: '0.5rem 1rem',
                          background: 'rgba(91, 163, 245, 0.2)',
                          border: '1px solid rgba(91, 163, 245, 0.4)',
                          borderRadius: '6px',
                          color: '#5ba3f5',
                          cursor: 'pointer',
                          fontSize: '0.85rem'
                        }}
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => setShowDeleteConfirm(template.template_id)}
                        style={{
                          padding: '0.5rem 1rem',
                          background: 'rgba(255, 107, 107, 0.2)',
                          border: '1px solid rgba(255, 107, 107, 0.4)',
                          borderRadius: '6px',
                          color: '#ff6b6b',
                          cursor: 'pointer',
                          fontSize: '0.85rem'
                        }}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
                {templates.length === 0 && (
                  <div style={{ textAlign: 'center', padding: '2rem', color: 'rgba(232, 238, 252, 0.6)' }}>
                    No templates found
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {activeTab === 'promote' && (
        <div className="admin-panel-promote">
          <div style={{
            background: 'rgba(15, 23, 48, 0.8)',
            border: '1px solid rgba(255, 193, 7, 0.3)',
            borderRadius: '12px',
            padding: '1.5rem',
            marginBottom: '1.5rem'
          }}>
            <h2 style={{ marginTop: 0, marginBottom: '1rem', color: '#ffc107' }}>
              ⚠️ Promote Staging to Production
            </h2>
            <div style={{ marginBottom: '1rem', color: 'rgba(232, 238, 252, 0.8)' }}>
              <p style={{ marginBottom: '0.5rem' }}>
                <strong>Warning:</strong> This operation will copy all data from the staging database to the production database.
              </p>
              <p style={{ marginBottom: '0.5rem' }}>
                This will <strong>overwrite</strong> all production data with staging data. This action cannot be undone.
              </p>
              <ul style={{ marginLeft: '1.5rem', marginTop: '0.5rem' }}>
                <li>All production users, promises, and data will be replaced</li>
                <li>This operation may take several minutes</li>
                <li>Production services may experience brief downtime</li>
              </ul>
            </div>
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem' }}>
                Type <strong>PROMOTE TO PROD</strong> to confirm:
              </label>
              <input
                type="text"
                value={promoteConfirmText}
                onChange={(e) => setPromoteConfirmText(e.target.value)}
                placeholder="PROMOTE TO PROD"
                style={{
                  width: '100%',
                  padding: '0.5rem',
                  borderRadius: '6px',
                  border: '1px solid rgba(232, 238, 252, 0.2)',
                  background: 'rgba(11, 16, 32, 0.6)',
                  color: '#fff',
                  fontSize: '1rem'
                }}
              />
            </div>
            <button
              onClick={async () => {
                if (promoteConfirmText !== 'PROMOTE TO PROD') {
                  setError('Please type "PROMOTE TO PROD" to confirm');
                  return;
                }
                if (!confirm('Are you absolutely sure you want to promote staging to production? This will overwrite all production data!')) {
                  return;
                }
                setPromoting(true);
                setError('');
                try {
                  await apiClient.promoteStagingToProd();
                  alert('Promotion started successfully! This may take several minutes.');
                  setPromoteConfirmText('');
                } catch (err) {
                  console.error('Failed to promote:', err);
                  if (err instanceof ApiError) {
                    setError(err.message);
                  } else {
                    setError('Failed to promote staging to production');
                  }
                } finally {
                  setPromoting(false);
                }
              }}
              disabled={promoting || promoteConfirmText !== 'PROMOTE TO PROD'}
              style={{
                padding: '0.75rem 1.5rem',
                background: promoting ? 'rgba(255, 193, 7, 0.3)' : 'linear-gradient(135deg, #ff6b6b, #ee5a6f)',
                border: 'none',
                borderRadius: '6px',
                color: '#fff',
                cursor: promoting ? 'not-allowed' : 'pointer',
                fontSize: '1rem',
                fontWeight: '600',
                opacity: (promoting || promoteConfirmText !== 'PROMOTE TO PROD') ? 0.5 : 1,
                width: '100%'
              }}
            >
              {promoting ? 'Promoting...' : '🚀 Promote Staging to Production'}
            </button>
          </div>
        </div>
      )}

      {activeTab === 'devtools' && (
        <div className="admin-panel-devtools">
          <h2 style={{ marginBottom: '1.5rem', color: '#fff' }}>Developer Tools</h2>
          <div style={{ display: 'grid', gap: '1rem' }}>
            <DevToolLink
              name="Better Stack"
              description="Monitoring and observability"
              url="https://telemetry.betterstack.com/team/t480691/tail?s=1619692"
              icon="📊"
            />
            <DevToolLink
              name="Neon Database"
              description="PostgreSQL database management"
              url="https://console.neon.tech/app/projects/royal-shape-47999151"
              icon="🗄️"
            />
            <DevToolLink
              name="GitHub"
              description="Source code repository"
              url="https://github.com/zana-AI/zana_planner"
              icon="🐙"
            />
            <DevToolLink
              name="GitHub Actions"
              description="CI/CD pipelines and workflows"
              url="https://github.com/zana-AI/zana_planner/actions"
              icon="⚙️"
            />
          </div>
        </div>
      )}
    </div>
  );
}

// Dev Tool Link Component
function DevToolLink({ name, description, url, icon }: { name: string; description: string; url: string; icon: string }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      style={{
        display: 'block',
        background: 'rgba(15, 23, 48, 0.6)',
        border: '1px solid rgba(232, 238, 252, 0.1)',
        borderRadius: '8px',
        padding: '1.5rem',
        textDecoration: 'none',
        color: 'inherit',
        transition: 'all 0.2s',
        cursor: 'pointer'
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = 'rgba(15, 23, 48, 0.8)';
        e.currentTarget.style.borderColor = 'rgba(91, 163, 245, 0.4)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = 'rgba(15, 23, 48, 0.6)';
        e.currentTarget.style.borderColor = 'rgba(232, 238, 252, 0.1)';
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <div style={{ fontSize: '2rem' }}>{icon}</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '1.1rem', fontWeight: '600', color: '#fff', marginBottom: '0.25rem' }}>
            {name}
          </div>
          <div style={{ fontSize: '0.85rem', color: 'rgba(232, 238, 252, 0.6)' }}>
            {description}
          </div>
        </div>
        <div style={{ color: 'rgba(91, 163, 245, 0.8)' }}>→</div>
      </div>
    </a>
  );
}

// Template Form Component
// Emoji picker options
const EMOJI_OPTIONS = ['🏃', '📚', '💪', '🧘', '🎯', '✍️', '🎨', '🎵', '💻', '🌱', '💧', '😴', '🍎', '💰', '🧠', '❤️'];

// Category options
const CATEGORY_OPTIONS = ['health', 'fitness', 'learning', 'productivity', 'mindfulness', 'creativity', 'finance', 'social', 'self-care', 'other'];

function TemplateForm({ template, onSave, onCancel }: { template: Partial<PromiseTemplate>, onSave: (data: any) => void, onCancel: () => void }) {
  const [prompt, setPrompt] = useState('');
  const [generating, setGenerating] = useState(false);
  const [formData, setFormData] = useState({
    title: template.title || '',
    description: template.description || '',
    category: template.category || 'other',
    target_value: template.target_value || 7,
    metric_type: template.metric_type || 'count',
    emoji: template.emoji || '',
    is_active: template.is_active !== undefined ? (typeof template.is_active === 'number' ? template.is_active !== 0 : template.is_active) : true,
  });

  const handleGenerate = async () => {
    if (!prompt.trim()) return;
    setGenerating(true);
    try {
      const draft = await apiClient.generateTemplateDraft(prompt);
      setFormData({
        title: draft.title || '',
        description: draft.description || '',
        category: draft.category || 'other',
        target_value: draft.target_value || 7,
        metric_type: draft.metric_type || 'count',
        emoji: draft.emoji || '',
        is_active: true,
      });
    } catch (err) {
      console.error('Failed to generate template:', err);
      alert('Failed to generate template. Please try again.');
    } finally {
      setGenerating(false);
    }
  };

  const inputStyle = {
    width: '100%',
    padding: '0.75rem',
    borderRadius: '8px',
    border: '1px solid rgba(232, 238, 252, 0.15)',
    background: 'rgba(11, 16, 32, 0.6)',
    color: '#fff',
    fontSize: '0.95rem'
  };

  const labelStyle = {
    display: 'block',
    marginBottom: '0.5rem',
    color: 'rgba(232, 238, 252, 0.7)',
    fontSize: '0.85rem',
    fontWeight: '500' as const
  };

  return (
    <div style={{
      background: 'rgba(15, 23, 48, 0.9)',
      border: '1px solid rgba(232, 238, 252, 0.15)',
      borderRadius: '16px',
      padding: '1.5rem',
      marginBottom: '1.5rem'
    }}>
      <h3 style={{ marginTop: 0, marginBottom: '1.25rem', color: '#fff', fontSize: '1.2rem' }}>
        {template.template_id ? '✏️ Edit Template' : '✨ Create Template'}
      </h3>

      {/* AI Generation Section */}
      {!template.template_id && (
        <div style={{
          marginBottom: '1.5rem',
          padding: '1rem',
          background: 'linear-gradient(135deg, rgba(91, 163, 245, 0.1), rgba(118, 75, 162, 0.1))',
          borderRadius: '12px',
          border: '1px solid rgba(91, 163, 245, 0.2)'
        }}>
          <label style={{ ...labelStyle, color: '#5ba3f5' }}>
            🤖 Quick Create with AI
          </label>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g., Exercise 3 times a week"
              onKeyPress={(e) => e.key === 'Enter' && handleGenerate()}
              style={{ ...inputStyle, flex: 1 }}
            />
            <button
              onClick={handleGenerate}
              disabled={!prompt.trim() || generating}
              style={{
                padding: '0.75rem 1.25rem',
                background: generating ? 'rgba(91, 163, 245, 0.3)' : 'linear-gradient(135deg, #5ba3f5, #667eea)',
                border: 'none',
                borderRadius: '8px',
                color: '#fff',
                cursor: (!prompt.trim() || generating) ? 'not-allowed' : 'pointer',
                opacity: (!prompt.trim() || generating) ? 0.6 : 1,
                fontWeight: '600',
                whiteSpace: 'nowrap'
              }}
            >
              {generating ? '...' : 'Generate'}
            </button>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gap: '1.25rem' }}>
        {/* Title + Emoji Row */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '1rem', alignItems: 'end' }}>
          <div>
            <label style={labelStyle}>Title *</label>
            <input
              type="text"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              placeholder="e.g., Daily Exercise"
              style={inputStyle}
            />
          </div>
          <div>
            <label style={labelStyle}>Emoji</label>
            <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', maxWidth: '200px' }}>
              {EMOJI_OPTIONS.map(emoji => (
                <button
                  key={emoji}
                  onClick={() => setFormData({ ...formData, emoji: formData.emoji === emoji ? '' : emoji })}
                  style={{
                    width: '32px',
                    height: '32px',
                    border: formData.emoji === emoji ? '2px solid #5ba3f5' : '1px solid rgba(232, 238, 252, 0.15)',
                    borderRadius: '6px',
                    background: formData.emoji === emoji ? 'rgba(91, 163, 245, 0.2)' : 'rgba(11, 16, 32, 0.6)',
                    cursor: 'pointer',
                    fontSize: '1rem'
                  }}
                >
                  {emoji}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Description */}
        <div>
          <label style={labelStyle}>Description (optional)</label>
          <textarea
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
            rows={2}
            placeholder="Why is this habit valuable?"
            style={{ ...inputStyle, resize: 'vertical' }}
          />
        </div>

        {/* Category + Target Row */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
          <div>
            <label style={labelStyle}>Category</label>
            <select
              value={formData.category}
              onChange={(e) => setFormData({ ...formData, category: e.target.value })}
              style={inputStyle}
            >
              {CATEGORY_OPTIONS.map(cat => (
                <option key={cat} value={cat}>{cat.charAt(0).toUpperCase() + cat.slice(1)}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={labelStyle}>Target</label>
            <input
              type="number"
              step="1"
              min="1"
              value={formData.target_value}
              onChange={(e) => setFormData({ ...formData, target_value: parseFloat(e.target.value) || 1 })}
              style={inputStyle}
            />
          </div>
          <div>
            <label style={labelStyle}>Per Week</label>
            <select
              value={formData.metric_type}
              onChange={(e) => setFormData({ ...formData, metric_type: e.target.value as 'hours' | 'count' })}
              style={inputStyle}
            >
              <option value="count">times</option>
              <option value="hours">hours</option>
            </select>
          </div>
        </div>

        {/* Preview */}
        <div style={{
          padding: '1rem',
          background: 'rgba(0,0,0,0.2)',
          borderRadius: '10px',
          border: '1px dashed rgba(232, 238, 252, 0.1)'
        }}>
          <div style={{ fontSize: '0.8rem', color: 'rgba(232, 238, 252, 0.5)', marginBottom: '0.5rem' }}>Preview</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ fontSize: '1.5rem' }}>{formData.emoji || '🎯'}</span>
            <div>
              <div style={{ fontWeight: '600', color: '#fff' }}>{formData.title || 'Template Title'}</div>
              <div style={{ fontSize: '0.85rem', color: 'rgba(232, 238, 252, 0.6)' }}>
                {formData.target_value} {formData.metric_type === 'hours' ? 'hours' : 'times'}/week • {formData.category}
              </div>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', paddingTop: '0.5rem' }}>
          <button
            onClick={onCancel}
            style={{
              padding: '0.75rem 1.5rem',
              background: 'transparent',
              border: '1px solid rgba(232, 238, 252, 0.2)',
              borderRadius: '8px',
              color: 'rgba(232, 238, 252, 0.8)',
              cursor: 'pointer',
              fontSize: '0.95rem'
            }}
          >
            Cancel
          </button>
          <button
            onClick={() => onSave(formData)}
            disabled={!formData.title.trim()}
            style={{
              padding: '0.75rem 1.5rem',
              background: !formData.title.trim() ? 'rgba(102, 126, 234, 0.3)' : 'linear-gradient(135deg, #667eea, #764ba2)',
              border: 'none',
              borderRadius: '8px',
              color: '#fff',
              cursor: !formData.title.trim() ? 'not-allowed' : 'pointer',
              fontSize: '0.95rem',
              fontWeight: '600'
            }}
          >
            {template.template_id ? 'Save Changes' : 'Create Template'}
          </button>
        </div>
      </div>
    </div>
  );
}

// Delete Confirmation Modal
function DeleteConfirmModal({ templateId, templateTitle, onConfirm, onCancel, confirmText, onConfirmTextChange }: {
  templateId: string;
  templateTitle: string;
  onConfirm: () => void;
  onCancel: () => void;
  confirmText: string;
  onConfirmTextChange: (text: string) => void;
}) {
  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0, 0, 0, 0.7)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000
    }}>
      <div style={{
        background: 'rgba(15, 23, 48, 0.98)',
        border: '1px solid rgba(232, 238, 252, 0.2)',
        borderRadius: '12px',
        padding: '1.5rem',
        maxWidth: '400px',
        width: '90%'
      }}>
        <h3 style={{ marginTop: 0, color: '#ff6b6b' }}>Delete Template</h3>
        <p style={{ color: 'rgba(232, 238, 252, 0.8)', marginBottom: '1rem' }}>
          Are you sure you want to delete <strong>{templateTitle}</strong>?
        </p>
        <p style={{ color: 'rgba(232, 238, 252, 0.6)', fontSize: '0.85rem', marginBottom: '1rem' }}>
          This action cannot be undone. Type the template ID to confirm:
        </p>
        <input
          type="text"
          value={confirmText}
          onChange={(e) => onConfirmTextChange(e.target.value)}
          placeholder={templateId}
          style={{
            width: '100%',
            padding: '0.5rem',
            borderRadius: '6px',
            border: '1px solid rgba(232, 238, 252, 0.2)',
            background: 'rgba(11, 16, 32, 0.6)',
            color: '#fff',
            marginBottom: '1rem'
          }}
        />
        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
          <button
            onClick={onCancel}
            style={{
              padding: '0.5rem 1rem',
              background: 'rgba(232, 238, 252, 0.1)',
              border: '1px solid rgba(232, 238, 252, 0.2)',
              borderRadius: '6px',
              color: '#fff',
              cursor: 'pointer'
            }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={confirmText !== templateId}
            style={{
              padding: '0.5rem 1rem',
              background: confirmText === templateId ? '#ff6b6b' : 'rgba(255, 107, 107, 0.3)',
              border: 'none',
              borderRadius: '6px',
              color: '#fff',
              cursor: confirmText === templateId ? 'pointer' : 'not-allowed',
              opacity: confirmText === templateId ? 1 : 0.5
            }}
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

