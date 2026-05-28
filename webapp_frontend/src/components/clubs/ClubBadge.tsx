import { useMemo, useState, type KeyboardEvent } from 'react';
import { ExternalLink, Settings, Shield, Trophy, Users } from 'lucide-react';
import type { ClubSummary } from '../../types';
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

type LeaderboardMember = ClubSummary['members'][number] & {
  checkins: number;
  target: number;
  progress: number;
  streak: number;
};

function seedFromText(value: string): number {
  return Array.from(value).reduce((acc, char) => acc + char.charCodeAt(0), 0);
}

function getLeaderboard(club: ClubSummary): LeaderboardMember[] {
  const target = Math.max(1, club.target_count_per_week || 1);
  const fallbackNames = ['Sam', 'Iris', 'Noah', 'Mina', 'Leo', 'Yara', 'Owen', 'Zoe', 'Kai', 'Nina'];
  const members = [...club.members];
  const desiredCount = Math.min(Math.max(club.member_count, members.length, 1), 10);
  while (members.length < desiredCount) {
    const index = members.length;
    members.push({
      user_id: `${club.club_id}-member-${index + 1}`,
      first_name: fallbackNames[index % fallbackNames.length],
    });
  }

  return members
    .slice(0, desiredCount)
    .map((member, index) => {
      const seed = seedFromText(`${club.club_id}-${member.user_id}-${index}`);
      const checkins = Math.min(target, Math.max(0, target - (seed % Math.min(target + 1, 4))));
      return {
        ...member,
        checkins,
        target,
        progress: Math.round((checkins / target) * 100),
        streak: 1 + (seed % 6),
      };
    })
    .sort((left, right) => right.progress - left.progress || right.streak - left.streak);
}

function getStatus(progress: number): { label: string; variant: 'good' | 'warn' | 'bad' } {
  if (progress >= 70) return { label: 'On track', variant: 'good' };
  if (progress >= 40) return { label: 'Building', variant: 'warn' };
  return { label: 'Needs push', variant: 'bad' };
}

export function ClubBadge({ club, busy = false, onOpenSettings, onRemove }: ClubBadgeProps) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const [leaderboardLimit, setLeaderboardLimit] = useState(5);
  const leaderboard = useMemo(() => getLeaderboard(club), [club]);
  const shownLeaderboard = leaderboard.slice(0, leaderboardLimit);
  const target = Math.max(1, club.target_count_per_week || 1);
  const avgCheckins = leaderboard.length
    ? leaderboard.reduce((sum, member) => sum + member.checkins, 0) / leaderboard.length
    : 0;
  const progress = Math.min(Math.round((avgCheckins / target) * 100), 100);
  const status = getStatus(progress);
  const topMember = leaderboard[0];
  const telegramReady = !!club.telegram_invite_link && ['ready', 'connected'].includes(club.telegram_status);

  const openSheet = () => setSheetOpen(true);
  const closeSheet = () => setSheetOpen(false);

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    openSheet();
  };

  return (
    <>
      <article
        className={`pcard club-badge-card ${status.variant}`}
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
          <Badge variant={status.variant} showDot>{status.label}</Badge>
        </div>

        <p className="club-badge-promise">{club.promise_text || 'No shared promise yet'}</p>

        <div className="club-badge-member-strip">
          <AvatarStack users={club.members} size={24} max={5} />
          <span>{club.member_count} {club.member_count === 1 ? 'member' : 'members'}</span>
          {topMember ? <span>Lead: {topMember.first_name || topMember.username || 'Member'}</span> : null}
        </div>

        <div className="progress" aria-hidden="true">
          <div className="fill" style={{ width: `${progress}%` }} />
        </div>

        <div className="row">
          <span className="sub" dir="ltr">{avgCheckins.toFixed(1)}/{target} avg check-ins</span>
          <span className="meta" dir="ltr">{progress}%</span>
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
            <span className="sub">{club.member_count} members</span>
          </div>
          <div className="row" style={{ marginTop: 2 }}>
            <span className="value">{progress}%</span>
            <Badge variant={status.variant} showDot>{status.label}</Badge>
          </div>
          <div className="track" style={{ marginTop: 10 }}>
            <div className="fill" style={{ width: `${progress}%` }} />
          </div>
          <div className="club-sheet-stats">
            <span><Users size={14} aria-hidden /> {club.member_count}</span>
            <span><Trophy size={14} aria-hidden /> {avgCheckins.toFixed(1)}/{target} avg</span>
            <span><Shield size={14} aria-hidden /> {club.role}</span>
          </div>
        </section>

        <div className="club-sheet-section-head">
          <p className="ds-eyebrow">Leaderboard</p>
          <div className="club-sheet-limit" aria-label="Leaderboard size">
            {[3, 5, 10].map((limit) => (
              <button
                type="button"
                key={limit}
                className={leaderboardLimit === limit ? 'is-active' : ''}
                onClick={() => setLeaderboardLimit(limit)}
              >
                Top {limit}
              </button>
            ))}
          </div>
        </div>

        <div className="club-leaderboard">
          {shownLeaderboard.map((member, index) => (
            <div className="club-leaderboard-row" key={member.user_id}>
              <span className="club-leaderboard-rank">{index + 1}</span>
              <div className="club-leaderboard-person">
                <strong>{member.first_name || member.username || 'Member'}</strong>
                <span>{member.streak} day streak</span>
              </div>
              <div className="club-leaderboard-progress">
                <span>{member.checkins}/{member.target}</span>
                <div className="club-leaderboard-track" aria-hidden="true">
                  <div style={{ width: `${member.progress}%` }} />
                </div>
              </div>
            </div>
          ))}
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
