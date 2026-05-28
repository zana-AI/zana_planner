import { useEffect, useState, type KeyboardEvent } from 'react';
import { ExternalLink, Settings, Shield, Trophy, Users } from 'lucide-react';
import { apiClient } from '../../api/client';
import type { ClubLeaderboardMember, ClubLeaderboardResponse, ClubSummary } from '../../types';
import { Badge } from '../ui/Badge';
import { BottomSheet } from '../ui/BottomSheet';
import { Button } from '../ui/Button';
import { AvatarStack } from '../ui/AvatarStack';

interface ClubBadgeProps {
  club: ClubSummary;
  busy?: boolean;
  onOpenSettings: (club: ClubSummary) => void;
  onRemove: (club: ClubSummary) => void;
}

function getStatus(progress: number): { label: string; variant: 'good' | 'warn' | 'bad' } {
  if (progress >= 70) return { label: 'On track', variant: 'good' };
  if (progress >= 40) return { label: 'Building', variant: 'warn' };
  return { label: 'Needs push', variant: 'bad' };
}

function formatValue(value: number, metricType: string): string {
  if (metricType === 'hours') {
    return `${value.toFixed(value % 1 === 0 ? 0 : 1)}h`;
  }
  return String(Math.round(value));
}

function formatBreakdown(member: ClubLeaderboardMember): string {
  if (!member.breakdown.length) return 'No activity yet';
  return member.breakdown
    .slice(0, 3)
    .map((item) => `${item.promise_text}: ${formatValue(item.achieved_value, item.metric_type)}/${formatValue(item.target_value, item.metric_type)}`)
    .join(' | ');
}

