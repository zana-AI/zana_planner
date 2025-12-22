import type { PromiseData, SessionData } from '../types';

interface PromiseCardProps {
  id: string;
  data: PromiseData;
  weekDays: string[]; // Array of date strings for the week (ISO format)
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
export function PromiseCard({ id, data, weekDays }: PromiseCardProps) {
  const { text, hours_promised, hours_spent, sessions } = data;
  
  const progress = calculateProgress(hours_spent, hours_promised);
  const emoji = getStatusEmoji(progress);
  
  // Create a map of date -> hours for quick lookup
  const sessionsByDate: Record<string, number> = {};
  sessions.forEach((session: SessionData) => {
    sessionsByDate[session.date] = (sessionsByDate[session.date] || 0) + session.hours;
  });
  
  // Get hours for each day of the week
  const dayHours = weekDays.map(date => sessionsByDate[date] || 0);
  
  // Calculate max height for bars
  const maxDayHours = Math.max(...dayHours, 0.001);
  const dailyTarget = hours_promised > 0 ? hours_promised / 7 : 0;
  const baseline = Math.max(dailyTarget, maxDayHours, 0.25);
  
  return (
    <article className="promise-card">
      <div className="card-top">
        <div className="card-title" dir="auto">
          <span className="card-emoji">{emoji}</span>
          <span className="card-title-text">{text}</span>
        </div>
        <div className="card-meta">
          <span className="card-id" dir="ltr">#{id}</span>
          <span className="card-ratio" dir="ltr">
            {hours_spent.toFixed(1)}/{hours_promised.toFixed(1)} h
          </span>
          <span className="card-pct" dir="ltr">{progress}%</span>
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
        {dayHours.map((hours, index) => {
          const heightPct = Math.round((hours / baseline) * 100);
          return (
            <div 
              key={index} 
              className="day-col"
              title={`${DAY_LABELS[index]}: ${hours.toFixed(2)}h`}
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
    </article>
  );
}
