import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Users, Trophy, Flame, Layers, Play } from 'lucide-react';
import { apiClient } from '../api/client';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import type { ChallengeSummary, ChallengeLeaderboardEntry } from '../types';

const surface = 'var(--color-surface, #131A2B)';
const border = 'var(--color-border, #1E2740)';
const textPrimary = 'var(--color-text-primary, #E6EAF2)';
const textSecondary = 'var(--color-text-secondary, #8A94A6)';
const accent = '#5DCAA5';

const ACTIVITY_LABEL: Record<string, string> = { flashcard: 'Flashcards', multiple_choice: 'Quiz' };

export function ChallengeDetailPage() {
  const navigate = useNavigate();
  const { challengeId } = useParams<{ challengeId: string }>();
  const { hapticFeedback } = useTelegramWebApp();

  const [challenge, setChallenge] = useState<ChallengeSummary | null>(null);
  const [leaderboard, setLeaderboard] = useState<ChallengeLeaderboardEntry[]>([]);
  const [hasDueDeck, setHasDueDeck] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!challengeId) return;
    let active = true;
    (async () => {
      setLoading(true);
      setError('');
      try {
        const [info, board, deck] = await Promise.all([
          apiClient.getChallenge(challengeId),
          apiClient.getChallengeLeaderboard(challengeId),
          apiClient.getDueDeck(challengeId),
        ]);
        if (!active) return;
        setChallenge(info);
        setLeaderboard(board);
        setHasDueDeck(!!deck && deck.items.length > 0);
      } catch (err) {
        console.error('Failed to load challenge:', err);
        if (active) setError('Could not load this challenge.');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [challengeId]);

  if (loading) {
    return (
      <div className="app">
        <div className="loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading…</div>
        </div>
      </div>
    );
  }

  if (error || !challenge) {
    return (
      <main style={{ padding: '40px 16px', textAlign: 'center', color: textSecondary }}>
        <div className="error-icon">!</div>
        <p style={{ marginTop: 12 }}>{error || 'Challenge not found.'}</p>
        <button className="retry-button" onClick={() => navigate('/challenges')}>
          Back to challenges
        </button>
      </main>
    );
  }

  return (
    <main style={{ padding: '8px 16px 96px', maxWidth: 560, margin: '0 auto' }}>
      {/* Host brand + summary */}
      <section
        style={{
          border: `1px solid ${border}`,
          borderRadius: 16,
          background: surface,
          padding: 20,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div
            aria-hidden
            style={{
              width: 44,
              height: 44,
              borderRadius: 999,
              background: 'linear-gradient(135deg, #5DCAA5, #378ADD)',
              display: 'grid',
              placeItems: 'center',
              color: '#06281F',
              fontWeight: 800,
              fontSize: 18,
              flexShrink: 0,
            }}
          >
            {challenge.host_name.charAt(0).toUpperCase()}
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: 20, lineHeight: 1.2, color: textPrimary }}>{challenge.title}</h1>
            <div style={{ fontSize: 13, color: textSecondary, marginTop: 2 }}>by {challenge.host_name}</div>
          </div>
        </div>

        {challenge.description ? (
          <p style={{ color: textSecondary, lineHeight: 1.5, marginTop: 14, marginBottom: 0 }}>{challenge.description}</p>
        ) : null}

        <div style={{ display: 'flex', gap: 16, marginTop: 16, color: textSecondary, fontSize: 13 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <Users size={14} /> {challenge.participant_count} {challenge.participant_count === 1 ? 'player' : 'players'}
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <Layers size={14} /> {ACTIVITY_LABEL[challenge.activity_type] ?? challenge.activity_type}
          </span>
        </div>
      </section>

      {/* Primary CTA */}
      {hasDueDeck ? (
        <button
          type="button"
          onClick={async () => {
            hapticFeedback('light');
            // Subscribe on first play so the challenge becomes a promise on My Week
            // (and the user is eligible for daily reminders) before they finish a deck.
            if (!challenge.joined) {
              try {
                await apiClient.joinChallenge(challenge.challenge_id);
              } catch (err) {
                console.error('Subscribe failed:', err);
              }
            }
            navigate(`/challenges/${challenge.challenge_id}/play`);
          }}
          style={{
            width: '100%',
            marginTop: 14,
            border: 0,
            borderRadius: 12,
            padding: '15px 16px',
            background: accent,
            color: '#06281F',
            fontWeight: 800,
            fontSize: 15,
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
          }}
        >
          <Play size={17} /> {challenge.joined ? "Play today's set" : 'Start playing'}
        </button>
      ) : (
        <div
          style={{
            marginTop: 14,
            border: `1px solid ${border}`,
            borderRadius: 12,
            padding: '14px 16px',
            textAlign: 'center',
            color: textSecondary,
            fontSize: 14,
          }}
        >
          You're all caught up — come back later for the next set.
        </div>
      )}

      {/* Leaderboard */}
      <section style={{ marginTop: 22 }}>
        <h2
          style={{
            fontSize: 14,
            color: textSecondary,
            margin: '0 0 10px',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <Trophy size={15} /> Leaderboard · this week
        </h2>
        {leaderboard.length === 0 ? (
          <p style={{ color: textSecondary, fontSize: 13 }}>Be the first on the board — play a round!</p>
        ) : (
          <div style={{ display: 'grid', gap: 6 }}>
            {leaderboard.map((e) => (
              <div
                key={e.user_id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '10px 14px',
                  borderRadius: 10,
                  border: `1px solid ${border}`,
                  background: surface,
                }}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: 10, color: textPrimary }}>
                  <span style={{ width: 22, textAlign: 'center', fontWeight: 700, color: e.rank <= 3 ? accent : textSecondary }}>
                    {e.rank}
                  </span>
                  {e.name}
                </span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, color: textSecondary }}>
                  {e.score_percent}% · {e.streak}🔥
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
