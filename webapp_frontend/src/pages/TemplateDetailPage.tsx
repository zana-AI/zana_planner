import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Bookmark } from 'lucide-react';
import { apiClient } from '../api/client';
import type { TemplateDetail } from '../types';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import { Button } from '../components/ui/Button';
import { Emoji } from '../components/ui/Emoji';

export function TemplateDetailPage() {
  const { templateId } = useParams<{ templateId: string }>();
  const navigate = useNavigate();
  const { hapticFeedback } = useTelegramWebApp();
  const [template, setTemplate] = useState<TemplateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [subscribing, setSubscribing] = useState(false);
  const [visibility, setVisibility] = useState<'public' | 'private'>('public');

  useEffect(() => {
    if (!templateId) return;
    const loadTemplate = async () => {
      setLoading(true);
      setError('');
      try {
        const data = await apiClient.getTemplate(templateId);
        setTemplate(data);
        hapticFeedback('success');
      } catch (err) {
        console.error('Failed to load template:', err);
        setError('Failed to load template');
        hapticFeedback('error');
      } finally {
        setLoading(false);
      }
    };
    loadTemplate();
  }, [templateId, hapticFeedback]);

  const handleSubscribe = async () => {
    if (!template || !templateId) return;

    setSubscribing(true);
    setError('');
    try {
      // Target and end date use the template defaults — no setup needed.
      await apiClient.subscribeTemplate(templateId, { visibility });
      hapticFeedback('success');
      navigate('/dashboard');
    } catch (err: any) {
      console.error('Failed to subscribe:', err);
      setError(err.message || 'Failed to add promise');
      hapticFeedback('error');
    } finally {
      setSubscribing(false);
    }
  };

  if (loading) {
    return (
      <div className="app">
        <div className="loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading template...</div>
        </div>
      </div>
    );
  }

  if (!template) {
    return (
      <div className="app">
        <div className="error">
          <div className="error-icon">!</div>
          <h1 className="error-title">Template not found</h1>
          <p className="error-message">{error || 'The selected template does not exist.'}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <main className="template-detail-page">
        <section className="template-detail-card">
          <div className="template-detail-title-row">
            <span className="template-detail-icon">
              {template.emoji ? (
                <Emoji emoji={template.emoji} size={28} />
              ) : (
                <Bookmark size={22} strokeWidth={1.8} color="rgba(237,243,255,0.45)" />
              )}
            </span>
            <div>
              <h2 className="template-detail-title">{template.title}</h2>
            </div>
          </div>

          {template.description ? <p className="template-detail-description">{template.description}</p> : null}

          {/* Visibility — the only choice; everything else uses sensible defaults. */}
          <div className="card-setting-row" style={{ marginTop: 12 }}>
            <div className="card-setting-info">
              <span className="card-setting-title">Public visibility</span>
              <span className="card-setting-subtitle">
                {visibility === 'public'
                  ? 'Visible to community — others can be inspired.'
                  : 'Only visible to you.'}
              </span>
            </div>
            <button
              type="button"
              className={`card-switch${visibility === 'public' ? ' card-switch--on' : ''}`}
              onClick={() => setVisibility((v) => (v === 'public' ? 'private' : 'public'))}
              aria-pressed={visibility === 'public'}
            >
              <span className="card-switch-track" aria-hidden="true">
                <span className="card-switch-thumb" />
              </span>
              <span className="card-switch-label">{visibility === 'public' ? 'Public' : 'Private'}</span>
            </button>
          </div>

          {error ? <div className="error-message" style={{ marginTop: 10 }}>{error}</div> : null}

          <div style={{ marginTop: 16 }}>
            <Button variant="primary" fullWidth size="lg" onClick={handleSubscribe} disabled={subscribing}>
              {subscribing ? 'Adding…' : 'Add to My Promises'}
            </Button>
          </div>
        </section>
      </main>
    </div>
  );
}
