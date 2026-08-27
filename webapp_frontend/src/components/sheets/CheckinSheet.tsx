import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation();
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
      onSuccess(t('checkin.checkedIn'));
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('checkin.failed'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <BottomSheet open={open} onClose={onClose} title={t('checkin.checkIn2')} subtitle={promiseText}>
      <button type="button" className="btn-checkin" onClick={handleSubmit} disabled={isSubmitting}>
        <span className="circle">✓</span>{t('checkin.markTodayComplete')}</button>
      {error ? <p className="ds-caption" style={{ color: 'var(--bad-500)', marginTop: 8 }}>{error}</p> : null}
    </BottomSheet>
  );
}
