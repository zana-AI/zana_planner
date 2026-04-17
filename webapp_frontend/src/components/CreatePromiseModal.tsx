import { useState } from 'react';
import { X } from 'lucide-react';
import { apiClient, ApiError } from '../api/client';
import { useModalBodyLock } from '../hooks/useModalBodyLock';

interface CreatePromiseModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

function getDefaultEndDate(): string {
  return `${new Date().getFullYear()}-12-31`;
}

export function CreatePromiseModal({ onClose, onSuccess }: CreatePromiseModalProps) {
  const [text, setText] = useState('');
  const [hoursPerWeek, setHoursPerWeek] = useState('1');
  const [endDate, setEndDate] = useState(getDefaultEndDate);
  const [visibility, setVisibility] = useState<'private' | 'public'>('private');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useModalBodyLock(true);

  const handleSubmit = async () => {
    const trimmedText = text.trim();
    const hours = Number(hoursPerWeek);

    if (!trimmedText) {
      setError('Enter a promise.');
      return;
    }

    if (!Number.isFinite(hours) || hours <= 0) {
      setError('Weekly hours must be greater than 0.');
      return;
    }

    setSaving(true);
    setError('');

    try {
      await apiClient.createPromise({
        text: trimmedText,
        hours_per_week: hours,
        recurring: true,
        end_date: endDate || undefined,
        visibility,
      });
      onSuccess();
      onClose();
    } catch (err) {
      console.error('Failed to create promise:', err);
      setError(err instanceof ApiError ? err.message : 'Failed to create promise.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content create-promise-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="modal-header">
          <h2 className="modal-title">New Promise</h2>
          <button className="modal-close" type="button" onClick={onClose} aria-label="Close new promise dialog" disabled={saving}>
            <X size={18} />
          </button>
        </div>

        <form
          className="modal-form"
          onSubmit={(e) => {
            e.preventDefault();
            handleSubmit();
          }}
        >
          <div className="modal-form-group">
            <label className="modal-label" htmlFor="create-promise-text">
              Promise
            </label>
            <textarea
              id="create-promise-text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="e.g., Practice guitar"
              rows={3}
              className="modal-input"
              disabled={saving}
              autoFocus
            />
          </div>

          <div className="modal-form-group">
            <label className="modal-label" htmlFor="create-promise-hours">
              Weekly hours
            </label>
            <input
              id="create-promise-hours"
              type="number"
              min="0.1"
              step="0.1"
              value={hoursPerWeek}
              onChange={(e) => setHoursPerWeek(e.target.value)}
              className="modal-input"
              disabled={saving}
            />
          </div>

          <div className="modal-form-group">
            <label className="modal-label" htmlFor="create-promise-end-date">
              End date (optional)
            </label>
            <input
              id="create-promise-end-date"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="modal-input"
              disabled={saving}
            />
          </div>

          <div className="modal-form-group">
            <label className="modal-label" htmlFor="create-promise-visibility">
              Visibility
            </label>
            <select
              id="create-promise-visibility"
              value={visibility}
              onChange={(e) => setVisibility(e.target.value as 'private' | 'public')}
              className="modal-input"
              disabled={saving}
            >
              <option value="private">Private</option>
              <option value="public">Public</option>
            </select>
          </div>

          {error ? <div className="modal-error">{error}</div> : null}

          <div className="modal-actions">
            <button className="modal-button modal-button-secondary" type="button" onClick={onClose} disabled={saving}>
              Cancel
            </button>
            <button className="modal-button modal-button-primary" type="submit" disabled={saving}>
              {saving ? 'Creating...' : 'Create Promise'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
