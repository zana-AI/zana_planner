import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Globe, Play, Send, Trophy, Users } from 'lucide-react';
import { apiClient } from '../api/client';
import { TelegramLogin } from '../components/TelegramLogin';
import type { PublicClubLink, PublicClubProfile } from '../types';
import './ClubProfilePage.css';

/**
 * The public club landing page (xaana.club/<club>).
 *
 * Design constraint driving everything here: a subscriber tapping this link in
 * a creator's Telegram channel must reach today's round in one or two taps.
 * Two consequences fall out of that budget and are load-bearing:
 *
 *  1. The page renders anonymously. Auth is deferred to the moment the visitor
 *     actually plays, so the shell (identity, today's round, leaderboard) is
 *     visible to someone who has never heard of Xaana.
 *  2. There is no separate "Join club" step. Starting the round joins you —
 *     `POST /challenges/{id}/join` already creates the backing promise, club
 *     membership and leaderboard share.
 *
 * See docs/CLUBS_MODEL.md §5.
 */

/** Same thresholds as the in-app leaderboard (ClubBadge.tsx). */
function activityLevel(score: number): number {
  if (score >= 90) return 4;
  if (score >= 60) return 3;
  if (score > 0) return 2;
  return 0;
}

function formatWindow(start?: string | null, end?: string | null): string {
  if (!start || !end) return 'Rolling 7 days';
  return `${start} – ${end}`;
}

function LinkChip({ link }: { link: PublicClubLink }) {
  const Icon = link.kind === 'telegram' ? Send : Globe;
  return (
    <a
      className="clubprofile-link"
      href={link.url}
      target="_blank"
      rel="noopener noreferrer"
    >
      <Icon size={13} aria-hidden />
      {link.label}
    </a>
  );
}

