import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CalendarPlus, Clock, Pencil, Timer, Trash2, Check, Users } from 'lucide-react';
import type { PromiseData, PlanSession } from '../../types';
import { formatPromiseText } from '../../utils/activityFormat';
import { Badge } from '../ui/Badge';
import { BottomSheet } from '../ui/BottomSheet';
import { Button } from '../ui/Button';
import { LogActionModal } from '../LogActionModal';
import { ScheduleSheet } from './ScheduleSheet';
import { AddToCalendarSheet } from './AddToCalendarSheet';
import { apiClient } from '../../api/client';

interface PromiseDetailSheetProps {
  open: boolean;
  promiseId: string;
  data: PromiseData;
  weekDays: string[];
  onClose: () => void;
  onLogTime: () => void;
  onCheckin: () => void;
  onSchedule: () => void;
  onFocus: () => void;
  onEdit: () => void;
  /** Called after a planned session is logged-as-done, so the parent can
   *  refetch the weekly report and refresh the badge/grids. */
  onLogged?: () => void;
}

function toLocalDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function weekExpectedFraction(weekDays: string[]): number {
  const todayKey = toLocalDateKey(new Date());
  const idx = weekDays.indexOf(todayKey);
  return idx >= 0 ? (idx + 1) / 7 : 1.0;
}

// Use raw (unrounded) progress so that e.g. 1 check-in on Monday (14.28%)
// is not marked behind due to integer rounding against expected 14.28%.
function getStatusClass(rawProgress: number, expectedFraction: number): 'good' | 'warn' | 'bad' | '' {
  const expected = expectedFraction * 100;
  if (rawProgress >= expected) return 'good';
  if (rawProgress >= expected * 0.5) return 'warn';
  if (rawProgress > 0) return 'bad';
  return '';
}

function formatSessionTime(isoStr: string | null): string {
  if (!isoStr) return 'No time set';
  const dt = new Date(isoStr);
  if (Number.isNaN(dt.getTime())) return 'No time set';
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  const dtDay = new Date(dt);
  dtDay.setHours(0, 0, 0, 0);
  const time = dt.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
  if (dtDay.getTime() === today.getTime()) return `Today · ${time}`;
  if (dtDay.getTime() === tomorrow.getTime()) return `Tomorrow · ${time}`;
  return dt.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }) + ` · ${time}`;
}

type RecentLog = { datetime: string; date: string; time_spent: number; time_str: string; notes: string | null };

const RECENT_LOGS_LIMIT = 3;

