import { useMemo } from 'react';
import type { WeeklyReportData } from '../types';
import { PromiseCard } from './PromiseCard';

interface WeeklyReportProps {
  data: WeeklyReportData;
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
  const start = new Date(weekStart);
  const days: string[] = [];
  
  for (let i = 0; i < 7; i++) {
    const date = new Date(start);
    date.setDate(start.getDate() + i);
    // Format as YYYY-MM-DD
    days.push(date.toISOString().split('T')[0]);
  }
  
  return days;
}

/**
 * WeeklyReport component - displays the full weekly report with header and promise cards
 */
export function WeeklyReport({ data }: WeeklyReportProps) {
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
      
      {/* Promise Cards or Empty State */}
      {hasPromises ? (
        <main className="promises-grid">
          {sortedPromises.map(([id, promiseData]) => (
            <PromiseCard
              key={id}
              id={id}
              data={promiseData}
              weekDays={weekDays}
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
