import { useState, useEffect } from 'react';
import { apiClient, ApiError } from '../api/client';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import { UserAvatar } from './UserAvatar';
import type { AdminUser, Broadcast, CreateBroadcastRequest, PromiseTemplate } from '../types';

export function AdminPanel() {
  const { initData } = useTelegramWebApp();
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
  const [activeTab, setActiveTab] = useState<'stats' | 'compose' | 'scheduled' | 'templates'>('stats');
  const [stats, setStats] = useState<{ total_users: number; active_users: number; total_promises: number } | null>(null);
  const [loadingStats, setLoadingStats] = useState(false);
  const [statsError, setStatsError] = useState<string>('');
  const [templates, setTemplates] = useState<PromiseTemplate[]>([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<PromiseTemplate | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(null);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');

  // Check for authentication (initData or browser token)
  const hasToken = !!localStorage.getItem('telegram_auth_token');
  const isAuthenticated = !!initData || hasToken;

  // Set initData for API client
  useEffect(() => {
    if (initData) {
      apiClient.setInitData(initData);
    }
  }, [initData]);

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
        <UserAvatar size={40} showMenu={false} />
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
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: '1.1rem', fontWeight: '600', color: '#fff', marginBottom: '0.25rem' }}>
                        {template.title}
                      </div>
                      <div style={{ fontSize: '0.85rem', color: 'rgba(232, 238, 252, 0.6)' }}>
                        {template.category} • {template.level} • {template.metric_type} • {template.is_active ? 'Active' : 'Inactive'}
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
    </div>
  );
}

