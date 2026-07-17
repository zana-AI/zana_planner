import { useEffect, useState } from 'react';
import { CalendarPlus } from 'lucide-react';
import type { UpcomingPlanSession } from '../types';
import { formatPromiseText } from '../utils/activityFormat';
import { AddToCalendarSheet } from './sheets/AddToCalendarSheet';
import { apiClient } from '../api/client';

interface TodayAgendaProps {
  /** Opens the promise detail sheet for a session's promise. */
  onOpenPromise: (promiseId: string) => void;
  /** Change this value to trigger a refetch (e.g. after logging/scheduling). */
  refreshKey?: unknown;
}

const UPNEXT_LIMIT = 3;
const FETCH_DAYS = 7;

function toLocalDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function formatClock(isoStr: string | null): string {
  if (!isoStr) return '—';
  const dt = new Date(isoStr);
  if (Number.isNaN(dt.getTime())) return '—';
  return dt.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
}

function formatDayLabel(isoStr: string | null): string {
  if (!isoStr) return '';
  const dt = new Date(isoStr);
  if (Number.isNaN(dt.getTime())) return '';
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const day = new Date(dt);
  day.setHours(0, 0, 0, 0);
  if (day.getTime() === today.getTime() + 86400000) return 'Tomorrow';
  return dt.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}

function totalPlannedLabel(sessions: UpcomingPlanSession[]): string {
  const totalMin = sessions.reduce((acc, s) => acc + (s.planned_duration_min || 0), 0);
  if (totalMin <= 0) return `${sessions.length} planned`;
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  const dur = h > 0 ? (m > 0 ? `${h}h ${m}m` : `${h}h`) : `${m}m`;
  return `${sessions.length} planned · ${dur}`;
}

export function TodayAgenda({ onOpenPromise, refreshKey }: TodayAgendaProps) {
  const [sessions, setSessions] = useState<UpcomingPlanSession[]>([]);
  const [calendarSession, setCalendarSession] = useState<UpcomingPlanSession | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiClient.getUpcomingPlanSessions(FETCH_DAYS)
      .then(data => { if (!cancelled) setSessions(data); })
      .catch(() => { if (!cancelled) setSessions([]); });
    return () => { cancelled = true; };
  }, [refreshKey]);

  const todayKey = toLocalDateKey(new Date());
  const todaySessions = sessions.filter(
    s => s.planned_start && toLocalDateKey(new Date(s.planned_start)) === todayKey,
  );
  // Only surface future sessions when today is empty, so the section stays quiet.
  const upNext = todaySessions.length === 0
    ? sessions.filter(s => s.planned_start && toLocalDateKey(new Date(s.planned_start)) > todayKey).slice(0, UPNEXT_LIMIT)
    : [];

  const shown = todaySessions.length > 0 ? todaySessions : upNext;
  if (shown.length === 0) return null;

  const isToday = todaySessions.length > 0;

  const renderRow = (session: UpcomingPlanSession) => {
    const promiseLabel = formatPromiseText(session.promise_text || '');
    const title = (session.title || '').trim() || promiseLabel || 'Session';
    const notes = (session.notes || '').trim();
    const checklistTotal = session.checklist?.length || 0;
    const checklistDone = session.checklist?.filter(item => item.done).length || 0;

    const metaParts: string[] = [];
    if (promiseLabel && promiseLabel !== title) metaParts.push(promiseLabel);
    if (session.planned_duration_min) metaParts.push(`${session.planned_duration_min} min`);
    if (checklistTotal > 0) metaParts.push(`${checklistDone}/${checklistTotal} steps`);

    return (
      <div
        key={session.id}
        className="agenda-row"
        role="button"
        tabIndex={0}
        onClick={() => session.promise_id && onOpenPromise(session.promise_id)}
        onKeyDown={(e) => {
          if ((e.key === 'Enter' || e.key === ' ') && session.promise_id) {
            e.preventDefault();
            onOpenPromise(session.promise_id);
          }
        }}
      >
        <span className="agenda-time">
          {isToday ? formatClock(session.planned_start) : formatDayLabel(session.planned_start)}
        </span>
        <div className="agenda-info">
          <span className="agenda-title">{title}</span>
          {(metaParts.length > 0 || notes) && (
            <span className="agenda-meta">
              {metaParts.join(' · ')}
              {metaParts.length > 0 && notes ? ' — ' : ''}
              {notes}
            </span>
          )}
        </div>
        <button
          type="button"
          className="plan-session-btn plan-session-btn--cal agenda-cal-btn"
          onClick={(e) => { e.stopPropagation(); setCalendarSession(session); }}
          aria-label="Add to calendar"
        >
          <CalendarPlus size={14} />
        </button>
      </div>
    );
  };

  return (
    <>
      <div className="section-head">
        <h2>{isToday ? 'Today' : 'Up next'}</h2>
        <span className="meta">{isToday ? totalPlannedLabel(todaySessions) : `next ${upNext.length}`}</span>
      </div>
      <div className="agenda-list">
        {shown.map(renderRow)}
      </div>

      <AddToCalendarSheet
        open={calendarSession !== null}
        session={calendarSession}
        promiseText={formatPromiseText(calendarSession?.promise_text || '')}
        onClose={() => setCalendarSession(null)}
      />
    </>
  );
}
