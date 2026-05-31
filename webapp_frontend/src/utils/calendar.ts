// Calendar helpers for scheduled sessions.
//
// Two low-friction "add to calendar" paths that work from a Telegram Mini App:
//   - a Google Calendar template URL (opens the GCal app/web), and
//   - a generated .ics file (opens the native add-to-calendar sheet on phones).
//
// All times are emitted in UTC; calendar apps localize them for the user.
import type { PlanSession } from '../types';

interface CalendarEvent {
  title: string;
  start: Date;
  durationMin: number;
  description: string;
}

const DEFAULT_DURATION_MIN = 30;

/** Format a Date as a UTC stamp: YYYYMMDDTHHMMSSZ (RFC 5545 / Google format). */
function utcStamp(date: Date): string {
  return date.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
}

/** Build a calendar event from a plan session, falling back sensibly. */
function eventFromSession(session: PlanSession, promiseText: string): CalendarEvent | null {
  if (!session.planned_start) return null;
  const start = new Date(session.planned_start);
  if (Number.isNaN(start.getTime())) return null;
  const title = (session.title || promiseText || 'Focus session').trim();
  const durationMin = session.planned_duration_min && session.planned_duration_min > 0
    ? session.planned_duration_min
    : DEFAULT_DURATION_MIN;
  const descParts = [promiseText ? `Xaana promise: ${promiseText}` : '', session.notes || ''];
  return { title, start, durationMin, description: descParts.filter(Boolean).join('\n') };
}

/** Google Calendar "template" URL — opens a pre-filled event in Google Calendar. */
export function googleCalendarUrl(session: PlanSession, promiseText: string): string | null {
  const ev = eventFromSession(session, promiseText);
  if (!ev) return null;
  const end = new Date(ev.start.getTime() + ev.durationMin * 60_000);
  const params = new URLSearchParams({
    action: 'TEMPLATE',
    text: ev.title,
    dates: `${utcStamp(ev.start)}/${utcStamp(end)}`,
    details: ev.description,
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

/** Escape a text value per RFC 5545. */
function icsEscape(value: string): string {
  return (value || '')
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\r?\n/g, '\\n');
}

/** Build an .ics (VCALENDAR) string for the session. */
export function buildIcs(session: PlanSession, promiseText: string): string | null {
  const ev = eventFromSession(session, promiseText);
  if (!ev) return null;
  const end = new Date(ev.start.getTime() + ev.durationMin * 60_000);
  const dtstamp = utcStamp(new Date());
  const uid = `${dtstamp}-${session.id}@xaana.club`;
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Xaana//Planner//EN',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    'BEGIN:VEVENT',
    `UID:${uid}`,
    `DTSTAMP:${dtstamp}`,
    `DTSTART:${utcStamp(ev.start)}`,
    `DTEND:${utcStamp(end)}`,
    `SUMMARY:${icsEscape(ev.title)}`,
  ];
  if (ev.description) lines.push(`DESCRIPTION:${icsEscape(ev.description)}`);
  if (session.reminder_enabled) {
    lines.push(
      'BEGIN:VALARM',
      'ACTION:DISPLAY',
      `DESCRIPTION:${icsEscape(ev.title)}`,
      `TRIGGER:-PT${Math.max(0, session.reminder_offset_min ?? 10)}M`,
      'END:VALARM',
    );
  }
  lines.push('END:VEVENT', 'END:VCALENDAR');
  return lines.join('\r\n') + '\r\n';
}

/** Open the Google Calendar event page (external browser when inside Telegram). */
export function openGoogleCalendar(session: PlanSession, promiseText: string): void {
  const url = googleCalendarUrl(session, promiseText);
  if (!url) return;
  const tg = window.Telegram?.WebApp;
  if (tg?.openLink) tg.openLink(url);
  else window.open(url, '_blank', 'noopener');
}

/** Trigger a download/open of the .ics so the OS offers "add to calendar". */
export function downloadIcs(session: PlanSession, promiseText: string): void {
  const ics = buildIcs(session, promiseText);
  if (!ics) return;
  const blob = new Blob([ics], { type: 'text/calendar;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'xaana-session.ics';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Revoke on the next tick so the click has time to start the download.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
