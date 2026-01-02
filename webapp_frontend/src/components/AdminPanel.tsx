import { useState, useEffect } from 'react';
import { apiClient, ApiError } from '../api/client';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import type { AdminUser, Broadcast, CreateBroadcastRequest } from '../types';

export function AdminPanel() {
  const { user, initData } = useTelegramWebApp();
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
  const [activeTab, setActiveTab] = useState<'compose' | 'scheduled'>('compose');

  // Set initData for API client
  useEffect(() => {
    if (initData) {
      apiClient.setInitData(initData);
    }
  }, [initData]);

  // Fetch users
  useEffect(() => {
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
  }, []);

  // Fetch broadcasts
  const fetchBroadcasts = async () => {
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
    if (activeTab === 'scheduled') {
      fetchBroadcasts();
    }
  }, [activeTab]);

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
        <div className="admin-panel-header">
          <h1 className="admin-panel-title">Admin Panel</h1>
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
        <div className="admin-panel-header">
          <h1 className="admin-panel-title">Admin Panel</h1>
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
      <div className="admin-panel-header">
        <h1 className="admin-panel-title">Admin Panel</h1>
        <div className="admin-panel-tabs">
          <button
            className={`admin-tab ${activeTab === 'compose' ? 'active' : ''}`}
            onClick={() => setActiveTab('compose')}
          >
            Compose
          </button>
          <button
            className={`admin-tab ${activeTab === 'scheduled' ? 'active' : ''}`}
            onClick={() => setActiveTab('scheduled')}
          >
            Scheduled ({broadcasts.length})
          </button>
        </div>
      </div>

      {error && !error.includes('Access denied') && (
        <div className="admin-panel-error-banner">
          <p>{error}</p>
          <button onClick={() => setError('')}>×</button>
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
    </div>
  );
}

