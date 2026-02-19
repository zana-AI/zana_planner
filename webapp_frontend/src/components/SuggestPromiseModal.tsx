import { useEffect, useState } from 'react';
import { Library, PenSquare, X } from 'lucide-react';
import { apiClient, ApiError } from '../api/client';
import { useModalBodyLock } from '../hooks/useModalBodyLock';
import type { CreateSuggestionRequest, PromiseTemplate } from '../types';

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

  const isSubmitDisabled =
    loading ||
    (mode === 'template' && !selectedTemplateId) ||
    (mode === 'freeform' && !freeformText.trim());

  const handleSubmit = async () => {
    if (mode === 'template' && !selectedTemplateId) {
      setError('Please select a template.');
      return;
    }

    if (mode === 'freeform' && !freeformText.trim()) {
      setError('Please enter a promise description.');
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
        setError('Failed to send suggestion.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content suggest-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="modal-header">
          <h2 className="modal-title">Suggest Promise</h2>
          <button className="modal-close" type="button" onClick={onClose} aria-label="Close suggest promise dialog">
            <X size={18} />
          </button>
        </div>

        <form
          className="modal-form"
          onSubmit={(e) => {
            e.preventDefault();
            handleSubmit();
          }}
        >
          <div className="modal-form-group">
            <label className="modal-label">Send to</label>
            <div className="modal-promise-text">{toUserName}</div>
          </div>

          <div className="modal-form-group">
            <label className="modal-label">Suggestion source</label>
            <div className="suggest-mode-toggle">
              <button
                type="button"
                className={`suggest-mode-button ${mode === 'template' ? 'active' : ''}`}
                onClick={() => setMode('template')}
                disabled={loading}
              >
                <Library size={14} />
                Template Library
              </button>
              <button
                type="button"
                className={`suggest-mode-button ${mode === 'freeform' ? 'active' : ''}`}
                onClick={() => setMode('freeform')}
                disabled={loading}
              >
                <PenSquare size={14} />
                Custom Text
              </button>
            </div>
          </div>

          {mode === 'template' ? (
            <div className="modal-form-group">
              <label className="modal-label" htmlFor="suggest-template-id">
                Select template
              </label>
              {loadingTemplates ? (
                <div className="suggest-modal-loading">Loading templates...</div>
              ) : (
                <select
                  id="suggest-template-id"
                  value={selectedTemplateId}
                  onChange={(e) => setSelectedTemplateId(e.target.value)}
                  className="modal-input"
                  disabled={loading}
                >
                  <option value="">Select a template</option>
                  {templates.map((template) => (
                    <option key={template.template_id} value={template.template_id}>
                      {template.title}
                    </option>
                  ))}
                </select>
              )}
            </div>
          ) : (
            <div className="modal-form-group">
              <label className="modal-label" htmlFor="suggest-freeform-text">
                Promise description
              </label>
              <textarea
                id="suggest-freeform-text"
                value={freeformText}
                onChange={(e) => setFreeformText(e.target.value)}
                placeholder="e.g., Take medicine every morning at 8 AM"
                rows={3}
                className="modal-input"
                disabled={loading}
              />
            </div>
          )}

          <div className="modal-form-group">
            <label className="modal-label" htmlFor="suggest-message">
              Personal message (optional)
            </label>
            <textarea
              id="suggest-message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Add a personal message"
              rows={2}
              className="modal-input"
              disabled={loading}
            />
          </div>

          {error ? <div className="modal-error">{error}</div> : null}

          <div className="modal-actions">
            <button className="modal-button modal-button-secondary" type="button" onClick={onClose} disabled={loading}>
              Cancel
            </button>
            <button className="modal-button modal-button-primary" type="submit" disabled={isSubmitDisabled}>
              {loading ? 'Sending...' : 'Send Suggestion'}
            </button>
          </div>

          <p className="suggest-modal-note">Suggestions appear in the recipient's inbox for review.</p>
        </form>
      </div>
    </div>
  );
}