import { useTranslation } from 'react-i18next';
import { useMemo, useState } from 'react';
import { apiClient } from '../../api/client';
import { useTelegramWebApp } from '../../hooks/useTelegramWebApp';
import { BottomSheet } from '../ui/BottomSheet';

interface PlanContentSheetProps {
  open: boolean;
  contentId: string | null;
  title: string;
  /** Runtime in seconds, when the item knows it — it makes a better default than 30. */
  durationSeconds?: number | null;
  onClose: () => void;
  onPlanned: (whenLabel: string) => void;
}

/** A named time, resolved against the viewer's own clock. */
function tonight(): Date {
  const when = new Date();
  when.setHours(20, 0, 0, 0);
  // Asking for "tonight" at half past nine means tomorrow night, not the past.
  if (when.getTime() <= Date.now()) when.setDate(when.getDate() + 1);
  return when;
}

function tomorrowMorning(): Date {
  const when = new Date();
  when.setDate(when.getDate() + 1);
  when.setHours(9, 0, 0, 0);
  return when;
}

function thisWeekend(): Date {
  const when = new Date();
  const daysUntilSaturday = (6 - when.getDay() + 7) % 7 || 7;
  when.setDate(when.getDate() + daysUntilSaturday);
  when.setHours(10, 0, 0, 0);
  return when;
}

/**
 * "Watch later" — but when?
 *
 * Planning used to require a promise: `plan_sessions.promise_uuid` was NOT
 * NULL, so saving a video for Thursday meant first choosing a promise to hang
 * it off, and the bot invented one when nothing fitted. Migration 037 made the
 * promise optional, so this sheet asks for a time and nothing else.
 */
export function PlanContentSheet({
  open,
  contentId,
  title,
  durationSeconds,
  onClose,
  onPlanned,
}: PlanContentSheetProps) {
  const { t } = useTranslation();
  const { hapticFeedback } = useTelegramWebApp();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [customValue, setCustomValue] = useState('');
  const [customOpen, setCustomOpen] = useState(false);

  // Round a known runtime up to the nearest five minutes; otherwise a sitting
  // that is long enough to be worth putting in a calendar.
  const durationMin = useMemo(() => {
    if (!durationSeconds || durationSeconds <= 0) return 30;
    return Math.max(5, Math.ceil(durationSeconds / 60 / 5) * 5);
  }, [durationSeconds]);

  const plan = async (when: Date, label: string) => {
    if (!contentId) return;
    setSaving(true);
    setError('');
    try {
      await apiClient.createStandalonePlanSession({
        title,
        content_id: contentId,
        planned_start: when.toISOString(),
        planned_duration_min: durationMin,
      });
      hapticFeedback('success');
      onPlanned(label);
      setCustomOpen(false);
      setCustomValue('');
      onClose();
    } catch (err) {
      console.error('Failed to plan content:', err);
      hapticFeedback('error');
      setError(t('content.planFailed'));
    } finally {
      setSaving(false);
    }
  };

  const options: { key: string; label: string; when: () => Date }[] = [
    { key: 'tonight', label: t('content.tonight'), when: tonight },
    { key: 'tomorrow', label: t('content.tomorrowMorning'), when: tomorrowMorning },
    { key: 'weekend', label: t('content.thisWeekend'), when: thisWeekend },
  ];

  return (
    <BottomSheet open={open} onClose={onClose} title={t('content.planIt')} subtitle={title}>
      <div className="plan-content-options">
        {options.map((option) => (
          <button
            key={option.key}
            type="button"
            className="plan-content-option"
            disabled={saving}
            onClick={() => void plan(option.when(), option.label)}
          >
            <span className="plan-content-option-label">{option.label}</span>
            <span className="plan-content-option-when">
              {option.when().toLocaleString(undefined, {
                weekday: 'short',
                hour: '2-digit',
                minute: '2-digit',
              })}
            </span>
          </button>
        ))}

        {customOpen ? (
          <div className="plan-content-custom">
            <input
              type="datetime-local"
              value={customValue}
              onChange={(event) => setCustomValue(event.target.value)}
              aria-label={t('content.pickATime')}
            />
            <button
              type="button"
              className="plan-content-option is-primary"
              disabled={saving || !customValue}
              onClick={() => void plan(new Date(customValue), t('content.pickATime'))}
            >
              {saving ? t('common.saving') : t('common.save')}
            </button>
          </div>
        ) : (
          <button
            type="button"
            className="plan-content-option"
            disabled={saving}
            onClick={() => setCustomOpen(true)}
          >
            <span className="plan-content-option-label">{t('content.pickATime')}</span>
          </button>
        )}
      </div>
      <p className="plan-content-note">{t('content.planNote', { minutes: durationMin })}</p>
      {error ? <p className="plan-content-error">{error}</p> : null}
    </BottomSheet>
  );
}
