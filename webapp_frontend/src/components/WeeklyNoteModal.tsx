import { useState, useEffect } from 'react';
import { apiClient } from '../api/client';

interface WeeklyNoteModalProps {
  promiseId: string;
  promiseText: string;
  weekStart: string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function WeeklyNoteModal({ promiseId, promiseText, weekStart, isOpen, onClose, onSuccess }: WeeklyNoteModalProps) {
  const [note, setNote] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    // Could load existing note here if we had an endpoint for it
    setNote('');
  }, [isOpen, weekStart]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    setIsSubmitting(true);

    try {
      await apiClient.updateWeeklyNote(promiseId, {
        week_start: weekStart,
        note: note || undefined,
      });
      
      setNote('');
      onSuccess();
      onClose();
    } catch (err: any) {
      console.error('Failed to update weekly note:', err);
      setError(err.message || 'Failed to update note. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    if (!isSubmitting) {
      setNote('');
      setError('');
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">Weekly Note</h2>
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
            <label htmlFor="weekly-note" className="modal-label">
              Reflection (optional)
            </label>
            <textarea
              id="weekly-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="modal-textarea"
              placeholder="How did this week go? What did you learn?"
              rows={4}
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
              {isSubmitting ? 'Saving...' : 'Save Note'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

