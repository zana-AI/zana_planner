import type { HTMLAttributes, KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { formatDate, formatNumber } from '../i18n/format';
import type { PromiseData, UpcomingPlanSession } from '../types';
import { Badge } from './ui/Badge';
import { formatPromiseText } from '../utils/activityFormat';

interface PromiseCardV2Props {
  id: string;
  data: PromiseData;
  weekDays: string[];
  onOpenDetail: () => void;
  /** Today's planned sessions for this promise, rendered as prominent nested rows. */
  plannedToday?: UpcomingPlanSession[];
}

function toLocalDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

// Time column for a nested session row: clock for today, day + clock for future,
// and a clear "No time" for accepted tasks that don't have a slot yet.
function formatSessionWhen(isoStr: string | null, t: TFunction): string {
  if (!isoStr) return t('promise.noTime');
  const dt = new Date(isoStr);
  if (Number.isNaN(dt.getTime())) return t('promise.noTime');
  const time = formatDate(dt, { hour: 'numeric', minute: '2-digit' });
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const dtDay = new Date(dt);
  dtDay.setHours(0, 0, 0, 0);
  const diffDays = Math.round((dtDay.getTime() - today.getTime()) / 86400000);
  if (diffDays === 0) return time;
  if (diffDays === 1) return t('promise.tomorrowShortAt', { time });
  return `${formatDate(dt, { weekday: 'short', month: 'short', day: 'numeric' })} · ${time}`;
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
): { key: 'onTrack' | 'behind' | 'atRisk'; cls: 'good' | 'warn' | 'bad' | '' } {
  const expected = expectedFraction * 100;
  if (progress >= expected) return { key: 'onTrack', cls: 'good' };
  if (progress >= expected * 0.5) return { key: 'behind', cls: 'warn' };
  if (progress > 0) return { key: 'atRisk', cls: 'bad' };
  return { key: 'atRisk', cls: '' };
}

function formatNextSession(isoStr: string, t: TFunction): string {
  const dt = new Date(isoStr);
  if (Number.isNaN(dt.getTime())) return '';
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  const dtDay = new Date(dt);
  dtDay.setHours(0, 0, 0, 0);
  const time = formatDate(dt, { hour: 'numeric', minute: '2-digit' });
  if (dtDay.getTime() === today.getTime()) return t('promise.todayAt', { time });
  if (dtDay.getTime() === tomorrow.getTime()) return t('promise.tomorrowAt', { time });
  return formatDate(dt, { weekday: 'short', month: 'short', day: 'numeric' });
}

export function PromiseCardV2({ id, data, weekDays, onOpenDetail, plannedToday = [] }: PromiseCardV2Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
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
    daily_activity,
    quizzes,
    decks = [],
    credits_minutes,
  } = data;

  const isCountBased = metric_type === 'count';
  const isBudget = template_kind === 'budget';
  const target = target_value || hours_promised || 1;
  const achieved = achieved_value ?? hours_spent ?? 0;
  const progress = target > 0 ? Math.min(Math.round((achieved / target) * 100), 100) : 0;
  const expectedFraction = weekExpectedFraction(weekDays);
  const { key: statusKey, cls: statusClass } = getStatusInfo(progress, expectedFraction);
  const statusLabel = t(`status.${statusKey}`);

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

  // Upcoming planned sessions for this promise (dated today/future or not-yet-timed),
  // soonest first with untimed last. These render as prominent rows nested under the
  // card so tasks stay noticed under their parent promise.
  const upcomingSessions = [...plannedToday]
    .filter(s => s.status === 'planned')
    .sort((a, b) => {
      const ta = a.planned_start ? new Date(a.planned_start).getTime() : Infinity;
      const tb = b.planned_start ? new Date(b.planned_start).getTime() : Infinity;
      return ta - tb;
    });
  const hasSessionRows = upcomingSessions.length > 0;

  // Small chip only kicks in when there are no rows to nest but the report still
  // reports a session (rare fallback).
  // At most two, and only for work that is actually waiting — a card carrying a
  // row of buttons stops reading as "this one needs you".
  const ctas: Array<{ key: string; label: string; to: string }> = [];
  const dueQuizzes = (quizzes ?? (daily_activity ? [daily_activity] : []))
    .filter((q) => q.status === 'due');
  for (const quiz of dueQuizzes) {
    if (ctas.length >= 2) break;
    ctas.push({
      key: `quiz-${quiz.challenge_id}`,
      // Once a promise owns several courses, "Today's quiz" is ambiguous — say
      // which one. With only one, the generic label reads better.
      label: dueQuizzes.length > 1 && quiz.title
        ? `📝 ${quiz.title} →`
        : "📝 Today's quiz →",
      to: `/challenges/${quiz.challenge_id}/play`,
    });
  }
  for (const deck of decks) {
    const pending = deck.due + deck.new;
    if (pending === 0 || ctas.length >= 2) continue;
    ctas.push({
      key: `deck-${deck.deck_id}`,
      label: `🎴 ${deck.name} · ${pending} to review →`,
      to: `/flashcards?deck=${encodeURIComponent(deck.deck_id)}&name=${encodeURIComponent(deck.name)}`,
    });
  }

  const sessionsLabel = !hasSessionRows && planned_sessions_count > 0
    ? (next_session_start
        ? formatNextSession(next_session_start, t)
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
            ? t('promise.checkIns', { done: Math.round(achieved), total: Math.round(target) })
            : t('dashboard.hoursOfHours', { spent: formatNumber(achieved, { minimumFractionDigits: 1, maximumFractionDigits: 1 }), promised: formatNumber(target, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) })}
        </span>
        {credits_minutes && credits_minutes > 0 ? (
          <span className="pcard-credits" dir="ltr" title="Earned from quizzes and reviews this week">
            ⚡ {Math.round(credits_minutes)}
          </span>
        ) : null}
        {sessionsLabel ? (
          <span className="sessions-chip" dir="ltr" aria-label={`${planned_sessions_count} planned session${planned_sessions_count > 1 ? 's' : ''}`}>
            &#x1F4C5; {sessionsLabel}
          </span>
        ) : (
          <span className="meta" dir="auto">{formatNumber(progress)}%</span>
        )}
      </DRow>
      {hasSessionRows ? (
        <div className="pcard-today">
          {upcomingSessions.map(session => {
            const title = (session.title || '').trim() || t('promise.session');
            const when = formatSessionWhen(session.planned_start, t);
            const checklistTotal = session.checklist?.length ?? 0;
            const checklistDone = session.checklist?.filter(item => item.done).length ?? 0;
            const meta = [
              session.planned_duration_min ? `${session.planned_duration_min} min` : '',
              checklistTotal > 0 ? `${checklistDone}/${checklistTotal} steps` : '',
            ].filter(Boolean).join(' · ');
            return (
              <div key={session.id} className="pcard-task">
                <span className={`pcard-task-time${session.planned_start ? '' : ' pcard-task-time--none'}`} dir="ltr">{when}</span>
                <span className="pcard-task-body">
                  <span className="pcard-task-title" dir="auto">{title}</span>
                  {meta && <span className="pcard-task-meta" dir="ltr">{meta}</span>}
                </span>
              </div>
            );
          })}
        </div>
      ) : null}
      {/* Call to action. A promise card that only reports a shortfall gives the
          user nothing to press; these turn "0/7 check-ins, at risk" into a way
          out of it. Vocabulary decks reuse the button the challenge quiz already
          had rather than inventing a second style for the same idea. */}
      {ctas.map((cta) => (
        <button
          key={cta.key}
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            navigate(cta.to);
          }}
          className="pcard-cta"
        >
          {cta.label}
        </button>
      ))}
      {daily_activity && daily_activity.status !== 'due' ? (
        <div
          style={{ marginTop: 10, fontSize: 12.5, color: 'var(--color-text-secondary, #8A94A6)', textAlign: 'right' }}
          dir="ltr"
        >
          ✓ Quiz done{daily_activity.score != null ? ` · ${Math.round(daily_activity.score)}%` : ''}
        </div>
      ) : null}
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
