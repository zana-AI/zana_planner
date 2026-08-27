import { useTranslation } from 'react-i18next';
interface PromiseDeleteConfirmModalProps {
  isOpen: boolean;
  promiseId: string;
  promiseText: string;
  isDeleting?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function PromiseDeleteConfirmModal({
  isOpen,
  promiseId,
  promiseText,
  isDeleting = false,
  onConfirm,
  onCancel,
}: PromiseDeleteConfirmModalProps) {
  const { t } = useTranslation();
  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={isDeleting ? undefined : onCancel}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">{t('promiseDelete.deletePromise')}</h2>
          <button className="modal-close" onClick={onCancel} disabled={isDeleting} aria-label={t('promiseDelete.close')}>
            x
          </button>
        </div>

        <div className="modal-form">
          <div className="modal-form-group">
            <p className="modal-message">{t('promiseDelete.areYouSureYouWantToDeleteThisPromise')}</p>
            <p className="modal-message" style={{ marginTop: '8px', opacity: 0.85 }}>
              <strong>#{promiseId}</strong> {promiseText.replace(/_/g, ' ')}
            </p>
          </div>

          <div className="modal-warning">
            <div className="modal-warning-icon">!</div>
            <div className="modal-warning-text">{t('promiseDelete.thisActionCannotBeUndone')}</div>
          </div>

          <div className="modal-actions">
            <button
              type="button"
              className="modal-button modal-button-secondary"
              onClick={onCancel}
              disabled={isDeleting}
            >{t('promiseDelete.cancel')}</button>
            <button
              type="button"
              className="modal-button modal-button-danger"
              onClick={onConfirm}
              disabled={isDeleting}
            >
              {isDeleting ? 'Deleting...' : 'Delete'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