// Format a YYYY-MM-DD log date as Today / Yesterday / "May 31".
function formatLogDate(dateStr: string): string {
  const [y, m, d] = (dateStr || '').split('-').map(Number);
  if (!y || !m || !d) return dateStr || '';
  const dt = new Date(y, m - 1, d);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diffDays = Math.round((today.getTime() - dt.getTime()) / 86400000);
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export function PromiseDetailSheet({
  open,
  promiseId,
  data,
  weekDays,
  onClose,
  onLogTime,
  onCheckin,
  onSchedule,
  onFocus,
  onEdit,
  onLogged,
}: PromiseDetailSheetProps) {
  const navigate = useNavigate();
  const {
    text,
    hours_promised,
    hours_spent,
    sessions = [],
    metric_type = 'hours',
    target_value = hours_promised,
    achieved_value = hours_spent,
    recurring = true,
    visibility,
  } = data;

  const isCountBased = metric_type === 'count';
  const isClubPromise = visibility === 'clubs';
  const target = target_value || hours_promised || 1;
  const achieved = achieved_value ?? hours_spent ?? 0;
  const rawProgress = target > 0 ? Math.min((achieved / target) * 100, 100) : 0;
  const progress = Math.round(rawProgress);
  const expectedFraction = weekExpectedFraction(weekDays);
  // Only show weekly status for promises with a real weekly target:
  // non-recurring (trip/project) and zero-target promises have no meaningful pace.
  const hasWeeklyTarget = isCountBased ? target > 0 : recurring && (hours_promised ?? 0) > 0;
  const statusClass = hasWeeklyTarget ? getStatusClass(rawProgress, expectedFraction) : null;
  const statusLabel = statusClass === 'good' ? 'On track' : statusClass === 'warn' ? 'Behind' : statusClass === 'bad' ? 'At risk' : '';

  const [planSessions, setPlanSessions] = useState<PlanSession[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  // Session being logged-as-done (opens LogActionModal pre-filled with its data)
  const [logDoneSessionId, setLogDoneSessionId] = useState<number | null>(null);
  // Session being edited (opens ScheduleSheet in edit mode) / added to calendar
  const [editSession, setEditSession] = useState<PlanSession | null>(null);
  const [calendarSession, setCalendarSession] = useState<PlanSession | null>(null);
  // A few recent activity logs (what was actually done on this promise) shown below the
  // upcoming sessions, so the sheet reads forward-first: what's planned next, then recently done.
  const [recentLogs, setRecentLogs] = useState<RecentLog[]>([]);

  const reloadSessions = useCallback(() => {
    apiClient.getPlanSessions(promiseId)
      .then(setPlanSessions)
      .catch(() => {});
  }, [promiseId]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setSessionsLoading(true);
    apiClient.getPlanSessions(promiseId)
      .then(data => { if (!cancelled) setPlanSessions(data); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setSessionsLoading(false); });
    apiClient.getPromiseLogs(promiseId, RECENT_LOGS_LIMIT)
      .then(res => { if (!cancelled) setRecentLogs(res.logs); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [open, promiseId]);

  // Planned sessions, ordered chronologically (soonest first). Sessions with no
  // time set sink to the bottom rather than jumping to the top.
  const upcomingSessions = planSessions
    .filter(s => s.status === 'planned')
    .sort((a, b) => {
      const ta = a.planned_start ? new Date(a.planned_start).getTime() : Infinity;
      const tb = b.planned_start ? new Date(b.planned_start).getTime() : Infinity;
      return ta - tb;
    });

  // Pre-fill values for LogActionModal from the session being marked done
  const doneSession = logDoneSessionId !== null
    ? planSessions.find(s => s.id === logDoneSessionId) ?? null
    : null;

  const doneSessionPrefill = doneSession ? (() => {
    const durationHours = doneSession.planned_duration_min
      ? (doneSession.planned_duration_min / 60).toFixed(2).replace(/\.?0+$/, '')
      : '';
    const isoStart = doneSession.planned_start;
    let prefillDate = '';
    let prefillTime = '';
    if (isoStart) {
      const dt = new Date(isoStart);
      if (!Number.isNaN(dt.getTime())) {
        prefillDate = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
        prefillTime = `${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`;
      }
    }
    // The session title belongs in notes, not appended to the promise title.
    const rawTitle = (doneSession.title ?? '').trim();
    const titlePart = rawTitle && !['planned session', 'session'].includes(rawTitle.toLowerCase()) ? rawTitle : '';
    const notesValue = [titlePart, (doneSession.notes ?? '').trim()].filter(Boolean).join('\n');
    return { hours: durationHours, date: prefillDate, time: prefillTime, notes: notesValue };
  })() : null;

  const handleLogDoneSuccess = async () => {
    if (logDoneSessionId === null) return;
    try {
      await apiClient.updatePlanSessionStatus(logDoneSessionId, 'done');
      setPlanSessions(prev => prev.map(s => s.id === logDoneSessionId ? { ...s, status: 'done' as const } : s));
    } catch {}
    setLogDoneSessionId(null);
    // Tell the parent to refetch the weekly report so the badge/grids
    // reflect the freshly logged time.
    onLogged?.();
  };

  const handleGoToClub = async () => {
    try {
      const { clubs } = await apiClient.getMyClubs();
      const club = clubs.find(c => c.promise_id === promiseId || c.promise_uuid === promiseId);
      if (club) { onClose(); navigate(`/community?club=${club.club_id}`); }
    } catch {}
  };

  const handleDelete = async (sessionId: number) => {
    try {
      await apiClient.deletePlanSession(sessionId);
      setPlanSessions(prev => prev.filter(s => s.id !== sessionId));
    } catch {}
  };

  const dayValues = useMemo(() => {
    const sessionsByDate: Record<string, number> = {};
    sessions.forEach((session) => {
      const dateKey = typeof session.date === 'string' ? session.date : String(session.date);
      if (isCountBased) {
        const count = (session as { count?: number }).count || 0;
        sessionsByDate[dateKey] = (sessionsByDate[dateKey] || 0) + count;
      } else {
        sessionsByDate[dateKey] = (sessionsByDate[dateKey] || 0) + (session.hours || 0);
      }
    });
    return weekDays.map((date) => sessionsByDate[date] || 0);
  }, [isCountBased, sessions, weekDays]);

  const maxDay = Math.max(...dayValues, 0.001);

  return (
    <BottomSheet
      open={open}
      onClose={onClose}
      title={formatPromiseText(text)}
      subtitle={`Promise #${promiseId}`}
      headerActions={(
        <>
          {isClubPromise && (
            <button type="button" className="btn btn-ghost btn-sm sheet-icon-action" onClick={handleGoToClub} aria-label="Go to club">
              <Users size={18} aria-hidden />
            </button>
          )}
          <button type="button" className="btn btn-ghost btn-sm sheet-icon-action" onClick={onFocus} aria-label="Start focus">
            <Timer size={18} aria-hidden />
          </button>
        </>
      )}
    >
      <section className="overall">
        <div className="row">
          <span className="label">This week</span>
          <span className="sub">
            {isCountBased
              ? `${Math.round(achieved)}/${Math.round(target)} check-ins`
              : `${achieved.toFixed(1)}h / ${target.toFixed(1)}h`}
          </span>
        </div>
        <div className="row" style={{ marginTop: 2 }}>
          <span className="value">{progress}%</span>
          {statusClass !== null && statusLabel && (
            <Badge variant={statusClass || 'neutral'} showDot>
              {statusLabel}
            </Badge>
          )}
        </div>
        {isCountBased && recurring ? (
          <div className="checkin-dots" style={{ marginTop: 10 }}>
            {dayValues.map((value, index) => (
              <div key={weekDays[index]} className={`d${value > 0 ? ' done' : ''}`} />
            ))}
          </div>
        ) : (
          <div className="track" style={{ marginTop: 10 }}>
            <div className="fill" style={{ width: `${progress}%` }} />
          </div>
        )}
      </section>

      {recurring ? (
        <>
          <p className="ds-eyebrow" style={{ marginTop: 16 }}>Weekly activity</p>
          <div className="heatmap">
            {dayValues.map((value, index) => (
              <div key={weekDays[index]} className="day">
                <div className="bar" style={{ height: `${Math.round((value / maxDay) * 100)}%` }} />
              </div>
            ))}
          </div>
          <div className="heatmap-labels">
            {['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((label) => (
              <span key={label}>{label}</span>
            ))}
          </div>
        </>
      ) : null}

      {/* Planned sessions — upcoming work comes first; what's already done is
          shown below under "Recent". */}
      {!sessionsLoading && upcomingSessions.length > 0 && (
        <>
          <p className="ds-eyebrow" style={{ marginTop: 16 }}>
            Scheduled sessions
          </p>
          <div className="plan-sessions-list">
            {upcomingSessions.map(session => (
              <div key={session.id} className="plan-session-row">
                <div className="plan-session-info">
                  <span className="plan-session-title">
                    {session.title || 'Untitled session'}
                  </span>
                  <span className="plan-session-time">
                    {formatSessionTime(session.planned_start)}
                    {session.planned_duration_min ? ` · ${session.planned_duration_min} min` : ''}
                  </span>
                </div>
                <div className="plan-session-actions">
                  <button
                    type="button"
                    className="plan-session-btn plan-session-btn--edit"
                    onClick={() => setEditSession(session)}
                    aria-label="Edit session"
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    type="button"
                    className="plan-session-btn plan-session-btn--cal"
                    onClick={() => setCalendarSession(session)}
                    aria-label="Add to calendar"
                  >
                    <CalendarPlus size={14} />
                  </button>
                  <button
                    type="button"
                    className="plan-session-btn plan-session-btn--done"
                    onClick={() => setLogDoneSessionId(session.id)}
                    aria-label="Log and mark done"
                  >
                    <Check size={14} />
                  </button>
                  <button
                    type="button"
                    className="plan-session-btn plan-session-btn--delete"
                    onClick={() => handleDelete(session.id)}
                    aria-label="Delete session"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Recent logs — what was actually done on this promise (read-only) */}
      {recentLogs.length > 0 && (
        <>
          <p className="ds-eyebrow" style={{ marginTop: 16 }}>Recent</p>
          <div className="recent-log-list">
            {recentLogs.map((log, index) => {
              const note = (log.notes ?? '').trim();
              const amount = log.time_spent > 0 ? log.time_str : '';
              return (
                <div key={`${log.datetime}-${index}`} className="recent-log-row">
                  <span className="recent-log-icon" aria-hidden>
                    <Check size={12} />
                  </span>
                  <span className="recent-log-title">
                    {note || (amount ? `${amount} logged` : 'Logged')}
                  </span>
                  <span className="recent-log-time">
                    {note && amount ? `${amount} · ` : ''}{formatLogDate(log.date)}
                  </span>
                </div>
              );
            })}
          </div>
        </>
      )}

      <div className="action-row" style={{ marginTop: 16 }}>
        {isCountBased ? (
          <Button variant="secondary" onClick={onCheckin}>
            <Check size={14} />
            Check in
          </Button>
        ) : (
          <Button variant="secondary" onClick={onLogTime}>
            <Clock size={14} />
            Log
          </Button>
        )}
        <Button variant="secondary" onClick={onSchedule}>
          <Timer size={14} />
          Schedule
        </Button>
        <Button variant="secondary" onClick={onEdit}>
          <Pencil size={14} />
          Edit
        </Button>
      </div>

      {/* Log + mark-done modal, opened when tapping ✓ on a planned session row */}
      <LogActionModal
        promiseId={promiseId}
        promiseText={formatPromiseText(text)}
        isOpen={logDoneSessionId !== null}
        onClose={() => setLogDoneSessionId(null)}
        onSuccess={handleLogDoneSuccess}
        prefillHours={doneSessionPrefill?.hours}
        prefillDate={doneSessionPrefill?.date}
        prefillTime={doneSessionPrefill?.time}
        prefillNotes={doneSessionPrefill?.notes}
      />

      {/* Edit a scheduled session — reuses the schedule sheet in edit mode */}
      <ScheduleSheet
        open={editSession !== null}
        promiseId={promiseId}
        promiseText={formatPromiseText(text)}
        weekDays={weekDays}
        editSession={editSession}
        onClose={() => setEditSession(null)}
        onSuccess={() => {
          setEditSession(null);
          reloadSessions();
          onLogged?.();
        }}
      />

      {/* Add-to-calendar chooser (Google Calendar / .ics) */}
      <AddToCalendarSheet
        open={calendarSession !== null}
        session={calendarSession}
        promiseText={formatPromiseText(text)}
        onClose={() => setCalendarSession(null)}
      />
    </BottomSheet>
  );
}
