import type { TFunction } from 'i18next';

export function formatRelativeActivity(lastActivityAtUtc?: string, t?: TFunction): string | null {
  const tr: TFunction = t ?? (((k: string) => k) as unknown as TFunction);
  if (!lastActivityAtUtc) return null;

  const lastActivityDate = new Date(lastActivityAtUtc);
  if (Number.isNaN(lastActivityDate.getTime())) return null;

  const now = Date.now();
  const diffMs = now - lastActivityDate.getTime();
  if (diffMs < 0) return tr('activity.recently');

  const dayMs = 24 * 60 * 60 * 1000;
  const dayDiff = Math.floor(diffMs / dayMs);

  if (dayDiff <= 0) return tr('activity.today');
  if (dayDiff === 1) return tr('activity.daysAgo', { count: 1 });
  if (dayDiff < 7) return tr('activity.daysAgo', { count: dayDiff });

  const weekDiff = Math.floor(dayDiff / 7);
  if (weekDiff === 1) return tr('activity.weeksAgo', { count: 1 });
  if (weekDiff < 5) return tr('activity.weeksAgo', { count: weekDiff });

  const monthDiff = Math.floor(dayDiff / 30);
  if (monthDiff === 1) return tr('activity.monthsAgo', { count: 1 });
  if (monthDiff < 12) return tr('activity.monthsAgo', { count: monthDiff });

  const yearDiff = Math.floor(dayDiff / 365);
  if (yearDiff <= 1) return tr('activity.yearsAgo', { count: 1 });
  return tr('activity.yearsAgo', { count: yearDiff });
}


export function buildActivitySummaryText(
  weeklyActivityCount?: number,
  lastActivityAtUtc?: string,
  t?: TFunction
): string {
  const tr: TFunction = t ?? (((k: string) => k) as unknown as TFunction);
  const weeklyCount = Number.isFinite(weeklyActivityCount as number) ? Math.max(0, Number(weeklyActivityCount)) : 0;

  if (weeklyCount > 0) {
    return tr('activity.thisWeek', { count: weeklyCount });
  }

  const relative = formatRelativeActivity(lastActivityAtUtc, t);
  if (relative) {
    return tr('activity.lastActivity', { when: relative });
  }

  return tr('activity.noActivity');
}
