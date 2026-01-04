import { useState, useEffect } from 'react';
import type { PromiseData, SessionData } from '../types';
import { apiClient } from '../api/client';
import { LogActionModal } from './LogActionModal';
import { CheckinModal } from './CheckinModal';
import { WeeklyNoteModal } from './WeeklyNoteModal';
import { VisibilityConfirmModal } from './VisibilityConfirmModal';

interface PromiseCardProps {
  id: string;
  data: PromiseData;
  weekDays: string[]; // Array of date strings for the week (ISO format)
  onRefresh?: () => void; // Callback to refresh data after changes
}

const DAY_LABELS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

/**
 * Get status emoji based on progress percentage
 */
function getStatusEmoji(progress: number): string {
  if (progress >= 90) return '✅';
  if (progress >= 60) return '🟡';
  if (progress >= 30) return '🟠';
  return '🔴';
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
    metric_type = 'hours',
    target_value = hours_promised,
    target_direction = 'at_least',
    template_kind = 'commitment',
    achieved_value = hours_spent,
  } = data;
  const [currentVisibility, setCurrentVisibility] = useState<'private' | 'public'>(
    (visibility === 'public' ? 'public' : 'private') as 'private' | 'public'
  );
  const [isUpdatingVisibility, setIsUpdatingVisibility] = useState(false);
  const [isLogModalOpen, setIsLogModalOpen] = useState(false);
  const [isCheckinModalOpen, setIsCheckinModalOpen] = useState(false);
  const [isWeeklyNoteModalOpen, setIsWeeklyNoteModalOpen] = useState(false);
  const [showVisibilityConfirm, setShowVisibilityConfirm] = useState(false);
  const [pendingVisibility, setPendingVisibility] = useState<'private' | 'public' | null>(null);
  
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
  
  const emoji = getStatusEmoji(progress);
  
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
  sessions.forEach((session: SessionData) => {
    const dateKey = typeof session.date === 'string' ? session.date : session.date;
    if (isCountBased) {
      // For count-based, sessions have 'count' field
      const count = (session as any).count || 0;
      sessionsByDate[dateKey] = (sessionsByDate[dateKey] || 0) + count;
    } else {
      sessionsByDate[dateKey] = (sessionsByDate[dateKey] || 0) + (session.hours || 0);
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
        className="promise-card"
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
          <button
            className={`card-snooze-button ${isSnoozeActive ? 'active' : ''}`}
            style={{
              opacity: snoozeButtonOpacity,
              transform: `translateY(-50%) scale(${snoozeButtonScale})`,
            }}
            onClick={handleSnoozeButtonClick}
            disabled={!isSnoozeActive}
          >
            {isSnoozeActive ? 'Snooze' : 'Swipe to snooze'}
          </button>
        )}
        
        <div className="card-top">
          <div className="card-title" dir="auto">
            <span className="card-emoji">{emoji}</span>
            <span className="card-title-text">{text}</span>
            <button
              className="card-visibility-toggle"
              onClick={handleVisibilityToggle}
              disabled={isUpdatingVisibility}
              title={currentVisibility === 'private' ? 'Make public' : 'Make private'}
            >
              {currentVisibility === 'private' ? '🔒' : '🌐'}
            </button>
          </div>
          <div className="card-meta">
            <span className="card-id" dir="ltr">#{id}</span>
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
      
      <div className="progress-row" aria-hidden="true">
        <div className="progress-track">
          <div 
            className="progress-fill" 
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
      
      <div className="days-row" aria-hidden="true">
        {dayValues.map((value, index) => {
          const heightPct = Math.round((value / baseline) * 100);
          const title = isCountBased 
            ? `${DAY_LABELS[index]}: ${Math.round(value)}`
            : `${DAY_LABELS[index]}: ${value.toFixed(2)}h`;
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
        <button
          className="card-log-button card-log-button-secondary"
          onClick={() => setIsWeeklyNoteModalOpen(true)}
          title="Add weekly note"
        >
          📝 Note
        </button>
        {isBudget && (
          <div className="budget-bar-container" style={{ marginTop: '0.5rem', width: '100%' }}>
            <div className="budget-bar-label" style={{ fontSize: '0.85rem', marginBottom: '0.25rem' }}>
              {isCountBased ? (
                <>{Math.round(achieved_value)}/{Math.round(target_value)}</>
              ) : (
                <>{achieved_value.toFixed(1)}h / {target_value.toFixed(1)}h</>
              )}
            </div>
            <div className="budget-bar" style={{ height: '8px', backgroundColor: '#2a2a3a', borderRadius: '4px', overflow: 'hidden' }}>
              <div 
                className={`budget-bar-fill ${achieved_value > target_value ? 'over-budget' : ''}`}
                style={{ 
                  height: '100%',
                  width: `${Math.min((achieved_value / target_value) * 100, 100)}%`,
                  backgroundColor: achieved_value > target_value ? '#ff4444' : '#4CAF50',
                  transition: 'width 0.3s ease'
                }}
              />
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
