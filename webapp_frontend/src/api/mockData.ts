import type { ClubSummary, PublicActivityItem, PublicUser, WeeklyReportData } from '../types';

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
  const olderEndDate = new Date(monday);
  olderEndDate.setDate(monday.getDate() - 3);

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
      spanish: {
        text: 'Practice Spanish',
        hours_promised: 2,
        hours_spent: 1,
        target_value: 2,
        achieved_value: 1,
        metric_type: 'hours',
        template_kind: 'commitment',
        recurring: true,
        visibility: 'private',
        end_date: toLocalDateKey(olderEndDate),
        sessions: [],
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

export function getMockPublicActivity(): PublicActivityItem[] {
  const users = getMockCommunityUsers();
  const now = Date.now();
  return [
    {
      activity_id: 'mock-activity-1',
      action_type: 'club_checkin',
      action_label: 'checked in for Morning Run Club',
      duration_minutes: 32,
      timestamp_utc: new Date(now - 1000 * 60 * 28).toISOString(),
      promise_id: 'promise-morning-run',
      promise_text: 'Run at least 3 km before work',
      actor: users[0],
    },
    {
      activity_id: 'mock-activity-2',
      action_type: 'focus',
      action_label: 'finished a deep work block',
      duration_minutes: 90,
      timestamp_utc: new Date(now - 1000 * 60 * 74).toISOString(),
      promise_id: 'promise-deep-work',
      promise_text: 'Complete one 90-minute focused work block',
      actor: users[1],
    },
  ];
}

export function getMockClubs(): ClubSummary[] {
  return [
    {
      club_id: 'club-morning-run',
      name: 'Morning Run Club',
      visibility: 'private',
      role: 'owner',
      member_count: 5,
      members: [
        { user_id: 'mock-101', first_name: 'Nora', username: 'nora_keeps_promises' },
        { user_id: 'mock-102', first_name: 'Amir', username: 'amir_builds' },
        { user_id: 'mock-103', first_name: 'Leila', username: 'leila_moves' },
        { user_id: 'mock-104', first_name: 'Jon', username: 'jon_runs' },
      ],
      telegram_status: 'connected',
      telegram_invite_link: 'https://t.me/example_morning_run_club',
      promise_id: 'promise-morning-run',
      promise_uuid: 'promise-morning-run',
      promise_text: 'Run at least 3 km before work',
      target_count_per_week: 4,
      reminder_time: '07:15',
      language: 'en',
      description: 'A small accountability group for weekday morning runs.',
      club_goal: 'Build a durable running habit without turning it into a race.',
      vibe: 'Supportive, practical, low-drama.',
      checkin_what_counts: 'A run, jog, or walk-run of 3 km or more counts.',
    },
    {
      club_id: 'club-deep-work',
      name: 'Deep Work Sprint',
      visibility: 'public',
      role: 'member',
      member_count: 8,
      members: [
        { user_id: 'mock-105', first_name: 'Maya', username: 'maya_focus' },
        { user_id: 'mock-106', first_name: 'Theo', username: 'theo_codes' },
        { user_id: 'mock-107', first_name: 'Sara', username: 'sara_writes' },
      ],
      telegram_status: 'ready',
      telegram_invite_link: 'https://t.me/example_deep_work_sprint',
      promise_id: 'promise-deep-work',
      promise_uuid: 'promise-deep-work',
      promise_text: 'Complete one 90-minute focused work block',
      target_count_per_week: 5,
      reminder_time: '09:00',
      language: 'en',
      description: 'A weekday focus group for makers, students, and founders.',
      club_goal: 'Make focused work visible and easier to repeat.',
      vibe: 'Quiet, serious, kind.',
      checkin_what_counts: 'A distraction-free 90-minute block with a clear outcome.',
    },
    {
      club_id: 'club-language-table',
      name: 'Language Table',
      visibility: 'private',
      role: 'owner',
      member_count: 3,
      members: [
        { user_id: 'mock-108', first_name: 'Ana', username: 'ana_speaks' },
        { user_id: 'mock-109', first_name: 'Rami', username: 'rami_words' },
        { user_id: 'mock-110', first_name: 'Claire', username: 'claire_fr' },
      ],
      telegram_status: 'pending_admin_setup',
      promise_id: 'promise-language-table',
      promise_uuid: 'promise-language-table',
      promise_text: 'Practice a target language for 20 minutes',
      target_count_per_week: 3,
      reminder_time: '20:30',
      language: 'fr',
      description: 'Friends practicing languages with lightweight check-ins.',
      club_goal: 'Keep daily language practice social and forgiving.',
      vibe: 'Casual and conversational.',
      checkin_what_counts: 'Speaking, listening, reading, or writing practice for 20 minutes.',
    },
  ];
}
