import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import type { PromiseTemplate } from '../types';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';

interface TemplateUser {
  user_id: string;
  first_name?: string;
  username?: string;
  avatar_path?: string;
  avatar_file_unique_id?: string;
}

export function TemplatesPage() {
  const navigate = useNavigate();
  const { hapticFeedback } = useTelegramWebApp();
  const [templates, setTemplates] = useState<PromiseTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [templateUsers, setTemplateUsers] = useState<Record<string, TemplateUser[]>>({});

  useEffect(() => {
    loadTemplates();
  }, [selectedCategory]);

  useEffect(() => {
    // Load users for each template
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
          <div className="loading-text">Loading promise marketplace...</div>
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
        <h1 className="page-title">Promise Marketplace</h1>
        <p className="page-subtitle">Choose a promise from the marketplace to start tracking your goals</p>
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
            <h2 className="empty-title">No promises found in marketplace</h2>
            <p className="empty-subtitle">Try selecting a different category</p>
          </div>
        ) : (
          templates.map(template => (
            <div
              key={template.template_id}
              className="template-card"
              onClick={() => {
                // Allow navigation regardless of lock status (locked UI hidden)
                navigate(`/templates/${template.template_id}`);
              }}
            >
              {/* Locked and Budget badges hidden per requirements */}
              {/* {!template.unlocked && (
                <div className="template-lock-badge">🔒 Locked</div>
              )}
              {template.template_kind === 'budget' && (
                <div style={{
                  position: 'absolute',
                  top: '8px',
                  right: '8px',
                  padding: '4px 8px',
                  background: 'rgba(255, 68, 68, 0.2)',
                  border: '1px solid rgba(255, 68, 68, 0.4)',
                  borderRadius: '6px',
                  fontSize: '0.7rem',
                  fontWeight: '600',
                  color: '#ff6b6b'
                }}>
                  📉 Budget
                </div>
              )} */}
              <div className="template-header">
                <span style={{ fontSize: '1.75rem', marginRight: '0.5rem' }}>{template.emoji || '🎯'}</span>
                <h3 className="template-title">{template.title}</h3>
              </div>
              {template.description && (
                <p className="template-why">{template.description}</p>
              )}
              <div className="template-meta">
                <span className="template-category">{template.category.replace('_', ' ')}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="template-metric">
                    {template.target_value} {template.metric_type === 'hours' ? 'hrs' : '×'}/week
                  </span>
                </div>
              </div>
              {templateUsers[template.template_id] && templateUsers[template.template_id].length > 0 && (
                <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                  {templateUsers[template.template_id].slice(0, 6).map((user) => (
                    <div
                      key={user.user_id}
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
                        fontWeight: '500'
                      }}
                      title={user.first_name || user.username || `User ${user.user_id}`}
                    >
                      {user.avatar_path ? (
                        <img
                          src={user.avatar_path}
                          alt={user.first_name || user.username || ''}
                          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                        />
                      ) : (
                        (user.first_name || user.username || 'U').charAt(0).toUpperCase()
                      )}
                    </div>
                  ))}
                  {templateUsers[template.template_id].length > 6 && (
                    <span style={{ fontSize: '0.75rem', color: 'rgba(232, 238, 252, 0.6)' }}>
                      +{templateUsers[template.template_id].length - 6}
                    </span>
                  )}
                </div>
              )}
              {/* Difficulty level indicator hidden per requirements */}
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
              {/* Lock reason hidden per requirements */}
              {/* {!template.unlocked && template.lock_reason && (
                <p className="template-lock-reason">{template.lock_reason}</p>
              )} */}
            </div>
          ))
        )}
      </main>
    </div>
  );
}

