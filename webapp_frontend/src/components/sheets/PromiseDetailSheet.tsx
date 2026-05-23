import { useEffect, useMemo, useState } from 'react';
import { Clock, Pencil, Play, Timer } from 'lucide-react';
import type { PromiseData } from '../../types';
import { formatPromiseText } from '../../utils/activityFormat';
import { Badge } from '../ui/Badge';
import { BottomSheet } from '../ui/BottomSheet';
import { Button } from '../ui/Button';

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
  onEdit?: () => void;
}

function getStatusClass(progress: number): 'good' | 'warn' | 'bad' | '' {
  if (progress >= 60) return 'good';
  if (progress >= 30) return 'warn';
  if (progress > 0) return 'bad';
  return '';
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
}: PromiseDetailSheetProps) {
  const {
    text,
    hours_promised,
    hours_spent,
    sessions = [],
    metric_type = 'hours',
    target_value = hours_promised,
    achieved_value = hours_spent,
    recurring = true,
  } = data;

  const isCountBased = metric_type === 'count';
  const target = target_value || hours_promised || 1;
  const achieved = achieved_value ?? hours_spent ?? 0;
  const progress = target > 0 ? Math.min(Math.round((achieved / target) * 100), 100) : 0;
  const statusClass = getStatusClass(progress);

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
    <BottomSheet open={open} onClose={onClose} title={formatPromiseText(text)} subtitle={`Promise #${promiseId}`}>
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
          <Badge variant={statusClass || 'neutral'} showDot>
            {statusClass === 'good' ? 'On track' : statusClass === 'warn' ? 'Behind' : 'At risk'}
          </Badge>
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

      <div className="action-row" style={{ marginTop: 16 }}>
        {onEdit ? (
          <Button variant="secondary" onClick={onEdit}>
            <Pencil size={14} />
            Edit
          </Button>
        ) : null}
        <Button variant="secondary" onClick={onLogTime}>
          <Clock size={14} />
          Log
        </Button>
        {isCountBased ? (
          <Button variant="secondary" onClick={onCheckin}>
            <Timer size={14} />
            Check in
          </Button>
        ) : (
          <Button variant="secondary" onClick={onSchedule}>
            <Timer size={14} />
            Schedule
          </Button>
        )}
        <Button variant="secondary" onClick={onFocus}>
          <Play size={14} />
          Focus
        </Button>
      </div>
    </BottomSheet>
  );
}
