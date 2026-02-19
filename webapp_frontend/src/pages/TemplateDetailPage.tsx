import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { apiClient } from '../api/client';
import type { TemplateDetail } from '../types';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { AppLogo } from '../components/ui/AppLogo';

export function TemplateDetailPage() {
  const { templateId } = useParams<{ templateId: string }>();
  const navigate = useNavigate();
  const { hapticFeedback } = useTelegramWebApp();
  const [template, setTemplate] = useState<TemplateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [subscribing, setSubscribing] = useState(false);
  const [targetValue, setTargetValue] = useState<number | null>(null);

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
      });
      hapticFeedback('success');
      navigate('/dashboard');
    } catch (err: any) {
      console.error('Failed to subscribe:', err);
      setError(err.message || 'Failed to subscribe to template');
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
      <PageHeader title="Template Details" showBack fallbackRoute="/templates" />

      <main className="template-detail-page">
        <section className="template-detail-card">
          <div className="template-detail-title-row">
            <span className="template-detail-icon">
              <AppLogo size={24} title={template.title} />
            </span>
            <div>
              <h2 className="template-detail-title">{template.title}</h2>
              <span className="template-detail-chip">{template.category.replace('_', ' ')}</span>
            </div>
          </div>

          {template.description ? <p className="template-detail-description">{template.description}</p> : null}

          <div className="template-detail-metric">
            <strong>{template.target_value}</strong>
            <span>{template.metric_type === 'hours' ? 'hours/week' : 'times/week'}</span>
          </div>
        </section>

        <section className="template-detail-card">
          <h3 className="template-detail-section-title">Start this promise</h3>
          <label className="template-detail-input-label">Your weekly target</label>
          <div className="template-detail-input-row">
            <input
              type="number"
              step="1"
              min="1"
              value={targetValue !== null ? targetValue : template.target_value}
              onChange={(e) => setTargetValue(parseFloat(e.target.value) || template.target_value)}
              className="template-detail-input"
            />
            <span className="template-detail-input-unit">
              {template.metric_type === 'hours' ? 'hours/week' : 'times/week'}
            </span>
          </div>

          {error ? <div className="error-message">{error}</div> : null}

          <Button variant="primary" fullWidth size="lg" onClick={handleSubscribe} disabled={subscribing}>
            {subscribing ? 'Creating promise...' : 'Start Tracking'}
          </Button>
        </section>
      </main>
    </div>
  );
}