// Template Form Component
function TemplateForm({ template, onSave, onCancel }: { template: Partial<PromiseTemplate>, onSave: (data: any) => void, onCancel: () => void }) {
  const [formData, setFormData] = useState({
    category: template.category || '',
    program_key: template.program_key || '',
    level: template.level || '',
    title: template.title || '',
    why: template.why || '',
    done: template.done || '',
    effort: template.effort || '',
    template_kind: template.template_kind || 'commitment',
    metric_type: template.metric_type || 'hours',
    target_value: template.target_value || 0,
    target_direction: template.target_direction || 'at_least',
    estimated_hours_per_unit: template.estimated_hours_per_unit || 1.0,
    duration_type: template.duration_type || 'week',
    duration_weeks: template.duration_weeks || 1,
    is_active: template.is_active !== undefined ? (typeof template.is_active === 'number' ? template.is_active !== 0 : template.is_active) : true,
  });

  return (
    <div style={{
      background: 'rgba(15, 23, 48, 0.8)',
      border: '1px solid rgba(232, 238, 252, 0.2)',
      borderRadius: '12px',
      padding: '1.5rem',
      marginBottom: '1.5rem'
    }}>
      <h3 style={{ marginTop: 0, marginBottom: '1rem', color: '#fff' }}>
        {template.template_id ? 'Edit Template' : 'Create Template'}
      </h3>
      <div style={{ display: 'grid', gap: '1rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem' }}>Category *</label>
            <input
              type="text"
              value={formData.category}
              onChange={(e) => setFormData({ ...formData, category: e.target.value })}
              style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid rgba(232, 238, 252, 0.2)', background: 'rgba(11, 16, 32, 0.6)', color: '#fff' }}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem' }}>Level *</label>
            <input
              type="text"
              value={formData.level}
              onChange={(e) => setFormData({ ...formData, level: e.target.value })}
              style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid rgba(232, 238, 252, 0.2)', background: 'rgba(11, 16, 32, 0.6)', color: '#fff' }}
            />
          </div>
        </div>
        <div>
          <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem' }}>Title *</label>
          <input
            type="text"
            value={formData.title}
            onChange={(e) => setFormData({ ...formData, title: e.target.value })}
            style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid rgba(232, 238, 252, 0.2)', background: 'rgba(11, 16, 32, 0.6)', color: '#fff' }}
          />
        </div>
        <div>
          <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem' }}>Why *</label>
          <textarea
            value={formData.why}
            onChange={(e) => setFormData({ ...formData, why: e.target.value })}
            rows={2}
            style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid rgba(232, 238, 252, 0.2)', background: 'rgba(11, 16, 32, 0.6)', color: '#fff' }}
          />
        </div>
        <div>
          <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem' }}>Done *</label>
          <textarea
            value={formData.done}
            onChange={(e) => setFormData({ ...formData, done: e.target.value })}
            rows={2}
            style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid rgba(232, 238, 252, 0.2)', background: 'rgba(11, 16, 32, 0.6)', color: '#fff' }}
          />
        </div>
        <div>
          <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem' }}>Effort *</label>
          <textarea
            value={formData.effort}
            onChange={(e) => setFormData({ ...formData, effort: e.target.value })}
            rows={2}
            style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid rgba(232, 238, 252, 0.2)', background: 'rgba(11, 16, 32, 0.6)', color: '#fff' }}
          />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem' }}>Program Key (Optional)</label>
            <input
              type="text"
              value={formData.program_key}
              onChange={(e) => setFormData({ ...formData, program_key: e.target.value })}
              placeholder="e.g., fitness, learning"
              style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid rgba(232, 238, 252, 0.2)', background: 'rgba(11, 16, 32, 0.6)', color: '#fff' }}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem' }}>Template Kind *</label>
            <select
              value={formData.template_kind}
              onChange={(e) => setFormData({ ...formData, template_kind: e.target.value as 'commitment' | 'budget' })}
              style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid rgba(232, 238, 252, 0.2)', background: 'rgba(11, 16, 32, 0.6)', color: '#fff' }}
            >
              <option value="commitment">Commitment</option>
              <option value="budget">Budget</option>
            </select>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem' }}>Metric Type *</label>
            <select
              value={formData.metric_type}
              onChange={(e) => setFormData({ ...formData, metric_type: e.target.value as 'hours' | 'count' })}
              style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid rgba(232, 238, 252, 0.2)', background: 'rgba(11, 16, 32, 0.6)', color: '#fff' }}
            >
              <option value="hours">Hours</option>
              <option value="count">Count</option>
            </select>
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem' }}>Target Value *</label>
            <input
              type="number"
              step="0.1"
              min="0"
              value={formData.target_value}
              onChange={(e) => setFormData({ ...formData, target_value: parseFloat(e.target.value) || 0 })}
              style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid rgba(232, 238, 252, 0.2)', background: 'rgba(11, 16, 32, 0.6)', color: '#fff' }}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem' }}>Target Direction *</label>
            <select
              value={formData.target_direction}
              onChange={(e) => setFormData({ ...formData, target_direction: e.target.value as 'at_least' | 'at_most' })}
              style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid rgba(232, 238, 252, 0.2)', background: 'rgba(11, 16, 32, 0.6)', color: '#fff' }}
            >
              <option value="at_least">At Least</option>
              <option value="at_most">At Most</option>
            </select>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem' }}>Duration Type *</label>
            <select
              value={formData.duration_type}
              onChange={(e) => setFormData({ ...formData, duration_type: e.target.value as 'week' | 'one_time' | 'date' })}
              style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid rgba(232, 238, 252, 0.2)', background: 'rgba(11, 16, 32, 0.6)', color: '#fff' }}
            >
              <option value="week">Week</option>
              <option value="one_time">One Time</option>
              <option value="date">Date</option>
            </select>
          </div>
          {formData.duration_type === 'week' && (
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem' }}>Duration Weeks</label>
              <input
                type="number"
                min="1"
                value={formData.duration_weeks}
                onChange={(e) => setFormData({ ...formData, duration_weeks: parseInt(e.target.value) || 1 })}
                style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid rgba(232, 238, 252, 0.2)', background: 'rgba(11, 16, 32, 0.6)', color: '#fff' }}
              />
            </div>
          )}
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem' }}>Estimated Hours Per Unit</label>
            <input
              type="number"
              step="0.1"
              min="0"
              value={formData.estimated_hours_per_unit}
              onChange={(e) => setFormData({ ...formData, estimated_hours_per_unit: parseFloat(e.target.value) || 1.0 })}
              style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid rgba(232, 238, 252, 0.2)', background: 'rgba(11, 16, 32, 0.6)', color: '#fff' }}
            />
          </div>
        </div>
        <div>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={formData.is_active}
              onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
              style={{ cursor: 'pointer' }}
            />
            Active (template will be visible to users)
          </label>
        </div>
        <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
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
            onClick={() => onSave(formData)}
            disabled={
              !formData.category || 
              !formData.level || 
              !formData.title || 
              !formData.why || 
              !formData.done || 
              !formData.effort ||
              !formData.metric_type ||
              formData.target_value <= 0 ||
              !formData.duration_type
            }
            style={{
              padding: '0.5rem 1rem',
              background: 'linear-gradient(135deg, #667eea, #764ba2)',
              border: 'none',
              borderRadius: '6px',
              color: '#fff',
              cursor: 'pointer',
              opacity: (
                !formData.category || 
                !formData.level || 
                !formData.title || 
                !formData.why || 
                !formData.done || 
                !formData.effort ||
                !formData.metric_type ||
                formData.target_value <= 0 ||
                !formData.duration_type
              ) ? 0.5 : 1
            }}
          >
            Save
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

