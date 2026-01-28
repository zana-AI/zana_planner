import { useState } from 'react';
import type { PublicPromiseBadge as PublicPromiseBadgeType } from '../types';
import { PromiseLogsModal } from './PromiseLogsModal';

interface PromiseBadgeProps {
  badge: PublicPromiseBadgeType;
  compact?: boolean;
  showLogsOnClick?: boolean;
}

/**
 * Get streak emoji and text
 */
function getStreakDisplay(streak: number): { emoji: string; text: string } {
  if (streak < 0) {
    return { emoji: '⏰', text: `${Math.abs(streak)}d ago` };
  } else if (streak === 0) {
    return { emoji: '🆕', text: 'New' };
  } else {
    return { emoji: '🔥', text: `${streak}d` };
  }
}

/**
 * Get progress emoji based on percentage
 */
function getProgressEmoji(progress: number): string {
  if (progress >= 90) return '✅';
  if (progress >= 60) return '🟡';
  if (progress >= 30) return '🟠';
  return '🔴';
}

/**
 * PromiseBadge component - displays a compact promise badge with stats
 */
export function PromiseBadge({ badge, compact = false, showLogsOnClick = true }: PromiseBadgeProps) {
  const { text, streak, progress_percentage, weekly_hours, hours_promised } = badge;
  const streakDisplay = getStreakDisplay(streak);
  const progressEmoji = getProgressEmoji(progress_percentage);
  const [isLogsModalOpen, setIsLogsModalOpen] = useState(false);
  
  // Truncate text if too long (more aggressive on mobile)
  const displayText = text.length > (compact ? 20 : 40) 
    ? text.substring(0, (compact ? 17 : 37)) + '...' 
    : text;
  
  const handleClick = () => {
    if (showLogsOnClick) {
      setIsLogsModalOpen(true);
    }
  };
  
  if (compact) {
    return (
      <>
        <div 
          className={`promise-badge compact ${showLogsOnClick ? 'clickable' : ''}`} 
          title={text}
          onClick={showLogsOnClick ? handleClick : undefined}
        >
          <span className="promise-badge-text">{displayText}</span>
          <span className="promise-badge-stats">
            <span className="promise-badge-streak">{streakDisplay.emoji} {streakDisplay.text}</span>
            <span className="promise-badge-progress">{progressEmoji} {Math.round(progress_percentage)}%</span>
          </span>
        </div>
        {showLogsOnClick && (
          <PromiseLogsModal
            promiseId={badge.promise_id}
            promiseText={text}
            isOpen={isLogsModalOpen}
            onClose={() => setIsLogsModalOpen(false)}
          />
        )}
      </>
    );
  }
  
  return (
    <>
      <div 
        className={`promise-badge ${showLogsOnClick ? 'clickable' : ''}`} 
        title={text}
        onClick={showLogsOnClick ? handleClick : undefined}
      >
        <div className="promise-badge-header">
          <span className="promise-badge-text">{displayText}</span>
          <span className="promise-badge-progress-emoji">{progressEmoji}</span>
        </div>
        <div className="promise-badge-stats">
          <span className="promise-badge-streak">
            {streakDisplay.emoji} {streakDisplay.text}
          </span>
          <span className="promise-badge-hours">
            {weekly_hours.toFixed(1)}/{hours_promised.toFixed(1)}h
          </span>
          <span className="promise-badge-percentage">
            {Math.round(progress_percentage)}%
          </span>
        </div>
        <div className="promise-badge-progress-bar">
          <div 
            className="promise-badge-progress-fill"
            style={{ width: `${Math.min(100, progress_percentage)}%` }}
          />
        </div>
      </div>
      {showLogsOnClick && (
        <PromiseLogsModal
          promiseId={badge.promise_id}
          promiseText={text}
          isOpen={isLogsModalOpen}
          onClose={() => setIsLogsModalOpen(false)}
        />
      )}
    </>
  );
}
