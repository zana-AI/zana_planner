import { useTranslation } from 'react-i18next';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Users, Layers, GraduationCap } from 'lucide-react';
import { apiClient } from '../api/client';
import type { ChallengeSummary, FlashcardDeckSummary, ExploreCatalog, ExploreItem, ExploreTopic } from '../types';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';

// Everything here is a quiz — the badge says which *kind*, so "Quiz" on its own
// would carry no information. Cohort quizzes release daily; vocab quizzes come
// back when you are about to forget them.
const CHALLENGE_ACTIVITY_LABEL: Record<string, string> = {
  flashcard: 'Daily',
  multiple_choice: 'Daily',
};

export function TemplatesPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { hapticFeedback } = useTelegramWebApp();
  const [challenges, setChallenges] = useState<ChallengeSummary[]>([]);
  const [studyDecks, setStudyDecks] = useState<FlashcardDeckSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [explore, setExplore] = useState<ExploreCatalog | null>(null);

  useEffect(() => {
    let active = true;
    const loadExplore = async () => {
      setLoading(true);
      setError('');
      try {
        const [catalog, availableChallenges, decks] = await Promise.all([
          apiClient.getExploreCatalog(),
          apiClient.listChallenges(),
          apiClient.getFlashcardSummary(),
        ]);
        if (!active) return;
        setExplore(catalog);
        setChallenges(availableChallenges);
        setStudyDecks(decks.filter((deck) => deck.total > 0));
        hapticFeedback('success');
      } catch (err) {
        console.error('Failed to load Explore:', err);
        setError(t('templates.loadFailed'));
        hapticFeedback('error');
      } finally {
        if (active) setLoading(false);
      }
    };
    loadExplore();
    return () => {
      active = false;
    };
  }, [hapticFeedback]);

  const openExploreItem = (item: ExploreItem) => {
    hapticFeedback('light');
    if (item.url && /^https?:\/\//i.test(item.url)) window.open(item.url, '_blank', 'noopener,noreferrer');
    else if (item.native_ref?.startsWith('/youtube-watch')) {
      const separator = item.native_ref.includes('?') ? '&' : '?';
      window.location.assign(`${item.native_ref}${separator}lang=${encodeURIComponent(i18n.language)}`);
    } else if (item.native_ref?.startsWith('/')) navigate(item.native_ref);
  };

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

  return (
    <div className="app">
      {explore?.categories.map((category) => {
        const topics: ExploreTopic[] = category.id === 'french' && studyDecks.length > 0
          ? [{
              id: 'review',
              title: 'Review',
              order: 5,
              published: true,
              items: studyDecks.map((deck, index) => ({
                id: `flashcard-${deck.deck_id}`,
                title: deck.name === 'French' ? 'Édito B1' : deck.name,
                type: 'flashcard',
                order: index + 1,
                published: true,
                native_ref: `/flashcards?deck=${encodeURIComponent(deck.deck_id)}&name=${encodeURIComponent(deck.name)}`,
                description: `${deck.total} card${deck.total === 1 ? '' : 's'} · ${deck.due + deck.new} to review`,
              })),
            }, ...category.topics]
          : category.topics;

        return (
        <section key={category.id} style={{ padding: '4px 0 10px' }}>
          <h2 style={{ fontSize: 13, fontWeight: 700, letterSpacing: 0.3, textTransform: 'uppercase', color: 'var(--color-text-secondary, #8A94A6)', margin: '0 0 10px' }}>{category.title}</h2>
          {topics.filter((topic) => topic.items.length > 0).map((topic) => (
            <div key={topic.id} style={{ marginBottom: 12 }}>
              <h3 style={{ fontSize: 15, margin: '0 0 7px', color: 'var(--color-text-primary, #E6EAF2)' }}>{topic.title}</h3>
              <div style={{ display: 'grid', gap: 8 }}>
                {topic.items.map((item) => {
                  const challengeId = item.native_ref?.match(/^\/challenges\/([^/?#]+)/)?.[1];
                  const challenge = item.type === 'challenge'
                    ? challenges.find((candidate) => candidate.challenge_id === challengeId)
                    : undefined;
                  const deck = item.type === 'flashcard'
                    ? studyDecks.find((candidate) => `flashcard-${candidate.deck_id}` === item.id)
                    : undefined;

                  if (challenge) {
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => { hapticFeedback('light'); navigate(`/challenges/${challenge.challenge_id}`); }}
                        style={{ textAlign: 'left', border: '1px solid var(--color-border, #1E2740)', background: 'var(--color-surface, #131A2B)', borderRadius: 12, padding: 12, color: 'var(--color-text-primary, #E6EAF2)', cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 7 }}
                      >
                        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                          <div style={{ fontSize: 15, fontWeight: 700 }}>{challenge.title}</div>
                          <span style={{ flexShrink: 0, fontSize: 11, fontWeight: 700, letterSpacing: 0.3, textTransform: 'uppercase', color: '#0B0F1A', background: '#7FB2F0', borderRadius: 999, padding: '4px 9px', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <Layers size={12} />{CHALLENGE_ACTIVITY_LABEL[challenge.activity_type] ?? challenge.activity_type}
                          </span>
                        </div>
                        {challenge.description ? <div style={{ fontSize: 13, color: 'var(--color-text-secondary, #B6BECC)', lineHeight: 1.45 }}>{challenge.description}</div> : null}
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 2, fontSize: 13, color: 'var(--color-text-secondary, #8A94A6)' }}>
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Users size={14} />{challenge.participant_count} {challenge.participant_count === 1 ? 'player' : 'players'}</span>
                          <span style={{ fontWeight: 700, color: challenge.joined ? 'var(--color-text-secondary, #8A94A6)' : '#5DCAA5' }}>{challenge.joined ? 'Continue →' : 'Subscribe →'}</span>
                        </div>
                      </button>
                    );
                  }

                  if (deck) {
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => { hapticFeedback('light'); openExploreItem(item); }}
                        style={{ textAlign: 'left', border: '1px solid var(--color-border, #1E2740)', background: 'var(--color-surface, #131A2B)', borderRadius: 12, padding: 12, color: 'var(--color-text-primary, #E6EAF2)', cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 7 }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                          <div style={{ fontSize: 15, fontWeight: 700 }}>{item.title}</div>
                          <span style={{ flexShrink: 0, fontSize: 11, fontWeight: 700, letterSpacing: 0.3, textTransform: 'uppercase', color: '#0B0F1A', background: '#9DE7B0', borderRadius: 999, padding: '4px 9px', display: 'inline-flex', alignItems: 'center', gap: 4 }}><GraduationCap size={12} />{t('templates.vocab')}</span>
                        </div>
                        <div style={{ fontSize: 13, color: 'var(--color-text-secondary, #B6BECC)' }}>{item.description}</div>
                      </button>
                    );
                  }

                  return (
                    <button key={item.id} type="button" onClick={() => openExploreItem(item)} disabled={!(item.url && /^https?:\/\//i.test(item.url)) && !item.native_ref?.startsWith('/')} style={{ textAlign: 'left', border: '1px solid var(--color-border, #1E2740)', background: 'var(--color-surface, #131A2B)', borderRadius: 12, padding: 12, color: 'var(--color-text-primary, #E6EAF2)', cursor: item.url || item.native_ref ? 'pointer' : 'default' }}>
                      {item.image ? <img src={item.image} alt="" loading="lazy" style={{ display: 'block', width: '100%', maxHeight: 120, objectFit: 'cover', borderRadius: 8, marginBottom: 8 }} /> : null}
                      <div style={{ fontSize: 15, fontWeight: 700 }}>{item.title}</div>
                      {item.description ? <div style={{ fontSize: 13, color: 'var(--color-text-secondary, #B6BECC)', marginTop: 3 }}>{item.description}</div> : null}
                      {item.class_offer ? <div style={{ fontSize: 12, color: '#5DCAA5', marginTop: 6 }}>{item.class_offer}</div> : null}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </section>
        );
      })}
    </div>
  );
}
