import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Bookmark, Globe, Lock } from 'lucide-react';
import { apiClient } from '../api/client';
import type { TemplateDetail } from '../types';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Emoji } from '../components/ui/Emoji';

// Mirrors the backend logic: max(today + 6 months, Dec 31 of this year)
function defaultEndDate(): string {
  const today = new Date();
  const m6 = new Date(today);
  m6.setMonth(m6.getMonth() + 6);
  const eoy = new Date(today.getFullYear(), 11, 31); // Dec 31
  const result = m6 > eoy ? m6 : eoy;
  return result.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
}

export function TemplateDetailPage() {
  const { templateId } = useParams<{ templateId: string }>();
  const navigate = useNavigate();
  const { hapticFeedback } = useTelegramWebApp();
  const [template, setTemplate] = useState<TemplateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [subscribing, setSubscribing] = useState(false);
  const [targetValue, setTargetValue] = useState<number | null>(null);
  const [visibility, setVisibility] = useState<'public' | 'private'>('public');
  const endDateDisplay = defaultEndDate();

  useEffect(() => {
    if (!templateId) return;
    const loadTemplate = async () => {
      setLoading(true);
      setError('');
      try {
        const data = await apiClient.getTemplate(templateId);
        setTemplate(data);
        setTargetValue(data.target_value);
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
      await apiClient.subscribeTemplate(templateId, {
        target_value: targetValue !== null ? targetValue : undefined,
        visibility,
      });
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
          <Button variant="secondary" onClick={() => navigate('/templates')}>
            Back to Explore
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <PageHeader title="Add Promise" showBack fallbackRoute="/templates" />

      <main className="template-detail-page">
        {/* Info card — read-only */}
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
              <span className="template-detail-chip">{template.category.replace(/_/g, ' ')}</span>
            </div>
          </div>

          {template.description ? <p className="template-detail-description">{template.description}</p> : null}

          <div className="template-detail-metric">
            <strong>{template.target_value}</strong>
            <span>{template.metric_type === 'hours' ? 'hours/week' : 'times/week'}</span>
          </div>
        </section>

        {/* Configure card — consistent with PromiseCard edit form */}
        <section className="template-detail-card">
          <h3 className="template-detail-section-title">Configure your promise</h3>

          {/* Weekly target */}
          <div className="card-form-group">
            <label className="card-form-label">Weekly target</label>
            <div className="template-detail-input-row">
              <input
                type="number"
                step="1"
                min="1"
                value={targetValue !== null ? targetValue : template.target_value}
                onChange={(e) => setTargetValue(parseFloat(e.target.value) || template.target_value)}
                className="card-form-input"
              />
              <span className="template-detail-input-unit">
                {template.metric_type === 'hours' ? 'hrs / week' : 'times / week'}
              </span>
            </div>
          </div>

          {/* End date (informational) */}
          <div className="card-form-group">
            <label className="card-form-label">Runs until</label>
            <div className="card-form-date-button" style={{ cursor: 'default', opacity: 0.75 }}>
              {endDateDisplay}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'rgba(232,238,252,0.45)', marginTop: 4, display: 'block' }}>
              Auto-set to 6 months from now or end of this year, whichever is later.
            </span>
          </div>

          {/* Visibility toggle */}
          <div className="card-recurring-section" style={{ marginTop: 8 }}>
            <div className="card-recurring-info">
              <span className="card-recurring-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                {visibility === 'public'
                  ? <><Globe size={14} style={{ opacity: 0.8 }} /> Visible to community</>
                  : <><Lock size={14} style={{ opacity: 0.7 }} /> Private (only you)</>
                }
              </span>
              <span className="card-recurring-subtitle">
                {visibility === 'public'
                  ? 'Others can see your progress and be inspired.'
                  : 'Your progress is hidden from other users.'}
              </span>
            </div>
            <button
              className={`card-recurring-toggle-button ${visibility === 'public' ? 'active' : ''}`}
              onClick={() => setVisibility((v) => v === 'public' ? 'private' : 'public')}
            >
              {visibility === 'public' ? 'Make private' : 'Make public'}
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
