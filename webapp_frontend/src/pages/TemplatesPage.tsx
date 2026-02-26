import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bookmark } from 'lucide-react';
import { apiClient } from '../api/client';
import type { PromiseTemplate } from '../types';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import { PageHeader } from '../components/ui/PageHeader';
import { Emoji } from '../components/ui/Emoji';
import { AvatarStack } from '../components/ui/AvatarStack';
import type { AvatarStackUser } from '../components/ui/AvatarStack';

type TemplateUser = AvatarStackUser;

export function TemplatesPage() {
  const navigate = useNavigate();
  const { hapticFeedback } = useTelegramWebApp();
  const [templates, setTemplates] = useState<PromiseTemplate[]>([]);
  const [allCategories, setAllCategories] = useState<string[]>([]);
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
        setAllCategories((prev) => {
          const next = new Set(prev);
          response.templates.forEach((template) => next.add(template.category));
          return Array.from(next).sort((a, b) => a.localeCompare(b));
        });
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

  const categories = allCategories;
  const formatCategoryLabel = (category: string) =>
    category
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (match) => match.toUpperCase());

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
              {formatCategoryLabel(category)}
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
                  {(templateUsers[template.template_id] ?? []).length > 0 ? (
                    <AvatarStack users={templateUsers[template.template_id]} size={20} max={3} />
                  ) : template.emoji ? (
                    <Emoji emoji={template.emoji} size={20} />
                  ) : (
                    <Bookmark size={16} strokeWidth={1.8} color="rgba(237,243,255,0.45)" />
                  )}
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
              {(templateUsers[template.template_id] ?? []).length > 0 && (
                <div className="template-card-users">
                  <span className="template-card-users-label">
                    {templateUsers[template.template_id].length === 1
                      ? '1 person doing this'
                      : `${templateUsers[template.template_id].length} people doing this`}
                  </span>
                </div>
              )}
            </div>
          ))
        )}
      </main>
    </div>
  );
}
