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

const TIME_SLOTS = ['07:00', '09:00', '12:00', '15:00', '18:00', '21:00'];
const DURATION_PRESETS = [15, 30, 45, 60, 90];
const DEFAULT_DURATION = 30;
const REMINDER_OPTIONS = [
  { value: 0, label: 'At start' },
  { value: 5, label: '5m before' },
  { value: 10, label: '10m before' },
  { value: 30, label: '30m before' },
  { value: 60, label: '1h before' },
];

function todayKey() {
  const now = new Date();
  return [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, '0'),
    String(now.getDate()).padStart(2, '0'),
  ].join('-');
}

function formatDayLabel(dateKey: string) {
  const date = new Date(`${dateKey}T12:00:00`);
  return {
    dow: date.toLocaleDateString('en-US', { weekday: 'short' }),
    num: date.getDate(),
  };
}

export function ScheduleSheet({ open, promiseId, promiseText, weekDays, onClose, onSuccess }: ScheduleSheetProps) {
  const [title, setTitle] = useState('');
  const [selectedDate, setSelectedDate] = useState(todayKey());
  const [selectedTime, setSelectedTime] = useState('09:00');
  const [duration, setDuration] = useState<number>(DEFAULT_DURATION);
  const [reminderEnabled, setReminderEnabled] = useState(true);
  const [reminderOffset, setReminderOffset] = useState('10');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  const selectableWeekDays = useMemo(() => weekDays.filter(day => day >= todayKey()), [weekDays]);
  const labels = useMemo(() => selectableWeekDays.map(formatDayLabel), [selectableWeekDays]);

  useEffect(() => {
    if (!open) return;
    setTitle('');
    setSelectedDate(todayKey());
    setSelectedTime('09:00');
    setDuration(DEFAULT_DURATION);
    setReminderEnabled(true);
    setReminderOffset('10');
    setError('');
  }, [open]);

  const handleSubmit = async () => {
    if (!selectedDate || !selectedTime) return;
    if (!Number.isFinite(duration) || duration <= 0) {
      setError('Duration must be greater than 0 minutes');
      return;
    }
    setIsSubmitting(true);
    setError('');
    try {
      const plannedStart = new Date(`${selectedDate}T${selectedTime}:00`).toISOString();
      await apiClient.createPlanSession(promiseId, {
        title: title.trim() || 'Planned session',
        planned_start: plannedStart,
        planned_duration_min: duration,
        reminder_enabled: reminderEnabled,
        reminder_offset_min: Number(reminderOffset),
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
      <p className="ds-caption">Title (optional)</p>
      <input
        type="text"
        className="sched-title-input"
        placeholder="Planned session"
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        maxLength={120}
      />

      <p className="ds-caption" style={{ marginTop: 12 }}>Date</p>
      <input
        type="date"
        className="sched-single-input"
        value={selectedDate}
        min={todayKey()}
        onChange={(event) => setSelectedDate(event.target.value)}
      />
      {labels.length > 0 ? (
        <div className="sched-grid" style={{ marginTop: 8 }}>
          {labels.map((label, index) => (
            <button
              key={selectableWeekDays[index]}
              type="button"
              className={`sched-day${selectedDate === selectableWeekDays[index] ? ' is-active' : ''}`}
              onClick={() => setSelectedDate(selectableWeekDays[index])}
            >
              <span>{label.dow}</span>
              <span className="num">{label.num}</span>
            </button>
          ))}
        </div>
      ) : null}

      <p className="ds-caption" style={{ marginTop: 12 }}>Time</p>
      <input
        type="time"
        className="sched-single-input"
        value={selectedTime}
        onChange={(event) => setSelectedTime(event.target.value)}
      />
      <div className="sched-chip-row" style={{ marginTop: 8 }}>
        {TIME_SLOTS.map((slot) => (
          <button
            key={slot}
            type="button"
            className={`sched-chip${selectedTime === slot ? ' is-active' : ''}`}
            onClick={() => setSelectedTime(slot)}
          >
            {slot}
          </button>
        ))}
      </div>

      <p className="ds-caption" style={{ marginTop: 12 }}>Duration</p>
      <div className="sched-chip-row">
        {DURATION_PRESETS.map((preset) => (
          <button
            key={preset}
            type="button"
            className={`sched-chip${duration === preset ? ' is-active' : ''}`}
            onClick={() => setDuration(preset)}
          >
            {preset}m
          </button>
        ))}
        <input
          type="number"
          className="sched-chip-input"
          min={1}
          step={5}
          placeholder="custom"
          value={DURATION_PRESETS.includes(duration) ? '' : String(duration)}
          onChange={(event) => {
            const next = Number(event.target.value);
            if (Number.isFinite(next) && next > 0) setDuration(next);
            else if (event.target.value === '') setDuration(DEFAULT_DURATION);
          }}
          aria-label="Custom duration in minutes"
        />
      </div>

      <div className="sched-reminder-row" style={{ marginTop: 12 }}>
        <label>
          <input
            type="checkbox"
            checked={reminderEnabled}
            onChange={(event) => setReminderEnabled(event.target.checked)}
          />
          Reminder
        </label>
        <select
          value={reminderOffset}
          disabled={!reminderEnabled}
          onChange={(event) => setReminderOffset(event.target.value)}
        >
          {REMINDER_OPTIONS.map(option => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>
      {error ? <p className="ds-caption" style={{ color: 'var(--bad-500)', marginTop: 8 }}>{error}</p> : null}
      <Button variant="primary" fullWidth onClick={handleSubmit} disabled={isSubmitting} style={{ marginTop: 16 }}>
        {isSubmitting ? 'Saving…' : 'Schedule session'}
      </Button>
    </BottomSheet>
  );
}
