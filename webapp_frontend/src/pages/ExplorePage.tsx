import { useTranslation } from 'react-i18next';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import type { ExploreCategory } from '../types';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import { topicLabel } from './exploreVocabulary';
import './explore.css';

/**
 * The root of Explore: subject tiles, and nothing else.
 *
 * Everything used to render on one scroll — every category, every topic, every
 * item — which was already long at eleven items. A subject is the only thing
 * that belongs at the root, because it is the only question a person can answer
 * before they know what is inside: what am I working on?
 */
export function ExplorePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { hapticFeedback } = useTelegramWebApp();
  const [categories, setCategories] = useState<ExploreCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    apiClient
      .getExploreCatalog()
      .then((catalog) => {
        if (!active) return;
        setCategories(catalog.categories.filter((category) => category.topics.some((topic) => topic.items.length > 0)));
        hapticFeedback('success');
      })
      .catch((err) => {
        console.error('Failed to load Explore:', err);
        if (!active) return;
        setError(t('templates.loadFailed'));
        hapticFeedback('error');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [hapticFeedback, t]);

  if (loading) {
    return (
      <div className="app">
        <div className="loading">
          <div className="loading-spinner" />
          <div className="loading-text">{t('templates.loading')}</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="app">
        <div className="error">
          <div className="error-icon">!</div>
          <h1 className="error-title">{t('common.somethingWentWrong')}</h1>
          <p className="error-message">{error}</p>
          <button className="retry-button" onClick={() => window.location.reload()}>
            {t('common.tryAgain')}
          </button>
        </div>
      </div>
    );
  }

  if (categories.length === 0) {
    return (
      <div className="app">
        <p className="explore-empty">{t('explore.noSubjects')}</p>
      </div>
    );
  }

  return (
    <div className="app">
      <div className="explore-subjects">
        {categories.map((category) => {
          const kinds = category.topics
            .filter((topic) => topic.items.length > 0)
            .map((topic) => topicLabel(t, topic));
          const total = category.topics.reduce((sum, topic) => sum + topic.items.length, 0);
          return (
            <button
              key={category.id}
              type="button"
              className="explore-subject"
              // The accent tints only the glyph's backing, never the tile: four
              // fully-coloured tiles in a grid read as four warnings.
              style={category.accent ? ({ '--subject-accent': category.accent } as React.CSSProperties) : undefined}
              onClick={() => {
                hapticFeedback('light');
                navigate(`/explore/${encodeURIComponent(category.id)}`);
              }}
            >
              <span className="explore-subject-glyph" aria-hidden>
                {category.icon || category.title.charAt(0)}
              </span>
              <span className="explore-subject-body">
                <span className="explore-subject-title" dir="auto">{category.title}</span>
                <span className="explore-subject-meta" dir="auto">
                  {kinds.join(' · ')}
                </span>
              </span>
              <span className="explore-subject-count">{total}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
