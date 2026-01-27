import React from 'react';

interface DeleteConfirmModalProps {
  templateId: string;
  templateTitle: string;
  onConfirm: () => void;
  onCancel: () => void;
  confirmText: string;
  onConfirmTextChange: (text: string) => void;
}

export function DeleteConfirmModal({
  templateId,
  templateTitle,
  onConfirm,
  onCancel,
  confirmText,
  onConfirmTextChange,
}: DeleteConfirmModalProps) {
  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0, 0, 0, 0.7)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000
    }}>
      <div style={{
        background: 'rgba(15, 23, 48, 0.98)',
        border: '1px solid rgba(232, 238, 252, 0.2)',
        borderRadius: '12px',
        padding: '1.5rem',
        maxWidth: '400px',
        width: '90%'
      }}>
        <h3 style={{ marginTop: 0, color: '#ff6b6b' }}>Delete Template</h3>
        <p style={{ color: 'rgba(232, 238, 252, 0.8)', marginBottom: '1rem' }}>
          Are you sure you want to delete <strong>{templateTitle}</strong>?
        </p>
        <p style={{ color: 'rgba(232, 238, 252, 0.6)', fontSize: '0.85rem', marginBottom: '1rem' }}>
          This action cannot be undone. Type the template ID to confirm:
        </p>
        <input
          type="text"
          value={confirmText}
          onChange={(e) => onConfirmTextChange(e.target.value)}
          placeholder={templateId}
          style={{
            width: '100%',
            padding: '0.5rem',
            borderRadius: '6px',
            border: '1px solid rgba(232, 238, 252, 0.2)',
            background: 'rgba(11, 16, 32, 0.6)',
            color: '#fff',
            marginBottom: '1rem'
          }}
        />
        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
          <button
            onClick={onCancel}
            style={{
              padding: '0.5rem 1rem',
              background: 'rgba(232, 238, 252, 0.1)',
              border: '1px solid rgba(232, 238, 252, 0.2)',
              borderRadius: '6px',
              color: '#fff',
              cursor: 'pointer'
            }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={confirmText !== templateId}
            style={{
              padding: '0.5rem 1rem',
              background: confirmText === templateId ? '#ff6b6b' : 'rgba(255, 107, 107, 0.3)',
              border: 'none',
              borderRadius: '6px',
              color: '#fff',
              cursor: confirmText === templateId ? 'pointer' : 'not-allowed',
              opacity: confirmText === templateId ? 1 : 0.5
            }}
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
