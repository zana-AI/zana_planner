import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import type { PromiseTemplate } from '../types';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';

export function TemplatesPage() {
  const navigate = useNavigate();
  const { hapticFeedback } = useTelegramWebApp();
  const [templates, setTemplates] = useState<PromiseTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [selectedCategory, setSelectedCategory] = useState<string>('');

  useEffect(() => {
    loadTemplates();
  }, [selectedCategory]);

  const loadTemplates = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await apiClient.getTemplates(selectedCategory || undefined);
      setTemplates(response.templates);
      hapticFeedback('success');
    } catch (err) {
      console.error('Failed to load templates:', err);
      setError('Failed to load templates');
      hapticFeedback('error');
    } finally {
      setLoading(false);
    }
  };

  const categories = Array.from(new Set(templates.map(t => t.category)));

  if (loading) {
    return (
      <div className="app">
        <div className="loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading templates...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="app">
        <div className="error">
          <div className="error-icon">😕</div>
          <h1 className="error-title">Something went wrong</h1>
          <p className="error-message">{error}</p>
          <button className="retry-button" onClick={loadTemplates}>
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="page-header">
        <h1 className="page-title">Promise Templates</h1>
        <p className="page-subtitle">Choose a template to start tracking your goals</p>
      </header>

      {categories.length > 0 && (
        <div className="category-filters">
          <button
            className={`category-filter ${selectedCategory === '' ? 'active' : ''}`}
            onClick={() => setSelectedCategory('')}
          >
            All
          </button>
          {categories.map(cat => (
            <button
              key={cat}
              className={`category-filter ${selectedCategory === cat ? 'active' : ''}`}
              onClick={() => setSelectedCategory(cat)}
            >
              {cat.replace('_', ' ')}
            </button>
          ))}
        </div>
      )}

      <main className="templates-grid">
        {templates.length === 0 ? (
          <div className="empty-state">
            <h2 className="empty-title">No templates found</h2>
            <p className="empty-subtitle">Try selecting a different category</p>
          </div>
        ) : (
          templates.map(template => (
            <div
              key={template.template_id}
              className={`template-card ${template.unlocked ? '' : 'locked'}`}
              onClick={() => {
                if (template.unlocked) {
                  navigate(`/templates/${template.template_id}`);
                } else {
                  hapticFeedback('warning');
                }
              }}
            >
              {!template.unlocked && (
                <div className="template-lock-badge">🔒 Locked</div>
              )}
              <div className="template-header">
                <h3 className="template-title">{template.title}</h3>
                <span className="template-level">{template.level}</span>
              </div>
              <p className="template-why">{template.why}</p>
              <div className="template-meta">
                <span className="template-category">{template.category.replace('_', ' ')}</span>
                {template.metric_type === 'count' ? (
                  <span className="template-metric">{template.target_value}x</span>
                ) : (
                  <span className="template-metric">{template.target_value}h</span>
                )}
              </div>
              {!template.unlocked && template.lock_reason && (
                <p className="template-lock-reason">{template.lock_reason}</p>
              )}
            </div>
          ))
        )}
      </main>
    </div>
  );
}

