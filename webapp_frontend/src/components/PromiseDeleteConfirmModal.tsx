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
  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={isDeleting ? undefined : onCancel}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">Delete Promise</h2>
          <button className="modal-close" onClick={onCancel} disabled={isDeleting} aria-label="Close">
            x
          </button>
        </div>

        <div className="modal-form">
          <div className="modal-form-group">
            <p className="modal-message">
              Are you sure you want to delete this promise?
            </p>
            <p className="modal-message" style={{ marginTop: '8px', opacity: 0.85 }}>
              <strong>#{promiseId}</strong> {promiseText.replace(/_/g, ' ')}
            </p>
          </div>

          <div className="modal-warning">
            <div className="modal-warning-icon">!</div>
            <div className="modal-warning-text">
              This action cannot be undone.
            </div>
          </div>

          <div className="modal-actions">
            <button
              type="button"
              className="modal-button modal-button-secondary"
              onClick={onCancel}
              disabled={isDeleting}
            >
              Cancel
            </button>
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
