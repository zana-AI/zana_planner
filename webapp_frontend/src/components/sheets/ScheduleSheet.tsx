import { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../api/client';
import { BottomSheet } from '../ui/BottomSheet';
import { Button } from '../ui/Button';

interface ScheduleSheetProps {
  open: boolean;
  promiseId: string;
  promiseText: string;
  weekDays: string[];
  onClose: () => void;
  onSuccess: (message: string) => void;
}

const TIME_SLOTS = ['09:00', '12:00', '15:00', '18:00'];

function formatDayLabel(dateKey: string) {
  const date = new Date(`${dateKey}T12:00:00`);
  return {
    dow: date.toLocaleDateString('en-US', { weekday: 'short' }),
    num: date.getDate(),
  };
}

export function ScheduleSheet({ open, promiseId, promiseText, weekDays, onClose, onSuccess }: ScheduleSheetProps) {
  const [selectedDay, setSelectedDay] = useState(0);
  const [selectedTime, setSelectedTime] = useState('09:00');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  const labels = useMemo(() => weekDays.map(formatDayLabel), [weekDays]);

  useEffect(() => {
    if (!open) return;
    setSelectedDay(0);
    setSelectedTime('09:00');
    setError('');
  }, [open]);

  const handleSubmit = async () => {
    if (!weekDays[selectedDay]) return;
    setIsSubmitting(true);
    setError('');
    try {
      const plannedStart = `${weekDays[selectedDay]}T${selectedTime}:00`;
      await apiClient.createPlanSession(promiseId, {
        title: 'Planned session',
        planned_start: plannedStart,
        planned_duration_min: 25,
      });
      onSuccess('Session scheduled');
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to schedule session');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <BottomSheet open={open} onClose={onClose} title="Schedule session" subtitle={promiseText}>
      <p className="ds-caption">Pick a day</p>
      <div className="sched-grid">
        {labels.map((label, index) => (
          <button
            key={weekDays[index]}
            type="button"
            className={`sched-day${selectedDay === index ? ' is-active' : ''}`}
            onClick={() => setSelectedDay(index)}
          >
            <span>{label.dow}</span>
            <span className="num">{label.num}</span>
          </button>
        ))}
      </div>
      <p className="ds-caption" style={{ marginTop: 12 }}>Pick a time</p>
      <div className="time-row">
        {TIME_SLOTS.map((slot) => (
          <button
            key={slot}
            type="button"
            className={selectedTime === slot ? 'is-active' : ''}
            onClick={() => setSelectedTime(slot)}
          >
            {slot}
          </button>
        ))}
      </div>
      {error ? <p className="ds-caption" style={{ color: 'var(--bad-500)', marginTop: 8 }}>{error}</p> : null}
      <Button variant="primary" fullWidth onClick={handleSubmit} disabled={isSubmitting} style={{ marginTop: 16 }}>
        {isSubmitting ? 'Saving…' : 'Schedule session'}
      </Button>
    </BottomSheet>
  );
}
