import { useState } from 'react';
import { apiClient } from '../api/client';
import { useModalBodyLock } from '../hooks/useModalBodyLock';

interface CheckinModalProps {
  promiseId: string;
  promiseText: string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function CheckinModal({ promiseId, promiseText, isOpen, onClose, onSuccess }: CheckinModalProps) {
  const [date, setDate] = useState('');
  const [time, setTime] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  useModalBodyLock(isOpen);

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

    setIsSubmitting(true);

    try {
      // Combine date and time into ISO datetime string
      let actionDatetime: string | undefined;
      if (date && time) {
        const [hours24, minutes] = time.split(':');
        const datetime = new Date(`${date}T${hours24}:${minutes}:00`);
        actionDatetime = datetime.toISOString();
      }

      await apiClient.checkinPromise(promiseId, { action_datetime: actionDatetime });
      
      // Reset form
      setDate('');
      setTime('');
      
      onSuccess();
      onClose();
    } catch (err: any) {
      console.error('Failed to check in:', err);
      setError(err.message || 'Failed to check in. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    if (!isSubmitting) {
      setDate('');
      setTime('');
      setError('');
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">Check In</h2>
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
            <label htmlFor="checkin-date" className="modal-label">Date</label>
            <input
              id="checkin-date"
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="modal-input"
              disabled={isSubmitting}
            />
          </div>

          <div className="modal-form-group">
            <label htmlFor="checkin-time" className="modal-label">Time</label>
            <input
              id="checkin-time"
              type="time"
              value={time}
              onChange={(e) => setTime(e.target.value)}
              className="modal-input"
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
              disabled={isSubmitting}
            >
              {isSubmitting ? 'Checking in...' : 'Check In'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

