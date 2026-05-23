import { useEffect, useState } from 'react';
import { apiClient } from '../../api/client';
import { BottomSheet } from '../ui/BottomSheet';

interface CheckinSheetProps {
  open: boolean;
  promiseId: string;
  promiseText: string;
  onClose: () => void;
  onSuccess: (message: string) => void;
}

export function CheckinSheet({ open, promiseId, promiseText, onClose, onSuccess }: CheckinSheetProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setError('');
  }, [open]);

  const handleSubmit = async () => {
    setIsSubmitting(true);
    setError('');
    try {
      await apiClient.checkinPromise(promiseId, { action_datetime: new Date().toISOString() });
      onSuccess('Checked in');
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to check in');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <BottomSheet open={open} onClose={onClose} title="Check in" subtitle={promiseText}>
      <button type="button" className="btn-checkin" onClick={handleSubmit} disabled={isSubmitting}>
        <span className="circle">✓</span>
        Mark today complete
      </button>
      {error ? <p className="ds-caption" style={{ color: 'var(--bad-500)', marginTop: 8 }}>{error}</p> : null}
    </BottomSheet>
  );
}
