import { useState, useEffect } from 'react';
import { useModalBodyLock } from '../hooks/useModalBodyLock';

interface LogActionModalProps {
  promiseId: string;
  promiseText: string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  /** Pre-fill values (e.g. from a planned session) */
  prefillHours?: string;
  prefillDate?: string;
  prefillTime?: string;
  prefillNotes?: string;
}

export function LogActionModal({ promiseId, promiseText, isOpen, onClose, onSuccess, prefillHours, prefillDate, prefillTime, prefillNotes }: LogActionModalProps) {
  const [hours, setHours] = useState(prefillHours ?? '');
  const [date, setDate] = useState(prefillDate ?? '');
  const [time, setTime] = useState(prefillTime ?? '');
  const [notes, setNotes] = useState(prefillNotes ?? '');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  useModalBodyLock(isOpen);

  // Sync prefill values whenever the modal opens with new session data
  useEffect(() => {
    if (isOpen) {
      if (prefillHours !== undefined) setHours(prefillHours);
      if (prefillDate !== undefined) setDate(prefillDate);
      if (prefillTime !== undefined) setTime(prefillTime);
      if (prefillNotes !== undefined) setNotes(prefillNotes);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  // Initialize date/time to current if not set
  if (isOpen && !date && !time) {
    const now = new Date();
    setDate(now.toISOString().split('T')[0]);
    const hours24 = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    setTime(`${hours24}:${minutes}`);
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    const hoursNum = parseFloat(hours);
    if (isNaN(hoursNum) || hoursNum <= 0) {
      setError('Please enter a valid positive number of hours');
      return;
    }

    setIsSubmitting(true);

    try {
      const { apiClient } = await import('../api/client');
      
      // Combine date and time into ISO datetime string
      let actionDatetime: string | undefined;
      if (date && time) {
        const [hours24, minutes] = time.split(':');
        const datetime = new Date(`${date}T${hours24}:${minutes}:00`);
        actionDatetime = datetime.toISOString();
      }

      await apiClient.logAction(promiseId, hoursNum, actionDatetime, notes.trim() || undefined);
      
      // Reset form
      setHours('');
      setDate('');
      setTime('');
      setNotes('');
      
      onSuccess();
      onClose();
    } catch (err: any) {
      console.error('Failed to log action:', err);
      setError(err.message || 'Failed to log action. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    if (!isSubmitting) {
      setHours(prefillHours ?? '');
      setDate(prefillDate ?? '');
      setTime(prefillTime ?? '');
      setNotes(prefillNotes ?? '');
      setError('');
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">Log Time</h2>
          <button className="modal-close" onClick={handleClose} disabled={isSubmitting}>
            ×
          </button>
        </div>
        
        <form onSubmit={handleSubmit} className="modal-form">
          <div className="modal-form-group">
            <label className="modal-label">Promise</label>
            <div className="modal-promise-text">{promiseText}</div>
          </div>

          <div className="modal-form-group">
            <label htmlFor="hours" className="modal-label">
              Hours <span className="modal-required">*</span>
            </label>
            <input
              id="hours"
              type="number"
              step="0.1"
              min="0.1"
              value={hours}
              onChange={(e) => setHours(e.target.value)}
              className="modal-input"
              placeholder="e.g., 2.5"
              required
              disabled={isSubmitting}
            />
          </div>

          <div className="modal-form-group">
            <label htmlFor="date" className="modal-label">Date</label>
            <input
              id="date"
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="modal-input"
              disabled={isSubmitting}
            />
          </div>

          <div className="modal-form-group">
            <label htmlFor="time" className="modal-label">Time</label>
            <input
              id="time"
              type="time"
              value={time}
              onChange={(e) => setTime(e.target.value)}
              className="modal-input"
              disabled={isSubmitting}
            />
          </div>

          <div className="modal-form-group">
            <label htmlFor="notes" className="modal-label">Notes (optional)</label>
            <textarea
              id="notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="modal-input"
              placeholder="Add any notes about this session..."
              rows={3}
              disabled={isSubmitting}
            />
          </div>

          {error && (
            <div className="modal-error">{error}</div>
          )}

          <div className="modal-actions">
            <button
              type="button"
              className="modal-button modal-button-secondary"
              onClick={handleClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="modal-button modal-button-primary"
              disabled={isSubmitting || !hours}
            >
              {isSubmitting ? 'Logging...' : 'Log Time'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

