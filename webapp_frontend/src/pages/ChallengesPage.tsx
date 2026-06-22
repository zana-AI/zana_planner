import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Users, Sparkles, Layers } from 'lucide-react';
import { apiClient } from '../api/client';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import type { ChallengeSummary } from '../types';

const ACTIVITY_LABEL: Record<string, string> = {
  flashcard: 'Flashcards',
  multiple_choice: 'Quiz',
};

export function ChallengesPage() {
  const navigate = useNavigate();
  const { hapticFeedback } = useTelegramWebApp();
  const [challenges, setChallenges] = useState<ChallengeSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      setError('');
      try {
        const data = await apiClient.listChallenges();
        if (active) setChallenges(data);
      } catch (err) {
        console.error('Failed to load challenges:', err);
        if (active) setError('Failed to load challenges');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="app">
        <div className="loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading challenges…</div>
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
    <main style={{ padding: '8px 16px 96px', maxWidth: 720, margin: '0 auto' }}>
      {challenges.length === 0 ? (
        <div
          style={{
            textAlign: 'center',
            padding: '56px 20px',
            color: 'var(--color-text-secondary, #8A94A6)',
          }}
        >
          <Sparkles size={28} style={{ opacity: 0.6 }} />
          <p style={{ marginTop: 12, lineHeight: 1.5 }}>
            No challenges yet. New social challenges (vocab, quizzes and more) will show up here.
          </p>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 12 }}>
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
                padding: 16,
                color: 'var(--color-text-primary, #E6EAF2)',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                gap: 10,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                <div>
                  <div style={{ fontSize: 17, fontWeight: 700, lineHeight: 1.25 }}>{c.title}</div>
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
                    background: c.activity_type === 'multiple_choice' ? '#7FB2F0' : '#5DCAA5',
                    borderRadius: 999,
                    padding: '4px 10px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                  }}
                >
                  <Layers size={12} />
                  {ACTIVITY_LABEL[c.activity_type] ?? c.activity_type}
                </span>
              </div>

              {c.description ? (
                <div style={{ fontSize: 14, color: 'var(--color-text-secondary, #B6BECC)', lineHeight: 1.45 }}>
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
                  {c.joined ? 'Continue →' : 'Join →'}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </main>
  );
}
