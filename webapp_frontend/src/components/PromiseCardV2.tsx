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

function getStatusClass(progress: number): 'good' | 'warn' | 'bad' | '' {
  if (progress >= 60) return 'good';
  if (progress >= 30) return 'warn';
  if (progress > 0) return 'bad';
  return '';
}

function getStatusLabel(progress: number): string {
  if (progress >= 60) return 'On track';
  if (progress >= 30) return 'Behind';
  return 'At risk';
}

export function PromiseCardV2({ id, data, weekDays, onOpenDetail }: PromiseCardV2Props) {
  const {
    text,
    hours_promised,
    hours_spent,
    sessions,
    metric_type = 'hours',
    target_value = hours_promised,
    template_kind = 'commitment',
    achieved_value = hours_spent,
    recurring = true,
  } = data;

  const isCountBased = metric_type === 'count';
  const isBudget = template_kind === 'budget';
  const target = target_value || hours_promised || 1;
  const achieved = achieved_value ?? hours_spent ?? 0;
  const progress = target > 0 ? Math.min(Math.round((achieved / target) * 100), 100) : 0;
  const statusClass = getStatusClass(progress);

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
        <DTitle dir="auto">{formatPromiseText(text)}</DTitle>
        <Badge variant={statusClass || 'neutral'} showDot>
          {getStatusLabel(progress)}
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
        <span className="meta" dir="ltr">{progress}%</span>
      </DRow>
      <DFootline>
        <span>#{id}</span>
      </DFootline>
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
function DFootline(props: HTMLAttributes<HTMLDivElement>) {
  return <div className="footline" {...props} />;
}
