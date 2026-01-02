interface VisibilityConfirmModalProps {
  isOpen: boolean;
  currentVisibility: 'private' | 'public';
  newVisibility: 'private' | 'public';
  onConfirm: () => void;
  onCancel: () => void;
}

export function VisibilityConfirmModal({
  isOpen,
  currentVisibility,
  newVisibility,
  onConfirm,
  onCancel,
}: VisibilityConfirmModalProps) {
  if (!isOpen) return null;

  const isMakingPublic = newVisibility === 'public';
  const visibilityLabels = {
    private: 'Private',
    public: 'Public',
  };

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">Change Visibility</h2>
          <button className="modal-close" onClick={onCancel}>
            ×
          </button>
        </div>
        
        <div className="modal-form">
          <div className="modal-form-group">
            <p className="modal-message">
              Are you sure you want to change this promise from{' '}
              <strong>{visibilityLabels[currentVisibility]}</strong> to{' '}
              <strong>{visibilityLabels[newVisibility]}</strong>?
            </p>
          </div>

          {isMakingPublic && (
            <div className="modal-warning">
              <div className="modal-warning-icon">⚠️</div>
              <div className="modal-warning-text">
                Making this promise public will make it visible to everyone. 
                Others will be able to see your progress and activity.
              </div>
            </div>
          )}

          <div className="modal-actions">
            <button
              type="button"
              className="modal-button modal-button-secondary"
              onClick={onCancel}
            >
              Cancel
            </button>
            <button
              type="button"
              className="modal-button modal-button-primary"
              onClick={onConfirm}
            >
              Confirm
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

