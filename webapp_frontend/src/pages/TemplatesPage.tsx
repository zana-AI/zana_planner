import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import type { PromiseTemplate } from '../types';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import { PageHeader } from '../components/ui/PageHeader';
import { AppLogo } from '../components/ui/AppLogo';

interface TemplateUser {
  user_id: string;
  first_name?: string;
  username?: string;
  avatar_path?: string;
}

export function TemplatesPage() {
  const navigate = useNavigate();
  const { hapticFeedback } = useTelegramWebApp();
  const [templates, setTemplates] = useState<PromiseTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');
  const [templateUsers, setTemplateUsers] = useState<Record<string, TemplateUser[]>>({});

  useEffect(() => {
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
    loadTemplates();
  }, [selectedCategory, hapticFeedback]);

  useEffect(() => {
    const loadTemplateUsers = async () => {
      const usersMap: Record<string, TemplateUser[]> = {};
      for (const template of templates) {
        try {
          const response = await apiClient.getTemplateUsers(template.template_id, 8);
          usersMap[template.template_id] = response.users;
        } catch (err) {
          console.error(`Failed to load users for template ${template.template_id}:`, err);
          usersMap[template.template_id] = [];
        }
      }
      setTemplateUsers(usersMap);
    };
    if (templates.length > 0) {
      loadTemplateUsers();
    }
  }, [templates]);

  const categories = Array.from(new Set(templates.map((template) => template.category)));

  if (loading) {
    return (
      <div className="app">
        <div className="loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading promise library...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="app">
        <div className="error">
          <div className="error-icon">!</div>
          <h1 className="error-title">Something went wrong</h1>
          <p className="error-message">{error}</p>
          <button className="retry-button" onClick={() => window.location.reload()}>
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <PageHeader title="Explore" subtitle="Promise library and marketplace" />

      {categories.length > 0 ? (
        <div className="category-filters">
          <button className={`category-filter ${selectedCategory === '' ? 'active' : ''}`} onClick={() => setSelectedCategory('')}>
            All
          </button>
          {categories.map((category) => (
            <button
              key={category}
              className={`category-filter ${selectedCategory === category ? 'active' : ''}`}
              onClick={() => setSelectedCategory(category)}
            >
              {category.replace('_', ' ')}
            </button>
          ))}
        </div>
      ) : null}

      <main className="templates-grid">
        {templates.length === 0 ? (
          <div className="empty-state">
            <h2 className="empty-title">No promises found in library</h2>
            <p className="empty-subtitle">Try selecting a different category</p>
          </div>
        ) : (
          templates.map((template) => (
            <div key={template.template_id} className="template-card" onClick={() => navigate(`/templates/${template.template_id}`)}>
              <div className="template-header">
                <span className="template-list-logo">
                  <AppLogo size={20} title={template.title} />
                </span>
                <h3 className="template-title">{template.title}</h3>
              </div>
              {template.description ? <p className="template-why">{template.description}</p> : null}
              <div className="template-meta">
                <span className="template-category">{template.category.replace('_', ' ')}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="template-metric">
                    {template.target_value} {template.metric_type === 'hours' ? 'hrs' : 'times'}/week
                  </span>
                </div>
              </div>
              {templateUsers[template.template_id] && templateUsers[template.template_id].length > 0 ? (
                <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                  {templateUsers[template.template_id].slice(0, 6).map((templateUser) => (
                    <div
                      key={templateUser.user_id}
                      style={{
                        width: '24px',
                        height: '24px',
                        borderRadius: '50%',
                        overflow: 'hidden',
                        border: '2px solid rgba(232, 238, 252, 0.2)',
                        background: 'rgba(232, 238, 252, 0.1)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '10px',
                        color: '#fff',
                        fontWeight: '500',
                      }}
                      title={templateUser.first_name || templateUser.username || `User ${templateUser.user_id}`}
                    >
                      {templateUser.avatar_path ? (
                        <img src={templateUser.avatar_path} alt={templateUser.first_name || templateUser.username || ''} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                      ) : (
                        (templateUser.first_name || templateUser.username || 'U').charAt(0).toUpperCase()
                      )}
                    </div>
                  ))}
                  {templateUsers[template.template_id].length > 6 ? (
                    <span style={{ fontSize: '0.75rem', color: 'rgba(232, 238, 252, 0.6)' }}>
                      +{templateUsers[template.template_id].length - 6}
                    </span>
                  ) : null}
                </div>
              ) : null}
            </div>
          ))
        )}
      </main>
    </div>
  );
}
