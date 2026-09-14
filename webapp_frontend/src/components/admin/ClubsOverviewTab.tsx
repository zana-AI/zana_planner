import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient, ApiError } from '../../api/client';
import type { AdminClubSetupSummary, AdminReserveGroup } from '../../types';

/** What each reserve state means operationally, shown when there's no error note. */
const RESERVE_HINT: Record<AdminReserveGroup['status'], string> = {
  available: 'Ready for the next new club.',
  assigning: 'Mid-allocation — if it stays here, allocation died partway.',
  allocated: 'Consumed by a club. Reserves are single-use.',
  needs_review: 'Quarantined — check the reason before re-registering.',
  disabled: 'Manually pulled out of the pool.',
};

export function ClubsOverviewTab() {
  const [clubs, setClubs] = useState<AdminClubSetupSummary[]>([]);
  const [reserves, setReserves] = useState<AdminReserveGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busyLabel, setBusyLabel] = useState('');
  const [showArchived, setShowArchived] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [clubResponse, reserveResponse] = await Promise.all([
        apiClient.getAdminClubTelegramSetup('all'),
        apiClient.getAdminClubReserves(),
      ]);
      setClubs(clubResponse.clubs);
      setReserves(reserveResponse.reserves);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load clubs.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const available = useMemo(
    () => reserves.filter((reserve) => reserve.status === 'available').length,
    [reserves],
  );

  const activeClubs = useMemo(
    () => clubs.filter((club) => (club.club_status ?? 'active') === 'active'),
    [clubs],
  );
  const archivedCount = clubs.length - activeClubs.length;
  const visibleClubs = showArchived ? clubs : activeClubs;

  const handleDisable = async (label: string) => {
    setBusyLabel(label);
    setError('');
    try {
      await apiClient.disableAdminClubReserve(label);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `Could not disable ${label}.`);
    } finally {
      setBusyLabel('');
    }
  };

  if (loading) {
    return <div className="admin-empty-state">Loading clubs...</div>;
  }

  return (
    <div className="admin-section">
      {error ? <div className="admin-club-setup-note">{error}</div> : null}

      <div className="admin-club-setup-header">
        <div>
          <h2>Reserve pool</h2>
          <p className="admin-club-setup-note">
            {available === 0
              ? 'Empty — the next new club falls back to manual Telegram setup.'
              : `${available} group${available === 1 ? '' : 's'} ready${available <= 1 ? ' — worth topping up.' : '.'}`}
          </p>
        </div>
        <div className="admin-club-setup-filters">
          <button type="button" className="admin-club-filter" onClick={() => void load()}>
            Refresh
          </button>
        </div>
      </div>

      {reserves.length === 0 ? (
        <div className="admin-empty-state">No reserve groups registered yet.</div>
      ) : (
        <div className="admin-club-setup-list">
          {reserves.map((reserve) => (
            <article key={reserve.label} className="admin-club-setup-card">
              <div className="admin-club-setup-main">
                <div>
                  <h3>{reserve.label}</h3>
                  <p>Chat ID: {reserve.chat_id}</p>
                  <p>{reserve.last_error || RESERVE_HINT[reserve.status]}</p>
                  {reserve.club_id ? <p>Club: {reserve.club_id}</p> : null}
                </div>
                <span className={`admin-club-status admin-club-status-${reserve.status}`}>
                  {reserve.status.replace(/_/g, ' ')}
                </span>
              </div>
              {reserve.status === 'available' ? (
                <div className="admin-club-context-actions">
                  <button
                    type="button"
                    className="admin-club-filter"
                    disabled={busyLabel === reserve.label}
                    onClick={() => void handleDisable(reserve.label)}
                  >
                    {busyLabel === reserve.label ? 'Disabling...' : 'Disable'}
                  </button>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      )}

      <div className="admin-club-setup-header">
        <div>
          <h2>Clubs ({visibleClubs.length})</h2>
          <p className="admin-club-setup-note">Every club, not just those awaiting setup.</p>
        </div>
        {archivedCount > 0 ? (
          <div className="admin-club-setup-filters">
            <button
              type="button"
              className={`admin-club-filter ${showArchived ? 'active' : ''}`}
              onClick={() => setShowArchived((prev) => !prev)}
            >
              {showArchived ? 'Hide' : 'Show'} {archivedCount} archived
            </button>
          </div>
        ) : null}
      </div>

      {visibleClubs.length === 0 ? (
        <div className="admin-empty-state">No clubs.</div>
      ) : (
        <div className="admin-club-setup-list">
          {visibleClubs.map((club) => {
            const archived = (club.club_status ?? 'active') !== 'active';
            return (
              <article key={club.club_id} className="admin-club-setup-card">
                <div className="admin-club-setup-main">
                  <div>
                    <h3>
                      {club.name}
                      {archived ? ' (archived)' : ''}
                    </h3>
                    <p>Owner: {club.owner_name || club.owner_user_id}</p>
                    <p>
                      {club.member_count} member{club.member_count === 1 ? '' : 's'}
                      {club.vibe ? ` - vibe: ${club.vibe}` : ''}
                    </p>
                    <p>Created: {(club.created_at_utc || '').slice(0, 10)}</p>
                  </div>
                  <span className={`admin-club-status admin-club-status-${club.telegram_status}`}>
                    {club.telegram_status.replace(/_/g, ' ')}
                  </span>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
