import { useState, useEffect } from 'react';
import { apiClient, ApiError } from '../../api/client';
import type { AdminUser, BotToken, CreateBroadcastRequest } from '../../types';
import { UserSelector } from './UserSelector';
import type { TabType } from './AdminTabs';

interface BroadcastTabProps {
  users: AdminUser[];
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  setError: (error: string) => void;
  onTabChange: (tab: TabType) => void;
  onRefreshBroadcasts: () => void;
}

export function BroadcastTab({
  users,
  searchQuery,
  setSearchQuery,
  setError,
  onTabChange,
  onRefreshBroadcasts,
}: BroadcastTabProps) {
  const [message, setMessage] = useState('');
  const [selectedUserIds, setSelectedUserIds] = useState<Set<number>>(new Set());
  const [scheduledTime, setScheduledTime] = useState('');
  const [sending, setSending] = useState(false);
  const [botTokens, setBotTokens] = useState<BotToken[]>([]);
  const [selectedBotTokenId, setSelectedBotTokenId] = useState<string>('');
  const [loadingBotTokens, setLoadingBotTokens] = useState(false);

  // Fetch bot tokens
  useEffect(() => {
    const fetchBotTokens = async () => {
      setLoadingBotTokens(true);
      try {
        const tokens = await apiClient.getBotTokens(true);
        setBotTokens(tokens);
      } catch (err) {
        console.error('Failed to fetch bot tokens:', err);
      } finally {
        setLoadingBotTokens(false);
      }
    };
    fetchBotTokens();
  }, []);

  // Filter users for select all
  const filteredUsers = users.filter(user => {
    const query = searchQuery.toLowerCase();
    const firstName = user.first_name?.toLowerCase() || '';
    const lastName = user.last_name?.toLowerCase() || '';
    const username = user.username?.toLowerCase() || '';
    const userId = user.user_id.toLowerCase();
    return firstName.includes(query) || lastName.includes(query) || username.includes(query) || userId.includes(query);
  });

  const toggleUser = (userId: number) => {
    const newSelected = new Set(selectedUserIds);
    if (newSelected.has(userId)) {
      newSelected.delete(userId);
    } else {
      newSelected.add(userId);
    }
    setSelectedUserIds(newSelected);
  };

  const toggleSelectAll = () => {
    if (selectedUserIds.size === filteredUsers.length) {
      setSelectedUserIds(new Set());
    } else {
      setSelectedUserIds(new Set(filteredUsers.map(u => parseInt(u.user_id))));
    }
  };

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
      
      // Refresh broadcasts
      await onRefreshBroadcasts();
      
      // Switch to scheduled tab to see the new broadcast
      onTabChange('scheduled');
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

  const getCurrentDateTime = () => {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    return now.toISOString().slice(0, 16);
  };

  return (
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
        <UserSelector
          users={users}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          selectedUserIds={selectedUserIds}
          onToggleUser={toggleUser}
          mode="multi"
          showSearchInput={true}
          onSelectAll={toggleSelectAll}
          selectAllLabel={selectedUserIds.size === filteredUsers.length ? 'Deselect All' : 'Select All'}
        />
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
  );
}
