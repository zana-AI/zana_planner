import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import type { TemplateDetail } from '../types';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';

export function TemplateDetailPage() {
  const { templateId } = useParams<{ templateId: string }>();
  const navigate = useNavigate();
  const { hapticFeedback } = useTelegramWebApp();
  const [template, setTemplate] = useState<TemplateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [subscribing, setSubscribing] = useState(false);

  useEffect(() => {
    if (templateId) {
      loadTemplate();
    }
  }, [templateId]);

  const loadTemplate = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiClient.getTemplate(templateId!);
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

  const handleSubscribe = async () => {
    if (!template || !template.unlocked) {
      hapticFeedback('warning');
      return;
    }

    setSubscribing(true);
    try {
      await apiClient.subscribeTemplate(templateId!);
      hapticFeedback('success');
      // Navigate to weekly report or show success message
      navigate('/weekly');
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

  if (error && !template) {
    return (
      <div className="app">
        <div className="error">
          <div className="error-icon">😕</div>
          <h1 className="error-title">Something went wrong</h1>
          <p className="error-message">{error}</p>
          <button className="retry-button" onClick={loadTemplate}>
            Try Again
          </button>
        </div>
      </div>
    );
  }

  if (!template) {
    return (
      <div className="app">
        <div className="error">
          <div className="error-icon">😕</div>
          <h1 className="error-title">Template not found</h1>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="page-header">
        <button className="back-button" onClick={() => navigate('/templates')}>
          ← Back
        </button>
        <h1 className="page-title">{template.title}</h1>
        <div className="template-badges">
          <span className="template-level-badge">{template.level}</span>
          <span className="template-category-badge">{template.category.replace('_', ' ')}</span>
          {template.template_kind === 'budget' && (
            <span className="template-budget-badge">Budget</span>
          )}
        </div>
      </header>

      {!template.unlocked && (
        <div className="template-locked-notice">
          <h3>🔒 This template is locked</h3>
          <p>{template.lock_reason}</p>
          {template.prerequisites.length > 0 && (
            <div className="prerequisites-list">
              <h4>Unlock requirements:</h4>
              <ul>
                {template.prerequisites.map(prereq => (
                  <li key={prereq.prereq_id}>
                    {prereq.kind === 'completed_template' && (
                      <>Complete template: {prereq.required_template_id}</>
                    )}
                    {prereq.kind === 'success_rate' && (
                      <>
                        Achieve {((prereq.min_success_rate || 0) * 100).toFixed(0)}% success on{' '}
                        {prereq.required_template_id} over {prereq.window_weeks || 4} weeks
                      </>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <main className="template-detail">
        <section className="template-section">
          <h2>Why this helps</h2>
          <p>{template.why}</p>
        </section>

        <section className="template-section">
          <h2>What "done" means</h2>
          <p>{template.done}</p>
        </section>

        <section className="template-section">
          <h2>Expected effort</h2>
          <p>{template.effort}</p>
        </section>

        <section className="template-section">
          <h2>Details</h2>
          <div className="template-details-grid">
            <div className="detail-item">
              <span className="detail-label">Target:</span>
              <span className="detail-value">
                {template.metric_type === 'count' ? (
                  <>{template.target_value}x {template.target_direction === 'at_least' ? 'or more' : 'or less'}</>
                ) : (
                  <>{template.target_value}h {template.target_direction === 'at_least' ? 'or more' : 'or less'}</>
                )}
              </span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Duration:</span>
              <span className="detail-value">
                {template.duration_type === 'week' && (
                  <>{template.duration_weeks || 1} week{template.duration_weeks !== 1 ? 's' : ''}</>
                )}
                {template.duration_type === 'one_time' && <>One-time</>}
                {template.duration_type === 'date' && <>Date-based</>}
              </span>
            </div>
          </div>
        </section>

        {template.unlocked && (
          <div className="template-actions">
            <button
              className="subscribe-button"
              onClick={handleSubscribe}
              disabled={subscribing}
            >
              {subscribing ? 'Subscribing...' : 'Subscribe to this template'}
            </button>
          </div>
        )}

        {error && (
          <div className="error-message" style={{ marginTop: '1rem', color: 'red' }}>
            {error}
          </div>
        )}
      </main>
    </div>
  );
}

