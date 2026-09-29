import { useTranslation } from 'react-i18next';
import { BottomSheet } from './BottomSheet';

interface ConfirmActionSheetProps {
  open: boolean;
  title: string;
  subtitle?: string;
  message: string;
  confirmLabel: string;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

export function ConfirmActionSheet({
  open, title, subtitle, message, confirmLabel, busy = false, onConfirm, onClose,
}: ConfirmActionSheetProps) {
  const { t } = useTranslation();
  const close = () => { if (!busy) onClose(); };

  return (
    <BottomSheet open={open} onClose={close} title={title} subtitle={subtitle} showClose={!busy}>
      <p className="confirm-action-message">{message}</p>
      <div className="confirm-action-buttons">
        <button type="button" className="btn btn-ghost" onClick={close} disabled={busy}>
          {t('common.cancel')}
        </button>
        <button type="button" className="btn btn-primary" onClick={onConfirm} disabled={busy}>
          {confirmLabel}
        </button>
      </div>
    </BottomSheet>
  );
}
