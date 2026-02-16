import { useState, useEffect } from 'react';
import { apiClient, ApiError } from '../api/client';
import { useModalBodyLock } from '../hooks/useModalBodyLock';
import type { PromiseTemplate, CreateSuggestionRequest } from '../types';

interface SuggestPromiseModalProps {
  toUserId: string;
  toUserName: string;
  onClose: () => void;
  onSuccess: () => void;
}

export function SuggestPromiseModal({ toUserId, toUserName, onClose, onSuccess }: SuggestPromiseModalProps) {
  const [mode, setMode] = useState<'template' | 'freeform'>('template');
  const [templates, setTemplates] = useState<PromiseTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('');
  const [freeformText, setFreeformText] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [loadingTemplates, setLoadingTemplates] = useState(true);

  useModalBodyLock(true);

  useEffect(() => {
    const loadTemplates = async () => {
      try {
        const data = await apiClient.getTemplates();
        setTemplates(data.templates || []);
      } catch (err) {
        console.error('Failed to load templates:', err);
      } finally {
        setLoadingTemplates(false);
      }
    };
    loadTemplates();
  }, []);

  const handleSubmit = async () => {
    if (mode === 'template' && !selectedTemplateId) {
      setError('Please select a template');
      return;
    }
    if (mode === 'freeform' && !freeformText.trim()) {
      setError('Please enter a promise description');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const request: CreateSuggestionRequest = {
        to_user_id: toUserId,
        message: message.trim() || undefined,
      };

      if (mode === 'template') {
        request.template_id = selectedTemplateId;
      } else {
        request.freeform_text = freeformText.trim();
      }

      await apiClient.createSuggestion(request);
      onSuccess();
      onClose();
    } catch (err) {
      console.error('Failed to create suggestion:', err);
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to send suggestion');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Suggest Promise to {toUserName}</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        <div className="modal-body">
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)' }}>
              Suggest from:
            </label>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                className={mode === 'template' ? 'button-primary' : 'button-secondary'}
                onClick={() => setMode('template')}
                style={{ flex: 1 }}
              >
                Marketplace Template
              </button>
              <button
                className={mode === 'freeform' ? 'button-primary' : 'button-secondary'}
                onClick={() => setMode('freeform')}
                style={{ flex: 1 }}
              >
                Freeform Text
              </button>
            </div>
          </div>

          {mode === 'template' ? (
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)' }}>
                Select Template:
              </label>
              {loadingTemplates ? (
                <div>Loading templates...</div>
              ) : (
                <select
                  value={selectedTemplateId}
                  onChange={(e) => setSelectedTemplateId(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.5rem',
                    borderRadius: '6px',
                    border: '1px solid rgba(232, 238, 252, 0.2)',
                    background: 'rgba(11, 16, 32, 0.6)',
                    color: '#fff',
                    fontSize: '1rem'
                  }}
                >
                  <option value="">-- Select a template --</option>
                  {templates.map((t) => (
                    <option key={t.template_id} value={t.template_id}>
                      {t.title}
                    </option>
                  ))}
                </select>
              )}
            </div>
          ) : (
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)' }}>
                Promise Description:
              </label>
              <textarea
                value={freeformText}
                onChange={(e) => setFreeformText(e.target.value)}
                placeholder="e.g., Take medicine every morning at 8 AM"
                rows={3}
                style={{
                  width: '100%',
                  padding: '0.5rem',
                  borderRadius: '6px',
                  border: '1px solid rgba(232, 238, 252, 0.2)',
                  background: 'rgba(11, 16, 32, 0.6)',
                  color: '#fff',
                  fontSize: '1rem',
                  fontFamily: 'inherit'
                }}
              />
            </div>
          )}

          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)' }}>
              Optional Message:
            </label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Add a personal message (optional)"
              rows={2}
              style={{
                width: '100%',
                padding: '0.5rem',
                borderRadius: '6px',
                border: '1px solid rgba(232, 238, 252, 0.2)',
                background: 'rgba(11, 16, 32, 0.6)',
                color: '#fff',
                fontSize: '1rem',
                fontFamily: 'inherit'
              }}
            />
          </div>

          {error && (
            <div style={{ color: '#ff6b6b', marginBottom: '1rem', fontSize: '0.9rem' }}>
              {error}
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button className="button-secondary" onClick={onClose} disabled={loading}>
            Cancel
          </button>
          <button
            className="button-primary"
            onClick={handleSubmit}
            disabled={loading || (mode === 'template' && !selectedTemplateId) || (mode === 'freeform' && !freeformText.trim())}
          >
            {loading ? 'Sending...' : 'Send Suggestion'}
          </button>
        </div>
      </div>
    </div>
  );
}