export function ClubBadge({ club, busy = false, onOpenSettings, onRemove }: ClubBadgeProps) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const [leaderboard, setLeaderboard] = useState<ClubLeaderboardResponse | null>(null);
  const [leaderboardLoading, setLeaderboardLoading] = useState(false);
  const [leaderboardError, setLeaderboardError] = useState('');
  const progress = leaderboard?.average_score_percent ?? 0;
  const status = getStatus(progress);
  const topMember = leaderboard?.members[0];
  const telegramReady = !!club.telegram_invite_link && ['ready', 'connected'].includes(club.telegram_status);

  const openSheet = () => setSheetOpen(true);
  const closeSheet = () => setSheetOpen(false);

  useEffect(() => {
    if (!sheetOpen || leaderboard) return;
    let cancelled = false;
    setLeaderboardLoading(true);
    setLeaderboardError('');
    apiClient.getClubLeaderboard(club.club_id)
      .then((data) => {
        if (!cancelled) setLeaderboard(data);
      })
      .catch((err) => {
        if (!cancelled) {
          console.error('Failed to load club leaderboard:', err);
          setLeaderboardError(err instanceof Error ? err.message : 'Failed to load leaderboard.');
        }
      })
      .finally(() => {
        if (!cancelled) setLeaderboardLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [club.club_id, leaderboard, sheetOpen]);

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    openSheet();
  };

  return (
    <>
      <article
        className={['pcard', 'club-badge-card', leaderboard ? status.variant : ''].filter(Boolean).join(' ')}
        role="button"
        tabIndex={0}
        aria-label={`Open ${club.name} club`}
        onClick={openSheet}
        onKeyDown={handleKeyDown}
      >
        <div className="top">
          <div className="title">
            <span dir="auto">{club.name}</span>
            <span className="pid" dir="ltr">#{club.visibility}</span>
          </div>
          <Badge variant={leaderboard ? status.variant : 'neutral'} showDot={!!leaderboard}>
            {leaderboard ? status.label : 'Club'}
          </Badge>
        </div>

        <p className="club-badge-promise">{club.promise_text || 'No shared promise yet'}</p>

        <div className="club-badge-member-strip">
          <AvatarStack users={club.members} size={24} max={5} />
          <span>{club.member_count} {club.member_count === 1 ? 'member' : 'members'}</span>
          <span>{club.promise_count || (club.promise_uuid ? 1 : 0)} {(club.promise_count || 0) === 1 ? 'promise' : 'promises'}</span>
          {topMember ? <span>Lead: {topMember.first_name || topMember.username || 'Member'}</span> : null}
        </div>

        {leaderboard ? (
          <div className="progress" aria-hidden="true">
            <div className="fill" style={{ width: `${progress}%` }} />
          </div>
        ) : null}

        <div className="row">
          <span className="sub" dir="ltr">{leaderboard ? `${leaderboard.window_start} - ${leaderboard.window_end}` : 'Open leaderboard'}</span>
          <span className="meta" dir="ltr">{leaderboard ? `${progress}%` : 'Rolling 7d'}</span>
        </div>
      </article>

      <BottomSheet
        open={sheetOpen}
        onClose={closeSheet}
        title={club.name}
        subtitle={club.promise_text || 'Club promise'}
        headerActions={(
          <button
            type="button"
            className="btn btn-ghost btn-sm sheet-icon-action"
            onClick={() => onOpenSettings(club)}
            aria-label="Open club settings"
          >
            <Settings size={18} aria-hidden />
          </button>
        )}
      >
        <section className="overall club-sheet-overall">
          <div className="row">
            <span className="label">Club progress</span>
            <span className="sub">{leaderboard?.member_count ?? club.member_count} members</span>
          </div>
          <div className="row" style={{ marginTop: 2 }}>
            <span className="value">{progress}%</span>
            <Badge variant={status.variant} showDot>{status.label}</Badge>
          </div>
          <div className="track" style={{ marginTop: 10 }}>
            <div className="fill" style={{ width: `${progress}%` }} />
          </div>
          <div className="club-sheet-stats">
            <span><Users size={14} aria-hidden /> {leaderboard?.member_count ?? club.member_count}</span>
            <span><Trophy size={14} aria-hidden /> {leaderboard ? `${leaderboard.average_score_percent}% avg` : 'Loading'}</span>
            <span><Shield size={14} aria-hidden /> {club.role}</span>
          </div>
        </section>

        <div className="club-sheet-section-head">
          <p className="ds-eyebrow">Leaderboard</p>
          {leaderboard ? <span className="club-sheet-window">{leaderboard.window_start} - {leaderboard.window_end}</span> : null}
        </div>

        <div className="club-leaderboard">
          {leaderboardLoading ? (
            <div className="club-leaderboard-state">Loading leaderboard...</div>
          ) : leaderboardError ? (
            <div className="club-leaderboard-state club-leaderboard-state--error">{leaderboardError}</div>
          ) : leaderboard && leaderboard.members.length === 0 ? (
            <div className="club-leaderboard-state">No leaderboard activity yet.</div>
          ) : leaderboard?.members.map((member) => (
            <div className="club-leaderboard-row" key={member.user_id}>
              <span className="club-leaderboard-rank">{member.rank}</span>
              <div className="club-leaderboard-person">
                <strong>{member.first_name || member.username || 'Member'}</strong>
                <span>{member.freeze_streak} day streak | {formatBreakdown(member)}</span>
              </div>
              <div className="club-leaderboard-progress">
                <span>{member.score_percent}%</span>
                <div className="club-leaderboard-track" aria-hidden="true">
                  <div style={{ width: `${member.score_percent}%` }} />
                </div>
              </div>
            </div>
          )) || null}
        </div>

        <div className="action-row club-sheet-actions">
          {telegramReady ? (
            <Button
              variant="secondary"
              onClick={() => window.open(club.telegram_invite_link, '_blank', 'noopener,noreferrer')}
            >
              <ExternalLink size={14} />
              Telegram
            </Button>
          ) : (
            <Button variant="secondary" disabled>
              <ExternalLink size={14} />
              Pending
            </Button>
          )}
          <Button variant="secondary" onClick={() => onOpenSettings(club)}>
            <Settings size={14} />
            Manage
          </Button>
          <Button
            variant="danger"
            disabled={busy}
            onClick={() => {
              closeSheet();
              onRemove(club);
            }}
          >
            {club.role === 'owner' ? 'Cancel' : 'Leave'}
          </Button>
        </div>
      </BottomSheet>
    </>
  );
}
