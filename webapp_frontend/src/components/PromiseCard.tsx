import { useState, useEffect } from 'react';
import type { PromiseData, SessionData } from '../types';
import { apiClient } from '../api/client';
import { LogActionModal } from './LogActionModal';
import { CheckinModal } from './CheckinModal';
import { WeeklyNoteModal } from './WeeklyNoteModal';
import { VisibilityConfirmModal } from './VisibilityConfirmModal';
import { InlineCalendar } from './InlineCalendar';

interface PromiseCardProps {
  id: string;
  data: PromiseData;
  weekDays: string[]; // Array of date strings for the week (ISO format)
  onRefresh?: () => void; // Callback to refresh data after changes
}

const DAY_LABELS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];
type PromiseProgressTone = 'strong' | 'on-track' | 'attention' | 'risk';

/**
 * Get status label based on progress percentage
 */
function getStatusLabel(progress: number): string {
  if (progress >= 90) return 'Strong progress';
  if (progress >= 60) return 'On track';
  if (progress >= 30) return 'Needs attention';
  return 'At risk';
}

function getStatusTone(progress: number): PromiseProgressTone {
  if (progress >= 90) return 'strong';
  if (progress >= 60) return 'on-track';
  if (progress >= 30) return 'attention';
  return 'risk';
}

/**
 * Calculate progress percentage
 */
function calculateProgress(spent: number, promised: number): number {
  if (promised <= 0) return 0;
  return Math.min(Math.round((spent / promised) * 100), 100);
}

/**
 * PromiseCard component - displays a single promise with progress visualization
 */
