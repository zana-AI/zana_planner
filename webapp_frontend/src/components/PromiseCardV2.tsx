import type { HTMLAttributes, KeyboardEvent, MouseEvent, ReactNode } from 'react';
import type { PromiseData } from '../types';
import { Badge } from './ui/Badge';
import { formatPromiseText } from '../utils/activityFormat';
import {
  readPromiseCardIdPlacement,
  type PromiseCardIdPlacement,
} from './promiseCardIdPlacement';

interface PromiseCardV2Props {
  id: string;
  data: PromiseData;
  weekDays: string[];
  onOpenDetail: () => void;
  onEdit?: () => void;
  idPlacement?: PromiseCardIdPlacement;
  isComparison?: boolean;
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

function PromiseId({ id, className = '' }: { id: string; className?: string }) {
  return <span className={['pcard-id', className].filter(Boolean).join(' ')}>#{id}</span>;
}

export function PromiseCardV2({
  id,
  data,
  weekDays,
  onOpenDetail,
  onEdit,
  idPlacement: idPlacementProp,
  isComparison = false,
}: PromiseCardV2Props) {
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
    visibility = 'private',
  } = data;

  const idPlacement = idPlacementProp ?? readPromiseCardIdPlacement();
  const isClubPromise = visibility === 'clubs';

  const isCountBased = metric_type === 'count';
  const isBudget = template_kind === 'budget';
  const target = target_value || hours_promised || 1;
  const achieved = achieved_value ?? hours_spent ?? 0;
  const progress = target > 0 ? Math.min(Math.round((achieved / target) * 100), 100) : 0;
  const statusClass = getStatusClass(progress);
  const statusLabel = getStatusLabel(progress);

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

  const statsLabel = isCountBased
    ? `${Math.round(achieved)}/${Math.round(target)} check-ins`
    : `${achieved.toFixed(1)}h / ${target.toFixed(1)}h`;

  let statusBadge: ReactNode = (
    <Badge variant={statusClass || 'neutral'} showDot>
      {statusLabel}
    </Badge>
  );

  if (idPlacement === 'badge-before') {
    statusBadge = (
      <Badge variant={statusClass || 'neutral'} showDot className="pcard-badge-with-id">
        <PromiseId id={id} />
        <span className="pcard-badge-sep">·</span>
        {statusLabel}
      </Badge>
    );
  } else if (idPlacement === 'badge-after') {
    statusBadge = (
      <Badge variant={statusClass || 'neutral'} showDot className="pcard-badge-with-id">
        {statusLabel}
        <span className="pcard-badge-sep">·</span>
        <PromiseId id={id} />
      </Badge>
    );
  }

  const handleCardClick = () => {
    if (isComparison) return;
    onOpenDetail();
  };

  const handleEditClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    onEdit?.();
  };

  return (
    <article
      className={['pcard', statusClass, isComparison ? 'pcard--comparison' : ''].filter(Boolean).join(' ')}
      onClick={handleCardClick}
      role={isComparison ? undefined : 'button'}
      tabIndex={isComparison ? undefined : 0}
      onKeyDown={(event: KeyboardEvent<HTMLElement>) => {
        if (isComparison) return;
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onOpenDetail();
        }
      }}
    >
      <DTop>
        <DTitle dir="auto">
          {formatPromiseText(text)}
          {idPlacement === 'title' ? <PromiseId id={id} className="pcard-id--title" /> : null}
        </DTitle>
        <div className="pcard-top-actions">
          {onEdit && !isClubPromise && !isComparison ? (
            <button type="button" className="pcard-edit-btn" onClick={handleEditClick}>
              Edit
            </button>
          ) : null}
          {statusBadge}
        </div>
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
      <DRow className={idPlacement === 'meta' ? 'row-stats row-stats--with-id' : 'row-stats'}>
        {idPlacement === 'meta' ? <PromiseId id={id} /> : null}
        <span className="sub" dir="ltr">
          {statsLabel}
        </span>
        <span className="meta" dir="ltr">
          {progress}%
        </span>
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
