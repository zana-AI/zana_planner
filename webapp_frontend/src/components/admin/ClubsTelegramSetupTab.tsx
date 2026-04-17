import { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../api/client';
import type { AdminClubSetupSummary } from '../../types';

interface ClubsTelegramSetupTabProps {
  highlightClubId?: string | null;
  onError: (message: string) => void;
}

export function ClubsTelegramSetupTab({ highlightClubId, onError }: ClubsTelegramSetupTabProps) {
  const [clubs, setClubs] = useState<AdminClubSetupSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingByClub, setSavingByClub] = useState<Record<string, boolean>>({});
  const [linksByClub, setLinksByClub] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<'pending' | 'ready' | 'all'>(highlightClubId ? 'all' : 'pending');
  const [savedClubId, setSavedClubId] = useState<string | null>(null);

  const fetchClubs = async () => {
    setLoading(true);
    try {
      const response = await apiClient.getAdminClubTelegramSetup(status);
      setClubs(response.clubs);
      setLinksByClub((prev) => {
        const next = { ...prev };
        response.clubs.forEach((club) => {
          if (!(club.club_id in next)) {
            next[club.club_id] = club.telegram_invite_link || '';
          }
        });
        return next;
      });
    } catch (err) {
      console.error('Failed to load club setup queue:', err);
      onError(err instanceof Error ? err.message : 'Failed to load club setup queue.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchClubs();
  }, [status]);

  const sortedClubs = useMemo(() => {
    if (!highlightClubId) return clubs;
    return [...clubs].sort((left, right) => {
      if (left.club_id === highlightClubId) return -1;
      if (right.club_id === highlightClubId) return 1;
      return 0;
    });
  }, [clubs, highlightClubId]);

  const saveLink = async (club: AdminClubSetupSummary) => {
    const inviteLink = (linksByClub[club.club_id] || '').trim();
    if (!inviteLink) {
      onError('Paste the Telegram invite link first.');
      return;
    }

    setSavingByClub((prev) => ({ ...prev, [club.club_id]: true }));
    setSavedClubId(null);
    try {
      const updated = await apiClient.updateAdminClubTelegramLink(club.club_id, inviteLink);
      setClubs((prev) => prev.map((item) => (item.club_id === updated.club_id ? updated : item)));
      setLinksByClub((prev) => ({ ...prev, [updated.club_id]: updated.telegram_invite_link || inviteLink }));
      setSavedClubId(updated.club_id);
    } catch (err) {
      console.error('Failed to save Telegram link:', err);
      onError(err instanceof Error ? err.message : 'Failed to save Telegram link.');
    } finally {
      setSavingByClub((prev) => ({ ...prev, [club.club_id]: false }));
    }
  };

  return (
    <section className="admin-section admin-club-setup">
      <div className="admin-club-setup-header">
        <div>
          <h2 className="admin-section-title">Club Telegram Setup</h2>
          <p className="admin-club-setup-note">Create the Telegram group, add Xaana bot as admin, then save the invite link.</p>
        </div>
        <div className="admin-club-setup-filters">
          {(['pending', 'ready', 'all'] as const).map((item) => (
            <button
              key={item}
              type="button"
              className={`admin-club-filter ${status === item ? 'active' : ''}`}
              onClick={() => setStatus(item)}
            >
              {item}
            </button>
          ))}
          <button type="button" className="admin-club-filter" onClick={fetchClubs}>
            Refresh
          </button>
        </div>
      </div>

      {loading ? <div className="admin-empty-state">Loading club setup queue...</div> : null}

      {!loading && sortedClubs.length === 0 ? (
        <div className="admin-empty-state">No clubs in this setup queue.</div>
      ) : null}

      <div className="admin-club-setup-list">
        {sortedClubs.map((club) => (
          <article
            key={club.club_id}
            className={`admin-club-setup-card ${club.club_id === highlightClubId ? 'highlighted' : ''}`}
          >
            <div className="admin-club-setup-main">
              <div>
                <h3>{club.name}</h3>
                <p>Creator: {club.owner_name || club.owner_user_id}</p>
                <p>Promise: {club.promise_text || 'No shared promise'}</p>
              </div>
              <span className={`admin-club-status admin-club-status-${club.telegram_status}`}>
                {club.telegram_status.replace(/_/g, ' ')}
              </span>
            </div>

            <div className="admin-club-steps">
              <span>1. Create group</span>
              <span>2. Add Xaana bot as admin</span>
              <span>3. Save invite link</span>
            </div>

            <div className="admin-club-link-row">
              <input
                className="admin-search-input"
                value={linksByClub[club.club_id] || ''}
                onChange={(event) => setLinksByClub((prev) => ({ ...prev, [club.club_id]: event.target.value }))}
                placeholder="https://t.me/+..."
              />
              <button
                type="button"
                className="admin-select-all-btn"
                disabled={!!savingByClub[club.club_id]}
                onClick={() => saveLink(club)}
              >
                {savingByClub[club.club_id] ? 'Saving...' : 'Save link'}
              </button>
            </div>

            {savedClubId === club.club_id ? (
              <div className="admin-club-success">Saved. Creator notification queued.</div>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
