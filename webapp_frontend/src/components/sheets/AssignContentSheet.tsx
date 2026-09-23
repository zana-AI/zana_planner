import { useEffect, useState } from 'react';
import { Check } from 'lucide-react';
import { apiClient } from '../../api/client';
import { useTelegramWebApp } from '../../hooks/useTelegramWebApp';
import type { PromiseData } from '../../types';
import { BottomSheet } from '../ui/BottomSheet';

interface AssignContentSheetProps {
  open: boolean;
  contentId: string | null;
  contentTitle: string;
  onClose: () => void;
  onAssigned: (promiseId: string) => void;
}

export function AssignContentSheet({ open, contentId, contentTitle, onClose, onAssigned }: AssignContentSheetProps) {
  const { hapticFeedback } = useTelegramWebApp();
  const [promises, setPromises] = useState<Array<[string, PromiseData]>>([]);
  const [loading, setLoading] = useState(false);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    let active = true;
    setLoading(true);
    setError('');
    void apiClient.getWeeklyReport()
      .then((report) => {
        if (active) setPromises(Object.entries(report.promises));
      })
      .catch(() => {
        if (active) setError('Could not load your tasks. Please try again.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [open]);

  const assign = async (promiseId: string) => {
    if (!contentId) return;
    setSavingId(promiseId);
    setError('');
    try {
      await apiClient.assignUserContent(contentId, promiseId);
      hapticFeedback('success');
      onAssigned(promiseId);
      onClose();
    } catch {
      hapticFeedback('error');
      setError('Could not assign this content. Please try again.');
    } finally {
      setSavingId(null);
    }
  };

  return (
    <BottomSheet open={open} onClose={onClose} title="Assign to task" subtitle={contentTitle}>
      <div className="plan-content-options">
        {loading ? <p className="plan-content-note">Loading your tasks…</p> : null}
        {!loading && promises.map(([promiseId, promise]) => (
          <button
            key={promiseId}
            type="button"
            className="plan-content-option"
            disabled={savingId !== null}
            onClick={() => void assign(promiseId)}
          >
            <span className="plan-content-option-label" dir="auto">{promise.text}</span>
            {savingId === promiseId ? <Check size={18} aria-label="Saving" /> : <span>#{promiseId}</span>}
          </button>
        ))}
        {!loading && promises.length === 0 ? <p className="plan-content-note">No active tasks yet.</p> : null}
      </div>
      {error ? <p className="plan-content-error">{error}</p> : null}
    </BottomSheet>
  );
}