export function PromiseCard({ id, data, weekDays, onRefresh }: PromiseCardProps) {
  const { 
    text, 
    hours_promised, 
    hours_spent, 
    sessions, 
    visibility = 'private',
    recurring = true,
    metric_type = 'hours',
    target_value = hours_promised,
    target_direction = 'at_least',
    template_kind = 'commitment',
    achieved_value = hours_spent,
  } = data;
  const [currentVisibility, setCurrentVisibility] = useState<'private' | 'public'>(
    (visibility === 'public' ? 'public' : 'private') as 'private' | 'public'
  );
  const [currentRecurring, setCurrentRecurring] = useState<boolean>(recurring);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [isUpdatingVisibility, setIsUpdatingVisibility] = useState(false);
  const [isUpdatingRecurring, setIsUpdatingRecurring] = useState(false);

  // Sync recurring state when data changes
  useEffect(() => {
    setCurrentRecurring(recurring);
  }, [recurring]);
  
  // Sync editable fields when data changes
  useEffect(() => {
    setEditingText(text);
    setEditingHours(hours_promised);
    setEditingEndDate(data.end_date || '');
  }, [text, hours_promised, data.end_date]);
  const [isLogModalOpen, setIsLogModalOpen] = useState(false);
  const [isCheckinModalOpen, setIsCheckinModalOpen] = useState(false);
  const [isWeeklyNoteModalOpen, setIsWeeklyNoteModalOpen] = useState(false);
  const [showVisibilityConfirm, setShowVisibilityConfirm] = useState(false);
  const [pendingVisibility, setPendingVisibility] = useState<'private' | 'public' | null>(null);
  const [reminders, setReminders] = useState<Array<{ weekday: number; time: string; enabled: boolean }>>([]);
  const [isLoadingReminders, setIsLoadingReminders] = useState(false);
  
  // Editable fields state
  const [editingText, setEditingText] = useState(text);
  const [editingHours, setEditingHours] = useState(hours_promised);
  const [editingEndDate, setEditingEndDate] = useState(data.end_date || '');
  const [showCalendar, setShowCalendar] = useState(false);
  const [isUpdatingPromise, setIsUpdatingPromise] = useState(false);
  
  // Swipe gesture state
  const [swipeStart, setSwipeStart] = useState<{ x: number; y: number } | null>(null);
  const [swipeOffset, setSwipeOffset] = useState(0);
  const [thresholdReached, setThresholdReached] = useState(false);
  
  const SWIPE_THRESHOLD = 100; // pixels
  
  // Calculate progress based on metric type
  const isCountBased = metric_type === 'count';
  const isBudget = template_kind === 'budget';
  const isAtMost = target_direction === 'at_most';
  
  let progress: number;
  if (isCountBased) {
    progress = calculateProgress(achieved_value, target_value);
  } else if (isBudget && isAtMost) {
    // For budgets, progress is inverse: 100% when under budget, decreasing as we go over
    if (target_value > 0) {
      if (achieved_value <= target_value) {
        progress = (achieved_value / target_value) * 100;
      } else {
        // Over budget: show negative progress
        const excess = achieved_value - target_value;
        progress = Math.max(0, 100 - (excess / target_value) * 100);
      }
    } else {
      progress = achieved_value <= 0 ? 100 : 0;
    }
  } else {
    progress = calculateProgress(achieved_value, target_value);
  }
  
  const statusLabel = getStatusLabel(progress);
  const statusTone = getStatusTone(progress);
  
  const handleVisibilityToggle = () => {
    if (isUpdatingVisibility) return;
    
    const newVisibility = currentVisibility === 'private' ? 'public' : 'private';
    setPendingVisibility(newVisibility);
    setShowVisibilityConfirm(true);
  };
  
  const handleVisibilityConfirm = async () => {
    if (!pendingVisibility || isUpdatingVisibility) return;
    
    setIsUpdatingVisibility(true);
    setShowVisibilityConfirm(false);
    
    try {
      await apiClient.updatePromiseVisibility(id, pendingVisibility);
      setCurrentVisibility(pendingVisibility);
      if (onRefresh) {
        onRefresh();
      }
    } catch (err) {
      console.error('Failed to update visibility:', err);
      // Revert on error
      setCurrentVisibility((visibility === 'public' ? 'public' : 'private') as 'private' | 'public');
    } finally {
      setIsUpdatingVisibility(false);
      setPendingVisibility(null);
    }
  };
  
  const handleVisibilityCancel = () => {
    setShowVisibilityConfirm(false);
    setPendingVisibility(null);
  };
  
  const handleRecurringToggle = async () => {
    if (isUpdatingRecurring) return;
    
    const newRecurring = !currentRecurring;
    setIsUpdatingRecurring(true);
    
    try {
      await apiClient.updatePromiseRecurring(id, newRecurring);
      setCurrentRecurring(newRecurring);
      if (onRefresh) {
        onRefresh();
      }
    } catch (err) {
      console.error('Failed to update recurring status:', err);
      // Revert on error
      setCurrentRecurring(recurring);
    } finally {
      setIsUpdatingRecurring(false);
    }
  };
  
  const handleSavePromise = async () => {
    if (isUpdatingPromise) return;
    
    // Validate hours
    if (editingHours <= 0) {
      alert('Hours per week must be greater than 0');
      return;
    }
    
    setIsUpdatingPromise(true);
    
    try {
      const updateFields: { text?: string; hours_per_week?: number; end_date?: string } = {};
      
      // Only include fields that have changed
      if (editingText !== text) {
        updateFields.text = editingText;
      }
      if (editingHours !== hours_promised) {
        updateFields.hours_per_week = editingHours;
      }
      if (editingEndDate !== (data.end_date || '')) {
        updateFields.end_date = editingEndDate || undefined;
      }
      
      // Only make API call if there are changes
      if (Object.keys(updateFields).length > 0) {
        await apiClient.updatePromise(id, updateFields);
        if (onRefresh) {
          onRefresh();
        }
        // Exit edit mode after successful save
        setIsEditing(false);
      } else {
        // No changes, just exit edit mode
        setIsEditing(false);
      }
    } catch (err) {
      console.error('Failed to update promise:', err);
      alert(err instanceof Error ? err.message : 'Failed to update promise');
    } finally {
      setIsUpdatingPromise(false);
    }
  };
  
  const handleCancelEdit = () => {
    // Revert to original values
    setEditingText(text);
    setEditingHours(hours_promised);
    setEditingEndDate(data.end_date || '');
    setShowCalendar(false);
    setIsEditing(false);
  };
  
  const handleEditClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsEditing(true);
    if (!isExpanded) {
      setIsExpanded(true);
    }
    // Load reminders when entering edit mode
    if (reminders.length === 0 && !isLoadingReminders) {
      setIsLoadingReminders(true);
      try {
        const { apiClient } = await import('../api/client');
        const response = await apiClient.getPromiseReminders(id);
        // Convert backend reminder format to simple format for UI
        const simpleReminders = response.reminders
          .filter((r: any) => r.kind === 'fixed_time' && r.enabled)
          .map((r: any) => ({
            weekday: r.weekday,
            time: r.time_local ? r.time_local.substring(0, 5) : '09:00', // HH:MM format
            enabled: r.enabled !== false
          }));
        setReminders(simpleReminders);
      } catch (err) {
        console.error('Failed to load reminders:', err);
      } finally {
        setIsLoadingReminders(false);
      }
    }
  };
  
  const handleAddReminder = () => {
    setReminders([...reminders, { weekday: 0, time: '09:00', enabled: true }]);
  };
  
  const handleRemoveReminder = (index: number) => {
    setReminders(reminders.filter((_, i) => i !== index));
  };
  
  const handleUpdateReminder = (index: number, field: 'weekday' | 'time' | 'enabled', value: any) => {
    const updated = [...reminders];
    updated[index] = { ...updated[index], [field]: value };
    setReminders(updated);
  };
  
  const handleSaveReminders = async () => {
    try {
      const { apiClient } = await import('../api/client');
      // Convert to backend format
      const backendReminders = reminders.map(r => ({
        kind: 'fixed_time',
        weekday: r.weekday,
        time_local: r.time + ':00', // Add seconds
        enabled: r.enabled
      }));
      await apiClient.updatePromiseReminders(id, backendReminders);
      if (onRefresh) {
        onRefresh();
      }
    } catch (err) {
      console.error('Failed to save reminders:', err);
      alert(err instanceof Error ? err.message : 'Failed to save reminders');
    }
  };
  
  const WEEKDAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  
  const handleEndDateSelect = (date: string) => {
    setEditingEndDate(date);
    setShowCalendar(false);
  };
  
  const formatDate = (dateStr: string): string => {
    if (!dateStr) return 'Not set';
    try {
      const date = new Date(dateStr + 'T00:00:00');
      return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
    } catch {
      return dateStr;
    }
  };
  
  const handleCardHeaderClick = (e: React.MouseEvent) => {
    // Don't expand if clicking on visibility toggle or other interactive elements
    const target = e.target as HTMLElement;
    if (target.closest('.card-visibility-toggle') || target.closest('button')) {
      return;
    }
    setIsExpanded(!isExpanded);
  };
  
  const handleSwipeStart = (e: React.TouchEvent) => {
    const touch = e.touches[0];
    setSwipeStart({ x: touch.clientX, y: touch.clientY });
    setSwipeOffset(0);
  };
  
  const handleSwipeMove = (e: React.TouchEvent) => {
    if (!swipeStart) return;
    
    const touch = e.touches[0];
    const deltaX = touch.clientX - swipeStart.x;
    const deltaY = Math.abs(touch.clientY - swipeStart.y);
    
    // Only allow horizontal swipe (left)
    if (deltaX < 0 && deltaY < 50) {
      setSwipeOffset(Math.max(deltaX, -200)); // Limit to -200px
    }
  };
  
  const handleSwipeEnd = async () => {
    if (!swipeStart) return;
    
    if (swipeOffset <= -SWIPE_THRESHOLD) {
      // Trigger snooze
      try {
        await apiClient.snoozePromise(id);
        if (onRefresh) {
          onRefresh();
        }
      } catch (err) {
        console.error('Failed to snooze promise:', err);
      }
    }
    
    // Reset swipe state
    setSwipeStart(null);
    setSwipeOffset(0);
  };
  
  const handleSnoozeButtonClick = async () => {
    if (swipeOffset <= -SWIPE_THRESHOLD) {
      try {
        await apiClient.snoozePromise(id);
        if (onRefresh) {
          onRefresh();
        }
        // Reset swipe state
        setSwipeStart(null);
        setSwipeOffset(0);
      } catch (err) {
        console.error('Failed to snooze promise:', err);
      }
    }
  };
  
  // Calculate button visibility and scale based on swipe offset
  const snoozeButtonOpacity = swipeOffset < -50 
    ? Math.min(Math.abs(swipeOffset) / SWIPE_THRESHOLD, 1) 
    : 0;
  const snoozeButtonScale = swipeOffset < -50
    ? Math.min(0.5 + (Math.abs(swipeOffset) / SWIPE_THRESHOLD) * 0.5, 1)
    : 0.5;
  const isSnoozeActive = swipeOffset <= -SWIPE_THRESHOLD;
  
  // Haptic feedback when threshold is reached
  useEffect(() => {
    if (isSnoozeActive && !thresholdReached && swipeStart) {
      setThresholdReached(true);
      // Haptic feedback would go here if available
    } else if (!isSnoozeActive && thresholdReached) {
      setThresholdReached(false);
    }
  }, [isSnoozeActive, thresholdReached, swipeStart]);
  
  // Create a map of date -> value for quick lookup
  const sessionsByDate: Record<string, number> = {};
  const notesByDate: Record<string, string[]> = {};
  sessions.forEach((session: SessionData) => {
    const dateKey = typeof session.date === 'string' ? session.date : session.date;
    if (isCountBased) {
      // For count-based, sessions have 'count' field
      const count = (session as any).count || 0;
      sessionsByDate[dateKey] = (sessionsByDate[dateKey] || 0) + count;
    } else {
      sessionsByDate[dateKey] = (sessionsByDate[dateKey] || 0) + (session.hours || 0);
    }
    // Collect notes for this date
    if (session.notes && session.notes.length > 0) {
      if (!notesByDate[dateKey]) {
        notesByDate[dateKey] = [];
      }
      notesByDate[dateKey].push(...session.notes);
    }
  });
  
  // Get values for each day of the week
  const dayValues = weekDays.map(date => sessionsByDate[date] || 0);
  
  // Calculate max height for bars
  const maxDayValue = Math.max(...dayValues, 0.001);
  const dailyTarget = target_value > 0 ? target_value / 7 : 0;
  const baseline = Math.max(dailyTarget, maxDayValue, isCountBased ? 1 : 0.25);
  
  return (
    <>
      <article 
        className={`promise-card promise-card-${statusTone}`}
        style={{
          transform: swipeOffset < 0 ? `translateX(${swipeOffset}px)` : undefined,
          transition: swipeStart ? 'none' : 'transform 0.3s ease',
        }}
        onTouchStart={handleSwipeStart}
        onTouchMove={handleSwipeMove}
        onTouchEnd={handleSwipeEnd}
      >
        {/* Swipe overlay */}
        {swipeOffset < -50 && (
          <div 
            className="card-swipe-overlay"
            style={{
              opacity: Math.min(Math.abs(swipeOffset) / SWIPE_THRESHOLD, 0.3),
            }}
          />
        )}
        
        {/* Snooze button that appears during swipe */}
        {swipeOffset < -50 && (
          <div className="card-snooze-container">
            <button
              className={`card-snooze-button ${isSnoozeActive ? 'active' : ''}`}
              style={{
                opacity: snoozeButtonOpacity,
                transform: `scale(${snoozeButtonScale})`,
              }}
              onClick={handleSnoozeButtonClick}
              disabled={!isSnoozeActive}
            >
              {isSnoozeActive ? 'Snoozed until next week' : 'Swipe left to snooze'}
            </button>
          </div>
        )}
        
        <div 
          className="card-top" 
          onClick={handleCardHeaderClick}
          style={{ cursor: 'pointer' }}
        >
          <div className="card-title" dir="auto">
            <span className="card-status-label">{statusLabel}</span>
            <span className="card-title-text">{text}</span>
            {isBudget && (
              <span className="card-budget-badge">
                Budget
              </span>
            )}
            <button
              className="card-edit-button"
              onClick={handleEditClick}
              title="Edit promise"
            >
              <span>Edit</span>
            </button>
            <button
              className="card-visibility-toggle"
              onClick={(e) => {
                e.stopPropagation();
                handleVisibilityToggle();
              }}
              disabled={isUpdatingVisibility}
              title={currentVisibility === 'private' ? 'Make public' : 'Make private'}
            >
              <span>{currentVisibility === 'private' ? 'Private' : 'Public'}</span>
            </button>
          </div>
          <div className="card-meta">
            <span className="card-id" dir="ltr">#{id}</span>
            <div className="card-meta-ratio">
              <span className="card-ratio" dir="ltr">
                {isCountBased ? (
                  <>{Math.round(achieved_value)}/{Math.round(target_value)}</>
                ) : (
                  <>{achieved_value.toFixed(1)}/{target_value.toFixed(1)} h</>
                )}
              </span>
              <span className="card-pct" dir="ltr">{Math.round(progress)}%</span>
            </div>
          </div>
        </div>
        
        {/* Expanded section - shows notes when expanded, editable fields when editing */}
        {isExpanded && (
          <div 
            className="card-expanded-section"
            onClick={(e) => e.stopPropagation()}
          >
            {isEditing ? (
              /* Edit mode - show editable fields */
              <div className="card-edit-form">
                {/* Text field */}
                <div className="card-form-group">
                  <label className="card-form-label">
                    Promise Title
                  </label>
                  <input
                    type="text"
                    className="card-form-input"
                    value={editingText}
                    onChange={(e) => setEditingText(e.target.value)}
                    placeholder="Enter promise title"
                  />
                </div>
                
                {/* Hours per week field */}
                <div className="card-form-group">
                  <label className="card-form-label">
                    Hours per Week
                  </label>
                  <input
                    type="number"
                    className="card-form-input"
                    value={editingHours}
                    onChange={(e) => setEditingHours(parseFloat(e.target.value) || 0)}
                    min="0.1"
                    step="0.1"
                    placeholder="0.0"
                  />
                </div>
                
                {/* End date field */}
                <div className="card-form-group">
                  <label className="card-form-label">
                    End Date
                  </label>
                  <button
                    className="card-form-date-button"
                    onClick={() => setShowCalendar(!showCalendar)}
                  >
                    {formatDate(editingEndDate)}
                  </button>
                  {showCalendar && (
                    <InlineCalendar
                      selectedDate={editingEndDate || undefined}
                      onDateSelect={handleEndDateSelect}
                      minDate={data.start_date || undefined}
                      onClose={() => setShowCalendar(false)}
                    />
                  )}
                </div>
                
                {/* Recurring toggle */}
                <div className="card-recurring-section">
                  <div className="card-recurring-info">
                    <span className="card-recurring-title">
                      {currentRecurring ? 'Recurring Promise' : 'One-time Task'}
                    </span>
                    <span className="card-recurring-subtitle">
                      {currentRecurring 
                        ? 'This promise repeats every week' 
                        : 'This is a one-time task'}
                    </span>
                  </div>
                  <button
                    className={`card-recurring-toggle-button ${currentRecurring ? 'active' : ''}`}
                    onClick={handleRecurringToggle}
                    disabled={isUpdatingRecurring}
                  >
                    {isUpdatingRecurring ? '...' : (currentRecurring ? 'Make One-time' : 'Make Recurring')}
                  </button>
                </div>
                
                {/* Reminders section */}
                <div className="card-section card-reminders-section">
                  <div className="card-section-header">
                    <span>Reminders</span>
                    <button
                      className="card-reminders-add-button"
                      onClick={handleAddReminder}
                    >
                      + Add
                    </button>
                  </div>
                  
                  {isLoadingReminders ? (
                    <div className="card-empty-state">
                      Loading reminders...
                    </div>
                  ) : reminders.length === 0 ? (
                    <div className="card-empty-state">
                      No reminders set. Click "+ Add" to create one.
                    </div>
                  ) : (
                    reminders.map((reminder, index) => (
                      <div 
                        key={index}
                        className="card-reminder-item"
                      >
                        <select
                          className="card-reminder-weekday"
                          value={reminder.weekday}
                          onChange={(e) => handleUpdateReminder(index, 'weekday', parseInt(e.target.value))}
                        >
                          {WEEKDAY_NAMES.map((name, i) => (
                            <option key={i} value={i}>{name}</option>
                          ))}
                        </select>
                        <input
                          type="time"
                          className="card-reminder-time"
                          value={reminder.time}
                          onChange={(e) => handleUpdateReminder(index, 'time', e.target.value)}
                        />
                        <button
                          className={`card-reminder-toggle ${reminder.enabled ? 'enabled' : ''}`}
                          onClick={() => handleUpdateReminder(index, 'enabled', !reminder.enabled)}
                          title={reminder.enabled ? 'Disable' : 'Enable'}
                        >
                          {reminder.enabled ? 'On' : 'Off'}
                        </button>
                        <button
                          className="card-reminder-remove"
                          onClick={() => handleRemoveReminder(index)}
                          title="Remove"
                        >
                          Remove
                        </button>
                      </div>
                    ))
                  )}
                  
                  {reminders.length > 0 && (
                    <button
                      className="card-reminders-save-button"
                      onClick={handleSaveReminders}
                    >
                      Save Reminders
                    </button>
                  )}
                </div>
                
                {/* Save/Cancel buttons */}
                <div className="card-form-button-group">
                  <button
                    className="card-form-button-primary"
                    onClick={handleSavePromise}
                    disabled={isUpdatingPromise}
                  >
                    {isUpdatingPromise ? 'Saving...' : 'Save Changes'}
                  </button>
                  <button
                    className="card-form-button-secondary"
                    onClick={handleCancelEdit}
                    disabled={isUpdatingPromise}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              /* View mode - show notes and other info */
              <div className="card-edit-form">
                {/* Notes section - show all notes for the week */}
                {Object.keys(notesByDate).length > 0 && (
                  <div className="card-section card-notes-section">
                    <div className="card-section-header">
                      Notes for This Week
                    </div>
                    {weekDays.map((dateKey) => {
                      const dayNotes = notesByDate[dateKey] || [];
                      if (dayNotes.length === 0) return null;
                      
                      const date = new Date(dateKey);
                      const dayName = date.toLocaleDateString('en-US', { weekday: 'short' });
                      const dayNumber = date.getDate();
                      const month = date.toLocaleDateString('en-US', { month: 'short' });
                      
                      return (
                        <div 
                          key={dateKey}
                          className="card-notes-day-group"
                        >
                          <div className="card-notes-day-header">
                            {dayName}, {month} {dayNumber}
                          </div>
                          {dayNotes.map((note, noteIndex) => (
                            <div 
                              key={noteIndex}
                              className="card-notes-item"
                            >
                              {note}
                            </div>
                          ))}
                        </div>
                      );
                    })}
                  </div>
                )}
                
                {Object.keys(notesByDate).length === 0 && (
                  <div className="card-empty-state">
                    No notes for this week. Open Edit to modify this promise.
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      
      {!isBudget && (
        <div className="progress-row" aria-hidden="true">
          <div className="progress-track">
            <div 
              className="progress-fill" 
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}
      
      <div className="days-row" aria-hidden="true">
        {dayValues.map((value, index) => {
          const heightPct = Math.round((value / baseline) * 100);
          const dateKey = weekDays[index];
          const dayNotes = notesByDate[dateKey] || [];
          const hasNotes = dayNotes.length > 0;
          
          let title = isCountBased 
            ? `${DAY_LABELS[index]}: ${Math.round(value)}`
            : `${DAY_LABELS[index]}: ${value.toFixed(2)}h`;
          
          if (hasNotes) {
            title += '\n\nNotes:\n' + dayNotes.join('\n');
          }
          
          return (
            <div 
              key={index} 
              className="day-col"
              title={title}
            >
              <div 
                className="day-bar" 
                style={{ height: `${heightPct}%` }}
              />
              {hasNotes && (
                <div
                  className="card-day-indicator"
                  title={dayNotes.join('\n')}
                />
              )}
              <div className="day-label" dir="ltr">{DAY_LABELS[index]}</div>
            </div>
          );
        })}
      </div>
      
      <div className="card-actions">
        {isCountBased ? (
          <button
            className="card-log-button"
            onClick={() => setIsCheckinModalOpen(true)}
            title="Check in"
          >
            + Check In
          </button>
        ) : (
          <button
            className="card-log-button"
            onClick={() => setIsLogModalOpen(true)}
            title="Log time spent"
          >
            + Log Time
          </button>
        )}
        {isBudget && (
          <div className="budget-bar-container">
            <div className="budget-bar">
              <div 
                className={`budget-bar-fill ${achieved_value > target_value ? 'over-budget' : ''}`}
                style={{ 
                  width: `${Math.min((achieved_value / target_value) * 100, 100)}%`
                }}
              />
              <div className={`budget-bar-label ${achieved_value > target_value ? 'over-budget' : ''}`}>
                {isCountBased ? (
                  <>{Math.round(achieved_value)}/{Math.round(target_value)}</>
                ) : (
                  <>{achieved_value.toFixed(1)}h/{target_value.toFixed(1)}h</>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
      </article>
      
      <LogActionModal
        promiseId={id}
        promiseText={text}
        isOpen={isLogModalOpen}
        onClose={() => setIsLogModalOpen(false)}
        onSuccess={() => {
          if (onRefresh) {
            onRefresh();
          }
        }}
      />
      <CheckinModal
        promiseId={id}
        promiseText={text}
        isOpen={isCheckinModalOpen}
        onClose={() => setIsCheckinModalOpen(false)}
        onSuccess={() => {
          if (onRefresh) {
            onRefresh();
          }
        }}
      />
      <WeeklyNoteModal
        promiseId={id}
        promiseText={text}
        weekStart={weekDays[0]}
        isOpen={isWeeklyNoteModalOpen}
        onClose={() => setIsWeeklyNoteModalOpen(false)}
        onSuccess={() => {
          if (onRefresh) {
            onRefresh();
          }
        }}
      />
      
      {pendingVisibility && (
        <VisibilityConfirmModal
          isOpen={showVisibilityConfirm}
          currentVisibility={currentVisibility}
          newVisibility={pendingVisibility}
          onConfirm={handleVisibilityConfirm}
          onCancel={handleVisibilityCancel}
        />
      )}
    </>
  );
}
