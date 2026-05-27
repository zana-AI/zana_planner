import type { HTMLAttributes, KeyboardEvent } from 'react';
import type { PromiseData } from '../types';
import { Badge } from './ui/Badge';
import { formatPromiseText } from '../utils/activityFormat';

interface PromiseCardV2Props {
  id: string;
  data: PromiseData;
  weekDays: string[];
  onOpenDetail: () => void;
}

function toLocalDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

// Returns expected progress fraction (0-1) based on today's position in the week.
// Returns 1.0 for past weeks (today is not in weekDays).
function weekExpectedFraction(weekDays: string[]): number {
  const todayKey = toLocalDateKey(new Date());
  const idx = weekDays.indexOf(todayKey);
  return idx >= 0 ? (idx + 1) / 7 : 1.0;
}

function getStatusInfo(
  progress: number,
  expectedFraction: number,
): { label: string; cls: 'good' | 'warn' | 'bad' | '' } {
  const expected = expectedFraction * 100;
  if (progress >= expected) return { label: 'On track', cls: 'good' };
  if (progress >= expected * 0.5) return { label: 'Behind', cls: 'warn' };
  if (progress > 0) return { label: 'At risk', cls: 'bad' };
  return { label: 'At risk', cls: '' };
}

function formatNextSession(isoStr: string): string {
  const dt = new Date(isoStr);
  if (Number.isNaN(dt.getTime())) return '';
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  const dtDay = new Date(dt);
  dtDay.setHours(0, 0, 0, 0);
  const time = dt.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
  if (dtDay.getTime() === today.getTime()) return `Today ${time}`;
  if (dtDay.getTime() === tomorrow.getTime()) return `Tomorrow ${time}`;
  return dt.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}

export function PromiseCardV2({ id, data, weekDays, onOpenDetail }: PromiseCardV2Props) {
  const {
    text,
    hours_promised,
    hours_spent,
    sessions = [],
    metric_type = 'hours',
    target_value = hours_promised,
    template_kind = 'commitment',
    achieved_value = hours_spent,
    recurring = true,
    planned_sessions_count = 0,
    next_session_start,
  } = data;

  const isCountBased = metric_type === 'count';
  const isBudget = template_kind === 'budget';
  const target = target_value || hours_promised || 1;
  const achieved = achieved_value ?? hours_spent ?? 0;
  const progress = target > 0 ? Math.min(Math.round((achieved / target) * 100), 100) : 0;
  const expectedFraction = weekExpectedFraction(weekDays);
  const { label: statusLabel, cls: statusClass } = getStatusInfo(progress, expectedFraction);

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

  const checkinDays = weekDays.map((date) => (sessionsByDate[date] || 0) > 0);

  const sessionsLabel = planned_sessions_count > 0
    ? (next_session_start
        ? formatNextSession(next_session_start)
        : `${planned_sessions_count} session${planned_sessions_count > 1 ? 's' : ''}`)
    : null;

  return (
    <article
      className={['pcard', statusClass].filter(Boolean).join(' ')}
      onClick={onOpenDetail}
      role="button"
      tabIndex={0}
      onKeyDown={(event: KeyboardEvent<HTMLElement>) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onOpenDetail();
        }
      }}
    >
      <DTop>
        <DTitle>
          <span dir="auto">{formatPromiseText(text)}</span>
          <span className="pid" dir="ltr">#{id}</span>
        </DTitle>
        <Badge variant={statusClass || 'neutral'} showDot>
          {statusLabel}
        </Badge>
      </DTop>
      {isCountBased && recurring ? (
        <DDots aria-hidden="true">
          {checkinDays.map((done, index) => (
            <DDot key={weekDays[index]} className={`d${done ? ' done' : ''}`} />
          ))}
        </DDots>
      ) : !isBudget ? (
        <DProgress aria-hidden="true">
          <DFill style={{ width: `${progress}%` }} />
        </DProgress>
      ) : null}
      <DRow>
        <span className="sub" dir="ltr">
          {isCountBased
            ? `${Math.round(achieved)}/${Math.round(target)} check-ins`
            : `${achieved.toFixed(1)}h / ${target.toFixed(1)}h`}
        </span>
        {sessionsLabel ? (
          <span className="sessions-chip" dir="ltr" aria-label={`${planned_sessions_count} planned session${planned_sessions_count > 1 ? 's' : ''}`}>
            &#x1F4C5; {sessionsLabel}
          </span>
        ) : (
          <span className="meta" dir="ltr">{progress}%</span>
        )}
      </DRow>
    </article>
  );
}

function DTop(props: HTMLAttributes<HTMLDivElement>) {
  return <div className="top" {...props} />;
}
function DTitle(props: HTMLAttributes<HTMLDivElement>) {
  return <div className="title" {...props} />;
}
function DDots(props: HTMLAttributes<HTMLDivElement>) {
  return <div className="checkin-dots" {...props} />;
}
function DDot(props: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} />;
}
function DProgress(props: HTMLAttributes<HTMLDivElement>) {
  return <div className="progress" {...props} />;
}
function DFill(props: HTMLAttributes<HTMLDivElement>) {
  return <div className="fill" {...props} />;
}
function DRow(props: HTMLAttributes<HTMLDivElement>) {
  return <div className="row" {...props} />;
}
