import type { PublicUser, WeeklyReportData } from '../types';

function toLocalDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export function shouldUseLocalMockData(): boolean {
  return import.meta.env.DEV;
}

export function getMockWeeklyReport(refTime?: string): WeeklyReportData {
  const base = refTime ? new Date(refTime) : new Date();
  const day = base.getDay();
  const diff = base.getDate() - day + (day === 0 ? -6 : 1);
  const monday = new Date(base);
  monday.setDate(diff);
  monday.setHours(0, 0, 0, 0);

  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(monday);
    date.setDate(monday.getDate() + index);
    return toLocalDateKey(date);
  });

  return {
    week_start: days[0],
    week_end: days[6],
    total_promised: 12,
    total_spent: 7.25,
    promises: {
      writing: {
        text: 'Write the Xaana product note',
        hours_promised: 4,
        hours_spent: 2.5,
        target_value: 4,
        achieved_value: 2.5,
        metric_type: 'hours',
        template_kind: 'commitment',
        recurring: true,
        visibility: 'public',
        sessions: [
          { date: days[0], hours: 1.25, notes: ['Outlined the argument and tightened the intro.'] },
          { date: days[2], hours: 1.25, notes: ['Drafted the Mini App section.'] },
        ],
      },
      workout: {
        text: 'Move my body',
        hours_promised: 4,
        hours_spent: 3,
        target_value: 4,
        achieved_value: 3,
        metric_type: 'count',
        template_kind: 'commitment',
        recurring: true,
        visibility: 'public',
        sessions: [
          { date: days[0], hours: 0.5, count: 1 },
          { date: days[2], hours: 0.75, count: 1 },
          { date: days[4], hours: 0.75, count: 1 },
        ],
      },
      taxes: {
        text: 'Send accountant documents',
        hours_promised: 2,
        hours_spent: 1.75,
        target_value: 2,
        achieved_value: 1.75,
        metric_type: 'hours',
        template_kind: 'commitment',
        recurring: false,
        visibility: 'private',
        sessions: [
          { date: days[1], hours: 1 },
          { date: days[3], hours: 0.75 },
        ],
      },
      social_media: {
        text: 'Social media',
        hours_promised: 2,
        hours_spent: 1.25,
        target_value: 2,
        achieved_value: 1.25,
        metric_type: 'hours',
        template_kind: 'budget',
        recurring: true,
        visibility: 'private',
        sessions: [
          { date: days[1], hours: 0.5 },
          { date: days[4], hours: 0.75 },
        ],
      },
    },
  } as WeeklyReportData;
}

export function getMockCommunityUsers(): PublicUser[] {
  return [
    {
      user_id: 'mock-101',
      first_name: 'Nora',
      username: 'nora_keeps_promises',
      activity_count: 38,
      weekly_activity_count: 5,
      promise_count: 4,
      last_activity_at_utc: new Date(Date.now() - 1000 * 60 * 36).toISOString(),
    },
    {
      user_id: 'mock-102',
      first_name: 'Amir',
      username: 'amir_builds',
      activity_count: 22,
      weekly_activity_count: 3,
      promise_count: 3,
      last_activity_at_utc: new Date(Date.now() - 1000 * 60 * 140).toISOString(),
    },
  ];
}
