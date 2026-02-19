export function formatRelativeActivity(lastActivityAtUtc?: string): string | null {
  if (!lastActivityAtUtc) return null;

  const lastActivityDate = new Date(lastActivityAtUtc);
  if (Number.isNaN(lastActivityDate.getTime())) return null;

  const now = Date.now();
  const diffMs = now - lastActivityDate.getTime();
  if (diffMs < 0) return 'recently';

  const dayMs = 24 * 60 * 60 * 1000;
  const dayDiff = Math.floor(diffMs / dayMs);

  if (dayDiff <= 0) return 'today';
  if (dayDiff === 1) return '1 day ago';
  if (dayDiff < 7) return `${dayDiff} days ago`;

  const weekDiff = Math.floor(dayDiff / 7);
  if (weekDiff === 1) return '1 week ago';
  if (weekDiff < 5) return `${weekDiff} weeks ago`;

  const monthDiff = Math.floor(dayDiff / 30);
  if (monthDiff === 1) return '1 month ago';
  if (monthDiff < 12) return `${monthDiff} months ago`;

  const yearDiff = Math.floor(dayDiff / 365);
  if (yearDiff <= 1) return '1 year ago';
  return `${yearDiff} years ago`;
}


export function buildActivitySummaryText(
  weeklyActivityCount?: number,
  lastActivityAtUtc?: string
): string {
  const weeklyCount = Number.isFinite(weeklyActivityCount as number) ? Math.max(0, Number(weeklyActivityCount)) : 0;

  if (weeklyCount > 0) {
    return `${weeklyCount} ${weeklyCount === 1 ? 'activity' : 'activities'} this week`;
  }

  const relative = formatRelativeActivity(lastActivityAtUtc);
  if (relative) {
    return `Last activity ${relative}`;
  }

  return 'No activity yet';
}
