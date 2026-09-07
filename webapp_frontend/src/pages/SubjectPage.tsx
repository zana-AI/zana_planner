import { useTranslation } from 'react-i18next';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Check, Plus, Users } from 'lucide-react';
import { apiClient } from '../api/client';
import type { ChallengeSummary, ExploreCategory, ExploreItem } from '../types';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import { itemKind, topicLabel } from './exploreVocabulary';
import './explore.css';

/** One row of the list: a catalog item, plus the topic that decides what it is. */
interface SubjectEntry {
  item: ExploreItem;
  topicId: string;
  kind: string | null;
}

type AddState = 'idle' | 'adding' | 'added' | 'failed';

function youTubeUrlFor(item: ExploreItem): string | null {
  const videoId = item.native_ref?.match(/[?&]video_id=([a-zA-Z0-9_-]{11})/)?.[1];
  return videoId ? `https://www.youtube.com/watch?v=${videoId}` : null;
}

function challengeIdFor(item: ExploreItem): string | null {
  return item.native_ref?.match(/^\/challenges\/([^/?#]+)/)?.[1] ?? null;
}

/**
 * One subject: a single list, filtered by chips.
 *
 * The shelves this replaces described kinds of file rather than kinds of
 * behaviour, and six of them stacked vertically was more structure than eleven
 * items can carry. Chips hold the same information in one screen, and they are
 * the interaction Library already uses — so there is one way to browse a list
 * anywhere in the app.
 */
export function SubjectPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { subjectId = '' } = useParams();
  const { hapticFeedback } = useTelegramWebApp();
  const [category, setCategory] = useState<ExploreCategory | null>(null);
  const [challenges, setChallenges] = useState<ChallengeSummary[]>([]);
  const [topicFilter, setTopicFilter] = useState<string>('all');
  const [addState, setAddState] = useState<Record<string, AddState>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const [catalog, availableChallenges] = await Promise.all([
          apiClient.getExploreCatalog(),
          apiClient.listChallenges(),
        ]);
        if (!active) return;
        setCategory(catalog.categories.find((candidate) => candidate.id === subjectId) ?? null);
        setChallenges(availableChallenges);
      } catch (err) {
        console.error('Failed to load subject:', err);
        if (active) setError(t('templates.loadFailed'));
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [subjectId, t]);

  const topics = useMemo(
    () => (category?.topics ?? []).filter((topic) => topic.items.length > 0),
    [category],
  );

  const entries = useMemo<SubjectEntry[]>(
    () =>
      topics
        .filter((topic) => topicFilter === 'all' || topic.id === topicFilter)
        .flatMap((topic) =>
          topic.items.map((item) => ({ item, topicId: topic.id, kind: itemKind(topic.id) })),
        ),
    [topics, topicFilter],
  );

  const open = useCallback(
    (item: ExploreItem) => {
      hapticFeedback('light');
      if (item.url && /^https?:\/\//i.test(item.url)) {
        window.open(item.url, '_blank', 'noopener,noreferrer');
        return;
      }
      // The subtitle player is served outside the React router, so it needs a
      // real navigation rather than a route change.
      if (item.native_ref?.startsWith('/youtube-watch')) {
        const separator = item.native_ref.includes('?') ? '&' : '?';
        window.location.assign(`${item.native_ref}${separator}lang=${encodeURIComponent(i18n.language)}`);
        return;
      }
      if (item.native_ref?.startsWith('/')) navigate(item.native_ref);
    },
    [hapticFeedback, i18n.language, navigate],
  );

  /**
   * "Add" always means the same thing — this is mine now — and only the landing
   * place differs. A habit is the exception and has no Add: it needs a number
   * of hours before it can become a promise, so it opens its own page instead.
   */
  const add = useCallback(
    async (entry: SubjectEntry) => {
      const { item } = entry;
      setAddState((prev) => ({ ...prev, [item.id]: 'adding' }));
      try {
        const challengeId = challengeIdFor(item);
        if (challengeId) {
          const joined = await apiClient.joinChallenge(challengeId, 'explore');
          setChallenges((prev) => {
            const rest = prev.filter((candidate) => candidate.challenge_id !== challengeId);
            return [...rest, joined];
          });
        } else {
          const youTubeUrl = youTubeUrlFor(item);
          if (!youTubeUrl) throw new Error(`Nothing to add for ${item.id}`);
          const resolved = await apiClient.resolveContent(youTubeUrl);
          const contentId = resolved.content_id || resolved.id;
          if (!contentId) throw new Error('No content id returned');
          await apiClient.addUserContent(contentId);
        }
        hapticFeedback('success');
        setAddState((prev) => ({ ...prev, [item.id]: 'added' }));
      } catch (err) {
        console.error('Failed to add item:', err);
        hapticFeedback('error');
        setAddState((prev) => ({ ...prev, [item.id]: 'failed' }));
      }
    },
    [hapticFeedback],
  );

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

  if (error || !category) {
    return (
      <div className="app">
        <div className="error">
          <div className="error-icon">!</div>
          <h1 className="error-title">{t('common.somethingWentWrong')}</h1>
          <p className="error-message">{error || t('explore.subjectNotFound')}</p>
          <button className="retry-button" onClick={() => navigate('/explore')}>
            {t('explore.backToSubjects')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <h2 className="explore-subject-heading" dir="auto">
        {category.icon ? <span aria-hidden>{category.icon}</span> : null}
        {category.title}
      </h2>
      {topics.length > 1 ? (
        <div className="explore-chips" role="tablist" aria-label={category.title}>
          <button
            type="button"
            role="tab"
            aria-selected={topicFilter === 'all'}
            className={`explore-chip${topicFilter === 'all' ? ' is-active' : ''}`}
            onClick={() => setTopicFilter('all')}
          >
            {t('explore.all')}
          </button>
          {topics.map((topic) => (
            <button
              key={topic.id}
              type="button"
              role="tab"
              aria-selected={topicFilter === topic.id}
              className={`explore-chip${topicFilter === topic.id ? ' is-active' : ''}`}
              onClick={() => setTopicFilter(topic.id)}
            >
              {topicLabel(t, topic)}
            </button>
          ))}
        </div>
      ) : null}

      <div className="explore-list">
        {entries.map(({ item, topicId, kind }) => {
          const challengeId = challengeIdFor(item);
          const challenge = challengeId
            ? challenges.find((candidate) => candidate.challenge_id === challengeId)
            : undefined;
          const state = addState[item.id] ?? 'idle';
          const alreadyMine = state === 'added' || !!challenge?.joined;
          const addable = !!challengeId || !!youTubeUrlFor(item);

          return (
            <article key={item.id} className="explore-card">
              {item.image ? (
                <img className="explore-card-image" src={item.image} alt="" loading="lazy" />
              ) : null}
              <div className="explore-card-head">
                <h3 className="explore-card-title" dir="auto">{item.title}</h3>
                {kind ? <span className="explore-card-kind">{t(`explore.kind.${kind}`)}</span> : null}
              </div>
              {item.description ? (
                <p className="explore-card-description" dir="auto">{item.description}</p>
              ) : null}
              {challenge ? (
                <p className="explore-card-stat">
                  <Users size={14} aria-hidden />
                  {t('explore.players', { count: challenge.participant_count })}
                </p>
              ) : null}
              {item.class_offer ? <p className="explore-card-offer">{item.class_offer}</p> : null}
              <div className="explore-card-actions">
                <button type="button" className="explore-action is-primary" onClick={() => open(item)}>
                  {topicId === 'habits' ? t('explore.promiseIt') : t('explore.open')}
                </button>
                {addable ? (
                  <button
                    type="button"
                    className={`explore-action${alreadyMine ? ' is-done' : ''}`}
                    disabled={state === 'adding' || alreadyMine}
                    onClick={() => void add({ item, topicId, kind })}
                  >
                    {alreadyMine ? <Check size={14} aria-hidden /> : <Plus size={14} aria-hidden />}
                    {alreadyMine
                      ? t('explore.added')
                      : state === 'adding'
                        ? t('explore.adding')
                        : t('explore.add')}
                  </button>
                ) : null}
              </div>
              {state === 'failed' ? <p className="explore-card-error">{t('explore.addFailed')}</p> : null}
            </article>
          );
        })}
      </div>
    </div>
  );
}
