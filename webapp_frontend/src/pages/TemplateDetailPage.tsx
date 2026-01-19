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
    if (!template) {
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
      </header>

      <main className="template-detail" style={{ paddingTop: '1rem' }}>
        {/* Template Header Card */}
        <div style={{
          background: 'rgba(15, 23, 48, 0.8)',
          borderRadius: '16px',
          padding: '1.5rem',
          marginBottom: '1.5rem',
          border: '1px solid rgba(232, 238, 252, 0.1)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
            <span style={{ fontSize: '3rem' }}>{template.emoji || '🎯'}</span>
            <div>
              <h1 style={{ margin: 0, fontSize: '1.5rem', color: '#fff' }}>{template.title}</h1>
              <span style={{
                display: 'inline-block',
                marginTop: '0.5rem',
                padding: '0.25rem 0.75rem',
                background: 'rgba(102, 126, 234, 0.2)',
                borderRadius: '12px',
                fontSize: '0.8rem',
                color: 'rgba(232, 238, 252, 0.8)'
              }}>
                {template.category.replace('_', ' ')}
              </span>
            </div>
          </div>

          {template.description && (
            <p style={{
              margin: 0,
              color: 'rgba(232, 238, 252, 0.7)',
              fontSize: '0.95rem',
              lineHeight: 1.5
            }}>
              {template.description}
            </p>
          )}

          <div style={{
            marginTop: '1rem',
            padding: '1rem',
            background: 'rgba(0, 0, 0, 0.2)',
            borderRadius: '10px',
            display: 'flex',
            justifyContent: 'center',
            gap: '2rem'
          }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '1.5rem', fontWeight: '700', color: '#5ba3f5' }}>
                {template.target_value}
              </div>
              <div style={{ fontSize: '0.8rem', color: 'rgba(232, 238, 252, 0.5)' }}>
                {template.metric_type === 'hours' ? 'hours/week' : 'times/week'}
              </div>
            </div>
          </div>
        </div>

        {/* Subscribe Section */}
        <div style={{
          background: 'rgba(15, 23, 48, 0.8)',
          borderRadius: '16px',
          padding: '1.5rem',
          border: '1px solid rgba(232, 238, 252, 0.1)'
        }}>
          <h2 style={{ margin: '0 0 1rem 0', fontSize: '1.1rem', color: '#fff' }}>
            Start this habit
          </h2>

          <div style={{ marginBottom: '1.25rem' }}>
            <label style={{
              display: 'block',
              marginBottom: '0.5rem',
              color: 'rgba(232, 238, 252, 0.7)',
              fontSize: '0.9rem'
            }}>
              Your weekly target
            </label>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <input
                type="number"
                step="1"
                min="1"
                value={targetValue !== null ? targetValue : template.target_value}
                onChange={(e) => setTargetValue(parseFloat(e.target.value) || template.target_value)}
                style={{
                  flex: 1,
                  padding: '0.75rem',
                  borderRadius: '8px',
                  border: '1px solid rgba(232, 238, 252, 0.15)',
                  background: 'rgba(11, 16, 32, 0.6)',
                  color: '#fff',
                  fontSize: '1.1rem',
                  textAlign: 'center'
                }}
              />
              <span style={{ color: 'rgba(232, 238, 252, 0.6)', fontSize: '0.9rem' }}>
                {template.metric_type === 'hours' ? 'hours/week' : 'times/week'}
              </span>
            </div>
          </div>

          <button
            className="subscribe-button"
            onClick={handleSubscribe}
            disabled={subscribing}
            style={{
              width: '100%',
              padding: '1rem',
              background: subscribing ? 'rgba(102, 126, 234, 0.3)' : 'linear-gradient(135deg, #667eea, #764ba2)',
              border: 'none',
              borderRadius: '10px',
              color: '#fff',
              fontSize: '1rem',
              fontWeight: '600',
              cursor: subscribing ? 'not-allowed' : 'pointer'
            }}
          >
            {subscribing ? 'Creating promise...' : '✨ Start Tracking'}
          </button>

          {error && (
            <div style={{
              marginTop: '1rem',
              padding: '0.75rem',
              background: 'rgba(255, 107, 107, 0.1)',
              borderRadius: '8px',
              color: '#ff6b6b',
              fontSize: '0.9rem'
            }}>
              {error}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

