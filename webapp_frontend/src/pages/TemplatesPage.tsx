import { useTranslation } from 'react-i18next';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bookmark, Users, Layers, GraduationCap } from 'lucide-react';
import { apiClient } from '../api/client';
import type { PromiseTemplate, ChallengeSummary, FlashcardDeckSummary, ExploreCatalog, ExploreItem } from '../types';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import { Emoji } from '../components/ui/Emoji';
import { AvatarStack } from '../components/ui/AvatarStack';
import type { AvatarStackUser } from '../components/ui/AvatarStack';

type TemplateUser = AvatarStackUser;

// Everything here is a quiz — the badge says which *kind*, so "Quiz" on its own
// would carry no information. Cohort quizzes release daily; vocab quizzes come
// back when you are about to forget them.
const CHALLENGE_ACTIVITY_LABEL: Record<string, string> = {
  flashcard: 'Daily',
  multiple_choice: 'Daily',
};

export function TemplatesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { hapticFeedback } = useTelegramWebApp();
  const [templates, setTemplates] = useState<PromiseTemplate[]>([]);
  const [challenges, setChallenges] = useState<ChallengeSummary[]>([]);
  const [studyDecks, setStudyDecks] = useState<FlashcardDeckSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [templateUsers, setTemplateUsers] = useState<Record<string, TemplateUser[]>>({});
  const [explore, setExplore] = useState<ExploreCatalog | null>(null);

  useEffect(() => {
    const loadTemplates = async () => {
      setLoading(true);
      setError('');
      try {
        const response = await apiClient.getTemplates();
        setTemplates(response.templates);
        hapticFeedback('success');
      } catch (err) {
        console.error('Failed to load templates:', err);
        setError(t('templates.loadFailed'));
        hapticFeedback('error');
      } finally {
        setLoading(false);
      }
    };
    loadTemplates();
  }, [hapticFeedback]);

  useEffect(() => {
    let active = true;
    apiClient
      .listChallenges()
      .then((data) => {
        if (active) setChallenges(data);
      })
      .catch((err) => console.error('Failed to load challenges:', err));
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    apiClient.getExploreCatalog().then(setExplore).catch((err) => console.error('Failed to load Explore catalog:', err));
  }, []);

  const openExploreItem = (item: ExploreItem) => {
    hapticFeedback('light');
    if (item.url && /^https?:\/\//i.test(item.url)) window.open(item.url, '_blank', 'noopener,noreferrer');
    else if (item.native_ref?.startsWith('/')) navigate(item.native_ref);
  };

  // Study decks are listed from the user's own decks, so a new subject or
  // language appears here on its own without touching this page.
  useEffect(() => {
    let active = true;
    apiClient
      .getFlashcardSummary()
      .then((data) => {
        if (active) setStudyDecks(data.filter((d) => d.total > 0));
      })
      .catch((err) => console.error('Failed to load study decks:', err));
    return () => {
      active = false;
    };
  }, []);

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
      {studyDecks.length > 0 ? (
        <section style={{ padding: '4px 0 8px' }}>
          <h2
            style={{
              fontSize: 13,
              fontWeight: 700,
              letterSpacing: 0.3,
              textTransform: 'uppercase',
              color: 'var(--color-text-secondary, #8A94A6)',
              margin: '0 0 10px',
            }}
          >{t('templates.quiz')}</h2>
          <div style={{ display: 'grid', gap: 10 }}>
            {studyDecks.map((deck) => (
              <button
                key={deck.deck_id}
                type="button"
                onClick={() => {
                  hapticFeedback('light');
                  navigate(
                    `/flashcards?deck=${encodeURIComponent(deck.deck_id)}` +
                    `&name=${encodeURIComponent(deck.name)}`,
                  );
                }}
                style={{
                  textAlign: 'left',
                  border: '1px solid var(--color-border, #1E2740)',
                  background: 'var(--color-surface, #131A2B)',
                  borderRadius: 14,
                  padding: 14,
                  color: 'var(--color-text-primary, #E6EAF2)',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 700, lineHeight: 1.25 }}>{deck.name}</div>
                    <div style={{ fontSize: 13, color: 'var(--color-text-secondary, #8A94A6)', marginTop: 2 }}>
                      {deck.total} card{deck.total === 1 ? '' : 's'}
                    </div>
                  </div>
                  <span
                    style={{
                      flexShrink: 0,
                      fontSize: 11,
                      fontWeight: 700,
                      letterSpacing: 0.3,
                      textTransform: 'uppercase',
                      color: '#0B0F1A',
                      background: '#9DE7B0',
                      borderRadius: 999,
                      padding: '4px 10px',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 4,
                    }}
                  >
                    <GraduationCap size={12} />{t('templates.vocab')}</span>
                </div>
                <div style={{ fontSize: 13, color: 'var(--color-text-secondary, #B6BECC)' }}>
                  {deck.due + deck.new > 0
                    ? `${deck.due} due · ${deck.new} new`
                    : 'All caught up for now'}
                </div>
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {challenges.length > 0 ? (
        <section style={{ padding: '4px 0 8px' }}>
          <h2
            style={{
              fontSize: 13,
              fontWeight: 700,
              letterSpacing: 0.3,
              textTransform: 'uppercase',
              color: 'var(--color-text-secondary, #8A94A6)',
              margin: '0 0 10px',
            }}
          >{t('templates.challenges')}</h2>
          <div style={{ display: 'grid', gap: 10 }}>
            {challenges.map((c) => (
              <button
                key={c.challenge_id}
                type="button"
                onClick={() => {
                  hapticFeedback('light');
                  navigate(`/challenges/${c.challenge_id}`);
                }}
                style={{
                  textAlign: 'left',
                  border: '1px solid var(--color-border, #1E2740)',
                  background: 'var(--color-surface, #131A2B)',
                  borderRadius: 14,
                  padding: 14,
                  color: 'var(--color-text-primary, #E6EAF2)',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 700, lineHeight: 1.25 }}>{c.title}</div>
                    <div style={{ fontSize: 13, color: 'var(--color-text-secondary, #8A94A6)', marginTop: 2 }}>
                      by {c.host_name}
                    </div>
                  </div>
                  <span
                    style={{
                      flexShrink: 0,
                      fontSize: 11,
                      fontWeight: 700,
                      letterSpacing: 0.3,
                      textTransform: 'uppercase',
                      color: '#0B0F1A',
                      background: '#7FB2F0',
                      borderRadius: 999,
                      padding: '4px 10px',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 4,
                    }}
                  >
                    <Layers size={12} />
                    {CHALLENGE_ACTIVITY_LABEL[c.activity_type] ?? c.activity_type}
                  </span>
                </div>
                {c.description ? (
                  <div style={{ fontSize: 13.5, color: 'var(--color-text-secondary, #B6BECC)', lineHeight: 1.45 }}>
                    {c.description}
                  </div>
                ) : null}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 2 }}>
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 6,
                      fontSize: 13,
                      color: 'var(--color-text-secondary, #8A94A6)',
                    }}
                  >
                    <Users size={14} />
                    {c.participant_count} {c.participant_count === 1 ? 'player' : 'players'}
                  </span>
                  <span
                    style={{
                      fontSize: 13,
                      fontWeight: 700,
                      color: c.joined ? 'var(--color-text-secondary, #8A94A6)' : '#5DCAA5',
                    }}
                  >
                    {c.joined ? 'Continue →' : 'Subscribe →'}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {explore?.categories.map((category) => (
        <section key={category.id} style={{ padding: '4px 0 10px' }}>
          <h2 style={{ fontSize: 13, fontWeight: 700, letterSpacing: 0.3, textTransform: 'uppercase', color: 'var(--color-text-secondary, #8A94A6)', margin: '0 0 10px' }}>{category.title}</h2>
          {category.topics.map((topic) => (
            <div key={topic.id} style={{ marginBottom: 12 }}>
              <h3 style={{ fontSize: 15, margin: '0 0 7px', color: 'var(--color-text-primary, #E6EAF2)' }}>{topic.title}</h3>
              <div style={{ display: 'grid', gap: 8 }}>
                {topic.items.map((item) => (
                  <button key={item.id} type="button" onClick={() => openExploreItem(item)} disabled={!(item.url && /^https?:\/\//i.test(item.url)) && !item.native_ref?.startsWith('/')} style={{ textAlign: 'left', border: '1px solid var(--color-border, #1E2740)', background: 'var(--color-surface, #131A2B)', borderRadius: 12, padding: 12, color: 'var(--color-text-primary, #E6EAF2)', cursor: item.url || item.native_ref ? 'pointer' : 'default' }}>
                    {item.image ? <img src={item.image} alt="" loading="lazy" style={{ display: 'block', width: '100%', maxHeight: 120, objectFit: 'cover', borderRadius: 8, marginBottom: 8 }} /> : null}
                    <div style={{ fontSize: 15, fontWeight: 700 }}>{item.title}</div>
                    {item.description ? <div style={{ fontSize: 13, color: 'var(--color-text-secondary, #B6BECC)', marginTop: 3 }}>{item.description}</div> : null}
                    {item.class_offer ? <div style={{ fontSize: 12, color: '#5DCAA5', marginTop: 6 }}>{item.class_offer}</div> : null}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </section>
      ))}

      {templates.length > 0 ? (
        <h2
          style={{
            fontSize: 13,
            fontWeight: 700,
            letterSpacing: 0.3,
            textTransform: 'uppercase',
            color: 'var(--color-text-secondary, #8A94A6)',
            margin: '8px 0 10px',
          }}
        >{t('templates.quickStartHabits')}</h2>
      ) : null}

      <main className="templates-grid">
        {templates.length === 0 ? (
          <div className="empty-state">
            <h2 className="empty-title">{t('templates.emptyTitle')}</h2>
            <p className="empty-subtitle">{t('templates.emptySubtitle')}</p>
          </div>
        ) : (
          templates.map((template) => {
            const users = templateUsers[template.template_id] ?? [];
            return (
              <div key={template.template_id} className="template-card" onClick={() => navigate(`/templates/${template.template_id}`)}>
                <div className="template-header">
                  <span className="template-list-logo">
                    {template.emoji ? (
                      <Emoji emoji={template.emoji} size={20} />
                    ) : (
                      <Bookmark size={16} strokeWidth={1.8} color="rgba(237,243,255,0.45)" />
                    )}
                  </span>
                  <h3 className="template-title">{template.title}</h3>
                </div>
                {template.description ? <p className="template-why">{template.description}</p> : null}
                {users.length > 0 && (
                  <div className="template-meta" style={{ alignItems: 'center', gap: 6 }}>
                    <AvatarStack users={users} size={18} max={3} />
                    <span style={{ fontSize: 12, color: 'var(--color-text-secondary, #8A94A6)' }}>
                      {users.length === 1 ? '1 doing this' : `${users.length} doing this`}
                    </span>
                  </div>
                )}
              </div>
            );
          })
        )}
      </main>
    </div>
  );
}
