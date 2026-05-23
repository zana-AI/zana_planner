import { useEffect, useState } from 'react';
import { apiClient } from '../../api/client';
import { BottomSheet } from '../ui/BottomSheet';
import { Button } from '../ui/Button';

interface LogTimeSheetProps {
  open: boolean;
  promiseId: string;
  promiseText: string;
  onClose: () => void;
  onSuccess: (message: string) => void;
  prefillHours?: string;
  prefillDate?: string;
  prefillTime?: string;
  prefillNotes?: string;
}

const QUICK_HOURS = ['0.5', '1', '2'];

export function LogTimeSheet({
  open,
  promiseId,
  promiseText,
  onClose,
  onSuccess,
  prefillHours,
  prefillDate,
  prefillTime,
  prefillNotes,
}: LogTimeSheetProps) {
  const [hours, setHours] = useState(prefillHours ?? '1');
  const [date, setDate] = useState('');
  const [time, setTime] = useState('');
  const [notes, setNotes] = useState(prefillNotes ?? '');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    const now = new Date();
    setHours(prefillHours ?? '1');
    setDate(prefillDate ?? now.toISOString().split('T')[0]);
    setTime(prefillTime ?? `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`);
    setNotes(prefillNotes ?? '');
    setError('');
  }, [open, prefillDate, prefillHours, prefillNotes, prefillTime]);

  const handleSubmit = async () => {
    const hoursNum = parseFloat(hours);
    if (Number.isNaN(hoursNum) || hoursNum <= 0) {
      setError('Enter a valid number of hours');
      return;
    }
    setIsSubmitting(true);
    setError('');
    try {
      let actionDatetime: string | undefined;
      if (date && time) {
        const [hours24, minutes] = time.split(':');
        actionDatetime = new Date(`${date}T${hours24}:${minutes}:00`).toISOString();
      }
      await apiClient.logAction(promiseId, hoursNum, actionDatetime, notes.trim() || undefined);
      onSuccess(`Logged ${hoursNum}h`);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to log time');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <BottomSheet open={open} onClose={onClose} title="Log time" subtitle={promiseText}>
      <div className="lt-quick">
        {QUICK_HOURS.map((value) => (
          <button
            key={value}
            type="button"
            className={hours === value ? 'is-active' : ''}
            onClick={() => setHours(value)}
          >
            {value}
            <span className="lt-sub">hours</span>
          </button>
        ))}
      </div>
      <div className="field-row" style={{ marginTop: 12 }}>
        <label htmlFor="log-hours">Hours</label>
        <input id="log-hours" type="number" step="0.1" min="0.1" value={hours} onChange={(e) => setHours(e.target.value)} />
      </div>
      <div className="lt-grid2" style={{ marginTop: 12 }}>
        <div className="field-row">
          <label htmlFor="log-date">Date</label>
          <input id="log-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </div>
        <div className="field-row">
          <label htmlFor="log-time">Time</label>
          <input id="log-time" type="time" value={time} onChange={(e) => setTime(e.target.value)} />
        </div>
      </div>
      <div className="field-row" style={{ marginTop: 12 }}>
        <label htmlFor="log-notes">Note (optional)</label>
        <textarea id="log-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
      </div>
      {error ? <p className="ds-caption" style={{ color: 'var(--bad-500)', marginTop: 8 }}>{error}</p> : null}
      <Button variant="primary" fullWidth onClick={handleSubmit} disabled={isSubmitting} style={{ marginTop: 16 }}>
        {isSubmitting ? 'Logging…' : 'Save log'}
      </Button>
    </BottomSheet>
  );
}
