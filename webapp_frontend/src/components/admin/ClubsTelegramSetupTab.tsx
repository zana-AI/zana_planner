import { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../api/client';
import type { AdminClubSetupSummary } from '../../types';

type ClubContextDraft = {
  description: string;
  club_goal: string;
  vibe: string;
  checkin_what_counts: string;
};

interface ClubsTelegramSetupTabProps {
  highlightClubId?: string | null;
  onError: (message: string) => void;
}

function contextDraftFromClub(club: AdminClubSetupSummary): ClubContextDraft {
  return {
    description: club.description || '',
    club_goal: club.club_goal || '',
    vibe: club.vibe || '',
    checkin_what_counts: club.checkin_what_counts || '',
  };
}

export function ClubsTelegramSetupTab({ highlightClubId, onError }: ClubsTelegramSetupTabProps) {
  const [clubs, setClubs] = useState<AdminClubSetupSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingByClub, setSavingByClub] = useState<Record<string, boolean>>({});
  const [savingContextByClub, setSavingContextByClub] = useState<Record<string, boolean>>({});
  const [linksByClub, setLinksByClub] = useState<Record<string, string>>({});
  const [contextByClub, setContextByClub] = useState<Record<string, ClubContextDraft>>({});
  const [status, setStatus] = useState<'pending' | 'ready' | 'all'>(highlightClubId ? 'all' : 'pending');
  const [savedClubId, setSavedClubId] = useState<string | null>(null);
  const [savedContextClubId, setSavedContextClubId] = useState<string | null>(null);

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
      setContextByClub((prev) => {
        const next = { ...prev };
        response.clubs.forEach((club) => {
          if (!(club.club_id in next)) {
            next[club.club_id] = contextDraftFromClub(club);
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

  const updateContextDraft = (clubId: string, field: keyof ClubContextDraft, value: string) => {
    setContextByClub((prev) => ({
      ...prev,
      [clubId]: {
        ...(prev[clubId] || { description: '', club_goal: '', vibe: '', checkin_what_counts: '' }),
        [field]: value,
      },
    }));
  };

  const saveContext = async (club: AdminClubSetupSummary) => {
    const draft = contextByClub[club.club_id] || contextDraftFromClub(club);
    setSavingContextByClub((prev) => ({ ...prev, [club.club_id]: true }));
    setSavedContextClubId(null);
    try {
      const updated = await apiClient.updateAdminClubContext(club.club_id, {
        description: draft.description.trim(),
        club_goal: draft.club_goal.trim(),
        vibe: draft.vibe.trim(),
        checkin_what_counts: draft.checkin_what_counts.trim(),
      });
      setClubs((prev) => prev.map((item) => (item.club_id === updated.club_id ? updated : item)));
      setContextByClub((prev) => ({ ...prev, [updated.club_id]: contextDraftFromClub(updated) }));
      setSavedContextClubId(updated.club_id);
    } catch (err) {
      console.error('Failed to save club context:', err);
      onError(err instanceof Error ? err.message : 'Failed to save club context.');
    } finally {
      setSavingContextByClub((prev) => ({ ...prev, [club.club_id]: false }));
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

            <details className="admin-club-context" open={club.club_id === highlightClubId}>
              <summary>Club context</summary>
              <div className="admin-club-context-grid">
                <label>
                  <span>Description</span>
                  <textarea
                    value={(contextByClub[club.club_id] || contextDraftFromClub(club)).description}
                    onChange={(event) => updateContextDraft(club.club_id, 'description', event.target.value)}
                    rows={3}
                    placeholder="Who is this club for, and what brings members together?"
                  />
                </label>
                <label>
                  <span>Goal</span>
                  <textarea
                    value={(contextByClub[club.club_id] || contextDraftFromClub(club)).club_goal}
                    onChange={(event) => updateContextDraft(club.club_id, 'club_goal', event.target.value)}
                    rows={3}
                    placeholder="What should Xaana help this club create in members' lives?"
                  />
                </label>
                <label>
                  <span>Vibe</span>
                  <textarea
                    value={(contextByClub[club.club_id] || contextDraftFromClub(club)).vibe}
                    onChange={(event) => updateContextDraft(club.club_id, 'vibe', event.target.value)}
                    rows={2}
                    placeholder="Warm, direct, playful, strict, gentle..."
                  />
                </label>
                <label>
                  <span>What counts as check-in</span>
                  <textarea
                    value={(contextByClub[club.club_id] || contextDraftFromClub(club)).checkin_what_counts}
                    onChange={(event) => updateContextDraft(club.club_id, 'checkin_what_counts', event.target.value)}
                    rows={2}
                    placeholder="Define the concrete action members should report."
                  />
                </label>
              </div>

              <div className="admin-club-context-hint">
                <div>Example club context:</div>
                <ul>
                  <li>A small mutual-aid club where members help each other keep one weekly promise that benefits someone beyond themselves.</li>
                  <li>The goal is to turn good intentions into visible acts of care: calls, donations, volunteering, mentoring, or checking on someone.</li>
                  <li>Xaana should sound warm, practical, and gently accountable: celebrate tiny acts, ask clear follow-up questions, and avoid guilt.</li>
                  <li>A check-in counts when a member reports one concrete action they took for another person or community this week.</li>
                </ul>
              </div>

              <div className="admin-club-context-actions">
                <button
                  type="button"
                  className="admin-select-all-btn"
                  disabled={!!savingContextByClub[club.club_id]}
                  onClick={() => saveContext(club)}
                >
                  {savingContextByClub[club.club_id] ? 'Saving...' : 'Save context'}
                </button>
                {savedContextClubId === club.club_id ? (
                  <span className="admin-club-success">Context saved.</span>
                ) : null}
              </div>
            </details>
          </article>
        ))}
      </div>
    </section>
  );
}
