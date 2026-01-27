import React, { useState } from 'react';
import { apiClient, ApiError } from '../../api/client';
import type { AdminUser, CreatePromiseForUserRequest } from '../../types';
import { UserSelector } from './UserSelector';
import { inputStyle, labelStyle } from './styles';

interface CreatePromiseTabProps {
  users: AdminUser[];
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  error: string;
  setError: (error: string) => void;
}

export function CreatePromiseTab({
  users,
  searchQuery,
  setSearchQuery,
  error,
  setError,
}: CreatePromiseTabProps) {
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [formData, setFormData] = useState({
    text: '',
    hours_per_week: 0,
    recurring: true,
    start_date: new Date().toISOString().split('T')[0],
    end_date: '',
    visibility: 'private' as 'private' | 'followers' | 'clubs' | 'public',
    description: ''
  });
  const [remindersEnabled, setRemindersEnabled] = useState(false);
  const [reminderTime, setReminderTime] = useState('09:00');
  const [selectedDays, setSelectedDays] = useState<Set<number>>(new Set());
  const [creating, setCreating] = useState(false);

  const dayNames = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  const dayAbbrevs = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  const toggleDay = (weekday: number) => {
    const newSelected = new Set(selectedDays);
    if (newSelected.has(weekday)) {
      newSelected.delete(weekday);
    } else {
      newSelected.add(weekday);
    }
    setSelectedDays(newSelected);
  };

  const selectAllDays = () => {
    setSelectedDays(new Set([0, 1, 2, 3, 4, 5, 6]));
  };

  const deselectAllDays = () => {
    setSelectedDays(new Set());
  };

  const handleSubmit = async () => {
    if (!selectedUserId) {
      setError('Please select a user');
      return;
    }
    if (!formData.text.trim()) {
      setError('Please enter promise text');
      return;
    }
    if (formData.hours_per_week < 0) {
      setError('Hours per week must be >= 0');
      return;
    }
    if (formData.end_date && formData.start_date && formData.end_date < formData.start_date) {
      setError('End date must be >= start date');
      return;
    }
    if (remindersEnabled && selectedDays.size === 0) {
      setError('Please select at least one day for reminders');
      return;
    }

    setCreating(true);
    setError('');

    try {
      const request: CreatePromiseForUserRequest = {
        target_user_id: selectedUserId,
        text: formData.text.trim(),
        hours_per_week: formData.hours_per_week,
        recurring: formData.recurring,
        start_date: formData.start_date || undefined,
        end_date: formData.end_date || undefined,
        visibility: formData.visibility,
        description: formData.description.trim() || undefined,
        reminders: remindersEnabled && selectedDays.size > 0
          ? Array.from(selectedDays).map(weekday => ({
              weekday,
              time: reminderTime,
              enabled: true
            }))
          : undefined
      };

      const result = await apiClient.createPromiseForUser(request);
      alert(`✅ Promise created successfully!\n\nPromise ID: ${result.promise_id}\n${result.message}`);
      
      // Reset form
      setSelectedUserId(null);
      setFormData({
        text: '',
        hours_per_week: 0,
        recurring: true,
        start_date: new Date().toISOString().split('T')[0],
        end_date: '',
        visibility: 'private',
        description: ''
      });
      setRemindersEnabled(false);
      setReminderTime('09:00');
      setSelectedDays(new Set());
    } catch (err) {
      console.error('Failed to create promise:', err);
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to create promise. Please try again.');
      }
    } finally {
      setCreating(false);
    }
  };

  const selectedDaysPreview = Array.from(selectedDays)
    .sort()
    .map(d => dayAbbrevs[d])
    .join(', ');

  return (
    <div className="admin-panel-compose">
      <div className="admin-section">
        <h2 className="admin-section-title">Select User</h2>
        <UserSelector
          users={users}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          selectedUserId={selectedUserId}
          onSelectUser={setSelectedUserId}
          mode="single"
          maxHeight="200px"
        />
      </div>

      <div className="admin-section">
        <h2 className="admin-section-title">Promise Details</h2>
        <div style={{ display: 'grid', gap: '1.25rem' }}>
          <div>
            <label style={labelStyle}>Promise Text *</label>
            <input
              type="text"
              value={formData.text}
              onChange={(e) => setFormData({ ...formData, text: e.target.value })}
              placeholder="e.g., Daily Exercise"
              style={inputStyle}
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={labelStyle}>Hours per Week</label>
              <input
                type="number"
                value={formData.hours_per_week}
                onChange={(e) => setFormData({ ...formData, hours_per_week: parseFloat(e.target.value) || 0 })}
                min="0"
                step="0.1"
                style={inputStyle}
              />
              <p style={{ fontSize: '0.75rem', color: 'rgba(232, 238, 252, 0.5)', marginTop: '0.25rem' }}>
                0.0 for check-based promises
              </p>
            </div>
            <div>
              <label style={labelStyle}>Recurring</label>
              <div style={{ display: 'flex', alignItems: 'center', marginTop: '0.5rem' }}>
                <input
                  type="checkbox"
                  checked={formData.recurring}
                  onChange={(e) => setFormData({ ...formData, recurring: e.target.checked })}
                  style={{ width: '20px', height: '20px', cursor: 'pointer' }}
                />
                <span style={{ marginLeft: '0.5rem', color: 'rgba(232, 238, 252, 0.8)' }}>Recurring promise</span>
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={labelStyle}>Start Date</label>
              <input
                type="date"
                value={formData.start_date}
                onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
                style={inputStyle}
              />
            </div>
            <div>
              <label style={labelStyle}>End Date (Optional)</label>
              <input
                type="date"
                value={formData.end_date}
                onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                min={formData.start_date}
                style={inputStyle}
              />
            </div>
          </div>

          <div>
            <label style={labelStyle}>Visibility</label>
            <select
              value={formData.visibility}
              onChange={(e) => setFormData({ ...formData, visibility: e.target.value as any })}
              style={inputStyle}
            >
              <option value="private">Private</option>
              <option value="followers">Followers</option>
              <option value="clubs">Clubs</option>
              <option value="public">Public</option>
            </select>
          </div>

          <div>
            <label style={labelStyle}>Description (Optional)</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              rows={3}
              placeholder="Additional description or notes..."
              style={{ ...inputStyle, resize: 'vertical' }}
            />
          </div>
        </div>
      </div>

      <div className="admin-section">
        <h2 className="admin-section-title">Reminders (Optional)</h2>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: '1rem' }}>
          <input
            type="checkbox"
            checked={remindersEnabled}
            onChange={(e) => {
              setRemindersEnabled(e.target.checked);
              if (!e.target.checked) {
                setSelectedDays(new Set());
              }
            }}
            style={{ width: '20px', height: '20px', cursor: 'pointer' }}
          />
          <span style={{ marginLeft: '0.5rem', color: 'rgba(232, 238, 252, 0.8)' }}>Enable reminders</span>
        </div>

        {remindersEnabled && (
          <div style={{ display: 'grid', gap: '1rem' }}>
            <div>
              <label style={labelStyle}>Reminder Time</label>
              <input
                type="time"
                value={reminderTime}
                onChange={(e) => setReminderTime(e.target.value)}
                style={inputStyle}
              />
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <label style={labelStyle}>Days of Week</label>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    type="button"
                    onClick={selectAllDays}
                    style={{
                      padding: '0.25rem 0.5rem',
                      background: 'rgba(91, 163, 245, 0.2)',
                      border: '1px solid rgba(91, 163, 245, 0.4)',
                      borderRadius: '4px',
                      color: '#5ba3f5',
                      cursor: 'pointer',
                      fontSize: '0.75rem'
                    }}
                  >
                    Select All
                  </button>
                  <button
                    type="button"
                    onClick={deselectAllDays}
                    style={{
                      padding: '0.25rem 0.5rem',
                      background: 'rgba(232, 238, 252, 0.1)',
                      border: '1px solid rgba(232, 238, 252, 0.2)',
                      borderRadius: '4px',
                      color: 'rgba(232, 238, 252, 0.8)',
                      cursor: 'pointer',
                      fontSize: '0.75rem'
                    }}
                  >
                    Deselect All
                  </button>
                </div>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                {dayNames.map((_day, index) => {
                  const isSelected = selectedDays.has(index);
                  return (
                    <button
                      key={index}
                      type="button"
                      onClick={() => toggleDay(index)}
                      style={{
                        padding: '0.5rem 1rem',
                        background: isSelected ? 'rgba(91, 163, 245, 0.3)' : 'rgba(11, 16, 32, 0.6)',
                        border: isSelected ? '2px solid #5ba3f5' : '1px solid rgba(232, 238, 252, 0.15)',
                        borderRadius: '6px',
                        color: '#fff',
                        cursor: 'pointer',
                        fontSize: '0.85rem',
                        fontWeight: isSelected ? '600' : '400'
                      }}
                    >
                      {dayAbbrevs[index]}
                    </button>
                  );
                })}
              </div>
              {selectedDays.size > 0 && (
                <p style={{ fontSize: '0.75rem', color: 'rgba(232, 238, 252, 0.6)', marginTop: '0.5rem' }}>
                  Selected: {selectedDaysPreview} at {reminderTime}
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="admin-panel-error-banner">
          <p>{error}</p>
          <button onClick={() => setError('')}>×</button>
        </div>
      )}

      <div className="admin-actions">
        <button
          className="admin-send-btn"
          onClick={handleSubmit}
          disabled={creating || !selectedUserId || !formData.text.trim()}
          style={{
            opacity: (creating || !selectedUserId || !formData.text.trim()) ? 0.5 : 1,
            cursor: (creating || !selectedUserId || !formData.text.trim()) ? 'not-allowed' : 'pointer'
          }}
        >
          {creating ? 'Creating...' : 'Create Promise'}
        </button>
      </div>
    </div>
  );
}
