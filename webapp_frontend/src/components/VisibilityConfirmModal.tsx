import { Globe, Lock } from 'lucide-react';

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
          <h2 className="modal-title">{isMakingPublic ? 'Share Promise Publicly' : 'Make Promise Private'}</h2>
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
              <div className="modal-warning-icon"><Globe size={20} strokeWidth={1.8} /></div>
              <div className="modal-warning-text">
                <strong>This will:</strong>
                <ul style={{ margin: '6px 0 0 0', paddingLeft: '18px', lineHeight: '1.7' }}>
                  <li>Show your progress in the <strong>community activity feed</strong></li>
                  <li>Add this promise to the <strong>promise template library</strong>, showing your activity on that template</li>
                  <li>Let others see your streak and progress</li>
                </ul>
              </div>
            </div>
          )}

          {!isMakingPublic && (
            <div className="modal-warning">
              <div className="modal-warning-icon"><Lock size={20} strokeWidth={1.8} /></div>
              <div className="modal-warning-text">
                Making this promise private will <strong>remove it from the community feed</strong> and the template library. Only you will see it.
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
              {isMakingPublic ? 'Share Publicly' : 'Make Private'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

