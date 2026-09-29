export type PromisePaceStatus = {
  key: 'onTrack' | 'behind' | 'atRisk';
  cls: 'good' | 'warn' | 'bad';
};

function localDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

/** Pace is measured against completed days; today's work is still available. */
export function expectedWeekFraction(weekDays: string[], today = new Date()): number {
  if (weekDays.length === 0) return 0;
  const todayKey = localDateKey(today);
  const todayIndex = weekDays.indexOf(todayKey);
  if (todayIndex >= 0) return todayIndex / weekDays.length;
  return todayKey < weekDays[0] ? 0 : 1;
}

export function getPromisePaceStatus(
  achieved: number,
  target: number,
  weekDays: string[],
  today = new Date(),
): PromisePaceStatus {
  if (target <= 0) return { key: 'onTrack', cls: 'good' };
  const progress = Math.max(0, achieved) / target;
  const expected = expectedWeekFraction(weekDays, today);
  // Compare raw fractions. Rounding 1/7 to 14% would incorrectly mark it
  // below a 14.2857% Tuesday threshold.
  if (progress + 1e-9 >= expected) return { key: 'onTrack', cls: 'good' };
  if (progress + 1e-9 >= expected * 0.5) return { key: 'behind', cls: 'warn' };
  return { key: 'atRisk', cls: 'bad' };
}
