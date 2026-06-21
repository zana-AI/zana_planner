import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Trophy, Flame, Check, X, RotateCcw } from 'lucide-react';
import { apiClient } from '../api/client';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import type {
  ChallengeSummary,
  ChallengeDeck,
  ChallengeAnswer,
  ChallengeCompleteResult,
  ChallengeLeaderboardEntry,
} from '../types';

type Phase = 'loading' | 'playing' | 'submitting' | 'result' | 'caughtup' | 'error';

const surface = 'var(--color-surface, #131A2B)';
const border = 'var(--color-border, #1E2740)';
const textPrimary = 'var(--color-text-primary, #E6EAF2)';
const textSecondary = 'var(--color-text-secondary, #8A94A6)';
const accent = '#5DCAA5';

export function ChallengePlayPage() {
  const navigate = useNavigate();
  const { challengeId } = useParams<{ challengeId: string }>();
  const { hapticFeedback } = useTelegramWebApp();

  const [phase, setPhase] = useState<Phase>('loading');
  const [challenge, setChallenge] = useState<ChallengeSummary | null>(null);
  const [deck, setDeck] = useState<ChallengeDeck | null>(null);
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [answers, setAnswers] = useState<ChallengeAnswer[]>([]);
  const [cardShownAt, setCardShownAt] = useState<number>(Date.now());
  const [result, setResult] = useState<ChallengeCompleteResult | null>(null);
  const [leaderboard, setLeaderboard] = useState<ChallengeLeaderboardEntry[]>([]);
  const [errorMsg, setErrorMsg] = useState('');

  const loadLeaderboard = useCallback(async (id: string) => {
    try {
      setLeaderboard(await apiClient.getChallengeLeaderboard(id));
    } catch {
      setLeaderboard([]);
    }
  }, []);

  useEffect(() => {
    if (!challengeId) return;
    let active = true;
    (async () => {
      setPhase('loading');
      try {
        const [info, dueDeck] = await Promise.all([
          apiClient.getChallenge(challengeId),
          apiClient.getDueDeck(challengeId),
        ]);
        if (!active) return;
        setChallenge(info);
        if (!dueDeck || dueDeck.items.length === 0) {
          await loadLeaderboard(challengeId);
          if (active) setPhase('caughtup');
          return;
        }
        setDeck(dueDeck);
        setIndex(0);
        setRevealed(false);
        setAnswers([]);
        setCardShownAt(Date.now());
        setPhase('playing');
      } catch (err) {
        console.error('Failed to load challenge:', err);
        if (active) {
          setErrorMsg('Could not load this challenge.');
          setPhase('error');
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [challengeId, loadLeaderboard]);

  const submit = useCallback(
    async (finalAnswers: ChallengeAnswer[]) => {
      if (!challengeId || !deck) return;
      setPhase('submitting');
      try {
        const res = await apiClient.completeChallengeDeck(challengeId, deck.deck_id, finalAnswers);
        setResult(res);
        await loadLeaderboard(challengeId);
        hapticFeedback('success');
        setPhase('result');
      } catch (err) {
        console.error('Failed to submit deck:', err);
        setErrorMsg('Could not save your answers.');
        setPhase('error');
      }
    },
    [challengeId, deck, hapticFeedback, loadLeaderboard],
  );

  const recordAndAdvance = useCallback(
    (response: string) => {
      if (!deck) return;
      const item = deck.items[index];
      const answer: ChallengeAnswer = {
        item_id: item.item_id,
        response,
        time_ms: Date.now() - cardShownAt,
      };
      const next = [...answers, answer];
      setAnswers(next);
      hapticFeedback('light');
      if (index + 1 >= deck.items.length) {
        submit(next);
      } else {
        setIndex(index + 1);
        setRevealed(false);
        setCardShownAt(Date.now());
      }
    },
    [answers, cardShownAt, deck, hapticFeedback, index, submit],
  );

  // ---- render helpers -----------------------------------------------------

  const shell = (children: React.ReactNode) => (
    <main style={{ padding: '8px 16px 96px', maxWidth: 560, margin: '0 auto' }}>{children}</main>
  );

  if (phase === 'loading' || phase === 'submitting') {
    return (
      <div className="app">
        <div className="loading">
          <div className="loading-spinner" />
          <div className="loading-text">{phase === 'submitting' ? 'Scoring…' : 'Loading…'}</div>
        </div>
      </div>
    );
  }

  if (phase === 'error') {
    return shell(
      <div style={{ textAlign: 'center', padding: '48px 16px', color: textSecondary }}>
        <div className="error-icon">!</div>
        <p style={{ marginTop: 12 }}>{errorMsg}</p>
        <button className="retry-button" onClick={() => navigate('/challenges')}>
          Back to challenges
        </button>
      </div>,
    );
  }

  const Leaderboard = (
    <section style={{ marginTop: 20 }}>
      <h2 style={{ fontSize: 14, color: textSecondary, margin: '0 0 10px', display: 'flex', alignItems: 'center', gap: 6 }}>
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
              <span style={{ fontSize: 13, color: textSecondary }}>{e.score_percent}% · {e.streak}🔥</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );

  if (phase === 'caughtup') {
    return shell(
      <div>
        <div
          style={{
            textAlign: 'center',
            padding: '32px 20px',
            border: `1px solid ${border}`,
            borderRadius: 16,
            background: surface,
          }}
        >
          <Check size={32} color={accent} />
          <h1 style={{ fontSize: 20, margin: '12px 0 6px', color: textPrimary }}>You're all caught up</h1>
          <p style={{ color: textSecondary, lineHeight: 1.5, margin: 0 }}>
            No new sets right now{challenge ? ` in ${challenge.title}` : ''}. Come back later for the next one.
          </p>
        </div>
        {Leaderboard}
      </div>,
    );
  }

  if (phase === 'result' && result) {
    return shell(
      <div>
        <div
          style={{
            textAlign: 'center',
            padding: '28px 20px',
            border: `1px solid ${border}`,
            borderRadius: 16,
            background: surface,
          }}
        >
          <div style={{ fontSize: 44, fontWeight: 800, color: accent, lineHeight: 1 }}>{result.score_pct}%</div>
          <p style={{ color: textPrimary, margin: '10px 0 4px', fontSize: 16 }}>
            {result.correct} / {result.total} correct
          </p>
          <p style={{ color: textSecondary, margin: 0, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <Flame size={15} color="#EF9F27" /> {result.streak}-day streak
          </p>
        </div>
        <button
          type="button"
          onClick={() => navigate(challengeId ? `/challenges/${challengeId}` : '/challenges')}
          style={{
            width: '100%',
            marginTop: 14,
            border: 0,
            borderRadius: 12,
            padding: '14px 16px',
            background: accent,
            color: '#06281F',
            fontWeight: 700,
            cursor: 'pointer',
          }}
        >
          Done
        </button>
        {Leaderboard}
      </div>,
    );
  }

  // ---- playing ------------------------------------------------------------
  if (!deck) return shell(null);
  const item = deck.items[index];
  const total = deck.items.length;
  const isFlashcard = deck.activity_type === 'flashcard';

  return shell(
    <div>
      {/* progress */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <div style={{ flex: 1, height: 6, borderRadius: 999, background: border, overflow: 'hidden' }}>
          <div style={{ width: `${(index / total) * 100}%`, height: '100%', background: accent, transition: 'width .2s' }} />
        </div>
        <span style={{ fontSize: 12, color: textSecondary, minWidth: 38, textAlign: 'right' }}>
          {index + 1}/{total}
        </span>
      </div>

      {/* card */}
      <div
        style={{
          border: `1px solid ${border}`,
          borderRadius: 16,
          background: surface,
          padding: '28px 20px',
          minHeight: 150,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
        }}
      >
        <div style={{ fontSize: 26, fontWeight: 700, color: textPrimary }}>{item.front}</div>
        {item.example ? (
          <div style={{ fontSize: 14, color: textSecondary, marginTop: 10, fontStyle: 'italic' }}>{item.example}</div>
        ) : null}
        {isFlashcard && revealed ? (
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: `1px solid ${border}`, width: '100%' }}>
            <div style={{ fontSize: 22, fontWeight: 700, color: accent }}>{item.back}</div>
          </div>
        ) : null}
      </div>

      {/* controls */}
      <div style={{ marginTop: 16 }}>
        {isFlashcard ? (
          revealed ? (
            <div style={{ display: 'flex', gap: 10 }}>
              <button type="button" onClick={() => recordAndAdvance('didnt')} style={choiceBtn('#3A2230', '#F0997B')}>
                <X size={16} /> Didn't know
              </button>
              <button type="button" onClick={() => recordAndAdvance('knew')} style={choiceBtn('#10302A', accent)}>
                <Check size={16} /> Knew it
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => {
                setRevealed(true);
                hapticFeedback('light');
              }}
              style={{
                width: '100%',
                border: `1px solid ${border}`,
                borderRadius: 12,
                padding: '14px 16px',
                background: 'transparent',
                color: textPrimary,
                fontWeight: 700,
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
              }}
            >
              <RotateCcw size={16} /> Show answer
            </button>
          )
        ) : (
          <div style={{ display: 'grid', gap: 10 }}>
            {(item.options ?? []).map((opt) => (
              <button
                key={opt}
                type="button"
                onClick={() => recordAndAdvance(opt)}
                style={{
                  border: `1px solid ${border}`,
                  borderRadius: 12,
                  padding: '14px 16px',
                  background: surface,
                  color: textPrimary,
                  fontWeight: 600,
                  fontSize: 15,
                  cursor: 'pointer',
                  textAlign: 'left',
                }}
              >
                {opt}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>,
  );
}

function choiceBtn(bg: string, color: string): React.CSSProperties {
  return {
    flex: 1,
    border: 0,
    borderRadius: 12,
    padding: '14px 16px',
    background: bg,
    color,
    fontWeight: 700,
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  };
}
