import { useMemo } from 'react';
import type { WeeklyReportData } from '../types';
import { PromiseCard } from './PromiseCard';

interface WeeklyReportProps {
  data: WeeklyReportData;
  onRefresh?: () => void; // Callback to refresh data
}

/**
 * Format date range for display
 */
function formatDateRange(startDate: string, endDate: string): string {
  const start = new Date(startDate);
  const end = new Date(endDate);
  
  const formatOptions: Intl.DateTimeFormatOptions = { 
    day: 'numeric', 
    month: 'short' 
  };
  
  return `${start.toLocaleDateString('en-US', formatOptions)} - ${end.toLocaleDateString('en-US', formatOptions)}`;
}

/**
 * Get all dates for the week (Monday to Sunday)
 */
function getWeekDays(weekStart: string): string[] {
  // weekStart is now a date-only string (YYYY-MM-DD) from backend
  // Parse it as a date at midnight local time to avoid timezone issues
  const [year, month, day] = weekStart.split('-').map(Number);
  const start = new Date(year, month - 1, day); // month is 0-indexed in JS
  const days: string[] = [];
  
  for (let i = 0; i < 7; i++) {
    const date = new Date(start);
    date.setDate(start.getDate() + i);
    // Format as YYYY-MM-DD in LOCAL timezone
    const dateYear = date.getFullYear();
    const dateMonth = String(date.getMonth() + 1).padStart(2, '0');
    const dateDay = String(date.getDate()).padStart(2, '0');
    days.push(`${dateYear}-${dateMonth}-${dateDay}`);
  }
  
  return days;
}

/**
 * WeeklyReport component - displays the full weekly report with header and promise cards
 */
export function WeeklyReport({ data, onRefresh }: WeeklyReportProps) {
  const { week_start, week_end, total_promised, total_spent, promises } = data;
  
  const dateRange = useMemo(
    () => formatDateRange(week_start, week_end),
    [week_start, week_end]
  );
  
  const weekDays = useMemo(
    () => getWeekDays(week_start),
    [week_start]
  );
  
  const promiseEntries = Object.entries(promises);
  const hasPromises = promiseEntries.length > 0;
  
  // Sort promises alphabetically by ID for consistent ordering
  const sortedPromises = useMemo(
    () => promiseEntries.sort((a, b) => a[0].localeCompare(b[0])),
    [promiseEntries]
  );
  
  return (
    <div className="weekly-report">
      {/* Header */}
      <header className="report-header">
        <div className="header-left">
          <h1 className="header-title" dir="auto">Weekly Report</h1>
          <div className="header-subtitle" dir="ltr">{dateRange}</div>
        </div>
        <div className="header-right">
          <div className="header-totals-label" dir="ltr">Totals</div>
          <div className="header-totals-value" dir="ltr">
            {total_spent.toFixed(1)}/{total_promised.toFixed(1)} h
          </div>
        </div>
      </header>
      
      {/* Overall Progress Bar */}
      {total_promised > 0 && (
        <div style={{ 
          marginBottom: '18px', 
          padding: '12px 18px',
          border: '1px solid rgba(232, 238, 252, 0.1)',
          borderRadius: '12px',
          background: 'rgba(15, 23, 48, 0.5)'
        }}>
          <div style={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center',
            marginBottom: '8px'
          }}>
            <span style={{ fontSize: '0.85rem', color: 'rgba(232, 238, 252, 0.72)' }}>Overall Progress</span>
            <span style={{ fontSize: '0.9rem', fontWeight: '700', color: 'var(--text)' }}>
              {Math.round((total_spent / total_promised) * 100)}%
            </span>
          </div>
          <div style={{ 
            height: '10px', 
            borderRadius: '999px', 
            background: 'rgba(232, 238, 252, 0.10)',
            overflow: 'hidden',
            border: '1px solid rgba(232, 238, 252, 0.06)'
          }}>
            <div style={{ 
              height: '100%',
              width: `${Math.min((total_spent / total_promised) * 100, 100)}%`,
              background: 'linear-gradient(90deg, var(--accent), var(--accent2))',
              borderRadius: '999px',
              transition: 'width 0.3s ease'
            }} />
          </div>
        </div>
      )}
      
      {/* Promise Cards or Empty State */}
      {hasPromises ? (
        <main className="promises-grid">
          {sortedPromises.map(([id, promiseData]) => (
            <PromiseCard
              key={id}
              id={id}
              data={promiseData}
              weekDays={weekDays}
              onRefresh={onRefresh}
            />
          ))}
        </main>
      ) : (
        <div className="empty-state">
          <h2 className="empty-title" dir="auto">No data available for this week</h2>
          <p className="empty-subtitle">
            Start tracking your promises in the Telegram bot to see your progress here.
          </p>
        </div>
      )}
    </div>
  );
}
