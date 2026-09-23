import { useTranslation } from 'react-i18next';

interface RemoveContentConfirmModalProps {
  isOpen: boolean;
  title: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Confirms the swipe-to-delete gesture on a library card. Same look as
 * PromiseDeleteConfirmModal — one confirm-delete pattern across the app. */
export function RemoveContentConfirmModal({ isOpen, title, onConfirm, onCancel }: RemoveContentConfirmModalProps) {
  const { t } = useTranslation();
  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content" onClick={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">{t('content.removeFromLibrary')}</h2>
          <button className="modal-close" onClick={onCancel} aria-label={t('common.close')}>×</button>
        </div>
        <div className="modal-form">
          <div className="modal-form-group">
            <p className="modal-message">{t('content.removeConfirmMessage')}</p>
            <p className="modal-message" style={{ marginTop: '8px', opacity: 0.85 }}>{title}</p>
          </div>
          <div className="modal-actions">
            <button type="button" className="modal-button modal-button-secondary" onClick={onCancel}>
              {t('common.cancel')}
            </button>
            <button type="button" className="modal-button modal-button-danger" onClick={onConfirm}>
              {t('common.delete')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
