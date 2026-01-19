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
  const [targetValue, setTargetValue] = useState<number | null>(null);

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
      await apiClient.subscribeTemplate(templateId!, {
        target_value: targetValue !== null ? targetValue : undefined
      });
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

  useEffect(() => {
    if (template) {
      setTargetValue(template.target_value);
    }
  }, [template]);

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
          {/* Difficulty level indicator and Budget badge hidden per requirements */}
          {/* <div className="template-level-indicator">
            {[1, 2, 3].map((num) => {
              const levelNum = parseInt(template.level.replace('L', '')) || 0;
              const isFilled = num <= levelNum;
              let fillColor = 'rgba(232, 238, 252, 0.15)';
              let borderColor = 'rgba(232, 238, 252, 0.3)';
              
              if (isFilled) {
                if (levelNum === 1) {
                  // L1: green
                  fillColor = '#22c55e';
                  borderColor = '#22c55e';
                } else if (levelNum === 2) {
                  // L2: orange
                  fillColor = '#f59e0b';
                  borderColor = '#f59e0b';
                } else if (levelNum === 3) {
                  // L3: red
                  fillColor = '#ef4444';
                  borderColor = '#ef4444';
                }
              }
              
              return (
                <div
                  key={num}
                  className="template-level-square"
                  style={{
                    backgroundColor: fillColor,
                    border: `1px solid ${borderColor}`
                  }}
                />
              );
            })}
          </div> */}
          <span className="template-category-badge">{template.category.replace('_', ' ')}</span>
          {/* {template.template_kind === 'budget' && (
            <span className="template-budget-badge">Budget</span>
          )} */}
        </div>
      </header>

      {/* Locked notice hidden per requirements */}
      {/* {!template.unlocked && (
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
      )} */}

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
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem' }}>
                {template.metric_type === 'hours' ? 'Time commitment (hours/week)' : 'Target value'}
              </label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                value={targetValue !== null ? targetValue : template.target_value}
                onChange={(e) => setTargetValue(parseFloat(e.target.value) || template.target_value)}
                style={{
                  width: '100%',
                  padding: '0.5rem',
                  borderRadius: '6px',
                  border: '1px solid rgba(232, 238, 252, 0.2)',
                  background: 'rgba(11, 16, 32, 0.6)',
                  color: '#fff',
                  fontSize: '1rem'
                }}
              />
              <p style={{ marginTop: '0.25rem', fontSize: '0.85rem', color: 'rgba(232, 238, 252, 0.6)' }}>
                Default: {template.target_value} {template.metric_type === 'hours' ? 'hours/week' : 'times/week'}
              </p>
            </div>
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

