import { useState } from 'react';
import type { PublicPromiseBadge as PublicPromiseBadgeType } from '../types';
import { PromiseLogsModal } from './PromiseLogsModal';
import { Badge } from './ui/Badge';

interface PromiseBadgeProps {
  badge: PublicPromiseBadgeType;
  compact?: boolean;
  showLogsOnClick?: boolean;
}

function getStreakText(streak: number): string {
  if (streak < 0) return `${Math.abs(streak)}d ago`;
  if (streak === 0) return 'New';
  return `${streak}d streak`;
}

function getProgressVariant(progress: number): 'progress' | 'warning' | 'danger' {
  if (progress >= 70) return 'progress';
  if (progress >= 40) return 'warning';
  return 'danger';
}

export function PromiseBadge({ badge, compact = false, showLogsOnClick = true }: PromiseBadgeProps) {
  const { text, streak, progress_percentage, weekly_hours, hours_promised } = badge;
  const [isLogsModalOpen, setIsLogsModalOpen] = useState(false);

  const displayText = text.length > (compact ? 26 : 44) ? `${text.substring(0, compact ? 23 : 41)}...` : text;
  const progressValue = Math.round(progress_percentage);

  const handleClick = () => {
    if (showLogsOnClick) {
      setIsLogsModalOpen(true);
    }
  };

  if (compact) {
    return (
      <>
        <div className={`promise-badge compact ${showLogsOnClick ? 'clickable' : ''}`} title={text} onClick={showLogsOnClick ? handleClick : undefined}>
          <span className="promise-badge-text">{displayText}</span>
          <span className="promise-badge-stats">
            <Badge variant="neutral">{getStreakText(streak)}</Badge>
            <Badge variant={getProgressVariant(progressValue)}>{progressValue}%</Badge>
          </span>
        </div>
        {showLogsOnClick ? (
          <PromiseLogsModal promiseId={badge.promise_id} promiseText={text} isOpen={isLogsModalOpen} onClose={() => setIsLogsModalOpen(false)} />
        ) : null}
      </>
    );
  }

  return (
    <>
      <div className={`promise-badge ${showLogsOnClick ? 'clickable' : ''}`} title={text} onClick={showLogsOnClick ? handleClick : undefined}>
        <div className="promise-badge-header">
          <span className="promise-badge-text">{displayText}</span>
          <Badge variant={getProgressVariant(progressValue)}>{progressValue}%</Badge>
        </div>
        <div className="promise-badge-stats">
          <Badge variant="neutral">{getStreakText(streak)}</Badge>
          <span className="promise-badge-hours">
            {weekly_hours.toFixed(1)}/{hours_promised.toFixed(1)}h
          </span>
        </div>
        <div className="promise-badge-progress-bar">
          <div className="promise-badge-progress-fill" style={{ width: `${Math.min(100, progress_percentage)}%` }} />
        </div>
      </div>
      {showLogsOnClick ? (
        <PromiseLogsModal promiseId={badge.promise_id} promiseText={text} isOpen={isLogsModalOpen} onClose={() => setIsLogsModalOpen(false)} />
      ) : null}
    </>
  );
}