export function ClubProfilePage() {
  const { clubRef } = useParams<{ clubRef: string }>();

  const [profile, setProfile] = useState<PublicClubProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [signingIn, setSigningIn] = useState(false);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    if (!clubRef) return;
    let active = true;
    setLoading(true);
    setError('');
    apiClient.getPublicClub(clubRef)
      .then((data) => { if (active) setProfile(data); })
      .catch((err) => {
        console.error('Failed to load club profile:', err);
        if (active) setError('This club page is not available.');
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [clubRef]);

  /** Where the CTA lands once we know who the visitor is. */
  const destination = useMemo(() => {
    if (!profile?.today) return null;
    if (profile.today.kind === 'quiz' && profile.today.challenge_id) {
      return `/challenges/${profile.today.challenge_id}/play`;
    }
    return `/community?club=${profile.club_id}`;
  }, [profile]);

  const enterRound = useCallback(async () => {
    if (!profile?.today || !destination) return;
    setStarting(true);
    try {
      // Implicit join: subscribing here is what makes them a member, so there
      // is never a separate join button to spend a tap on. Non-fatal — a failed
      // join shouldn't strand them outside the round they asked for.
      if (profile.today.kind === 'quiz' && profile.today.challenge_id) {
        await apiClient.joinChallenge(profile.today.challenge_id, 'club_page');
      }
    } catch (err) {
      console.error('Join failed, continuing to the round anyway:', err);
    }
    window.location.assign(destination);
  }, [destination, profile]);

  const handleCtaClick = useCallback(() => {
    if (profile?.viewer.authenticated) {
      void enterRound();
      return;
    }
    // Swap the button for the Telegram widget in place rather than routing to a
    // login screen — a detour here costs the click budget the page is built around.
    setSigningIn(true);
  }, [enterRound, profile]);

  // A full page load after login (rather than client-side navigation) guarantees
  // the new session token is picked up before the authenticated route mounts.
  const handleAuthSuccess = useCallback(() => {
    if (destination) window.location.assign(destination);
  }, [destination]);

  if (loading) {
    return <div className="clubprofile-state">Loading…</div>;
  }

  if (error || !profile) {
    return (
      <div className="clubprofile-state">
        <div>
          <p>{error || 'Club not found.'}</p>
          <p style={{ marginTop: 8 }}>
            <a href="/" style={{ color: 'var(--accent)' }}>Go to Xaana</a>
          </p>
        </div>
      </div>
    );
  }

  const round = profile.today;
  const memberLabel = profile.participant_count ?? profile.member_count;
  const ctaLabel = round?.kind === 'quiz'
    ? (profile.viewer.is_member ? "Play today's round" : 'Start playing')
    : 'Check in for today';

  return (
    <main className="clubprofile">
      <div className="clubprofile-inner">
        <header className="clubprofile-hero">
          <div className="clubprofile-monogram" aria-hidden>
            {profile.name.trim().charAt(0).toUpperCase()}
          </div>
          <h1 className="clubprofile-name" dir="auto">{profile.name}</h1>

          <p className="clubprofile-byline">
            {profile.host_name ? <span>by {profile.host_name}</span> : null}
            <span className={profile.host_name ? 'dot' : undefined}>
              <Users size={12} aria-hidden style={{ verticalAlign: '-1px', marginInlineEnd: 4 }} />
              {memberLabel} {memberLabel === 1 ? 'member' : 'members'}
            </span>
          </p>

          {profile.tagline ? (
            <p className="clubprofile-tagline" dir="auto">{profile.tagline}</p>
          ) : null}

          {profile.links.length ? (
            <nav className="clubprofile-links" aria-label="Club links">
              {profile.links.map((link) => <LinkChip key={link.url} link={link} />)}
            </nav>
          ) : null}
        </header>

        {round ? (
          <section className="clubprofile-today" aria-label="Today">
            <div className="clubprofile-today-head">
              <span className="clubprofile-eyebrow">Today</span>
              {round.item_count > 0 && round.kind === 'quiz' ? (
                <span className="clubprofile-today-meta">
                  {round.item_count} {round.item_count === 1 ? 'question' : 'questions'}
                </span>
              ) : null}
            </div>

            <h2 className="clubprofile-today-title" dir="auto">{round.title}</h2>
            {round.subtitle ? (
              <p className="clubprofile-today-sub" dir="auto">{round.subtitle}</p>
            ) : null}

            {signingIn ? (
              <div className="clubprofile-auth">
                <TelegramLogin onAuthSuccess={handleAuthSuccess} />
                <p className="clubprofile-cta-note">Sign in with Telegram to start.</p>
              </div>
            ) : (
              <>
                <button
                  type="button"
                  className="clubprofile-cta"
                  onClick={handleCtaClick}
                  disabled={starting}
                >
                  <Play size={17} aria-hidden />
                  {starting ? 'Opening…' : ctaLabel}
                </button>
                {!profile.viewer.authenticated ? (
                  <p className="clubprofile-cta-note">Free · no app to install</p>
                ) : null}
              </>
            )}
          </section>
        ) : (
          <section className="clubprofile-empty">
            Nothing scheduled today — check back tomorrow.
          </section>
        )}

        <section aria-label="Leaderboard">
          <div className="clubprofile-section-head">
            <h2 className="clubprofile-section-title">
              <Trophy size={14} aria-hidden /> This week
            </h2>
            <span className="clubprofile-window" dir="ltr">
              {formatWindow(profile.window_start, profile.window_end)}
            </span>
          </div>

          {profile.leaderboard.length === 0 ? (
            <p className="clubprofile-board-empty">
              No one has played yet this week — be first on the board.
            </p>
          ) : (
            <div className="clubprofile-board">
              {profile.leaderboard.map((row) => (
                <div
                  className={`clubprofile-row${row.rank <= 3 ? ' clubprofile-row--podium' : ''}`}
                  key={`${row.rank}-${row.name}`}
                >
                  <span className="clubprofile-rank">{row.rank}</span>
                  {row.user_id ? (
                    <img
                      className="clubprofile-avatar"
                      src={`/api/public/avatars/${row.user_id}`}
                      alt=""
                      loading="lazy"
                      onError={(event) => { event.currentTarget.style.display = 'none'; }}
                    />
                  ) : (
                    <span className="clubprofile-avatar" aria-hidden>{row.initials}</span>
                  )}
                  <div className="clubprofile-person">
                    <strong dir="auto">{row.name}</strong>
                    <span>{row.streak} day streak</span>
                  </div>
                  <div
                    className="clubprofile-strip"
                    aria-label={`Activity over the last ${row.daily_activity.length} days`}
                  >
                    {row.daily_activity.map((score, index) => (
                      <span
                        key={index}
                        className={`clubprofile-cell level-${activityLevel(score)}`}
                      />
                    ))}
                  </div>
                  <span className="clubprofile-score">{Math.round(row.score_percent)}%</span>
                </div>
              ))}
            </div>
          )}
        </section>

        {profile.description ? (
          <section aria-label="About">
            <div className="clubprofile-section-head">
              <h2 className="clubprofile-section-title">About</h2>
            </div>
            <p className="clubprofile-about" dir="auto">{profile.description}</p>
          </section>
        ) : null}

        <footer className="clubprofile-footer">
          <a href="/">Kept by Xaana</a>
        </footer>
      </div>
    </main>
  );
}
