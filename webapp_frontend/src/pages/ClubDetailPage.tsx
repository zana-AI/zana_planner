import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { apiClient, ApiError } from '../api/client';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import type { ClubSummary } from '../types';
import { AvatarStack } from '../components/ui/AvatarStack';
import { Button } from '../components/ui/Button';

export function ClubDetailPage() {
  const { clubId } = useParams<{ clubId: string }>();
  const navigate = useNavigate();
  const { initData, hapticFeedback } = useTelegramWebApp();
  const [club, setClub] = useState<ClubSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (initData) {
      apiClient.setInitData(initData);
    }
  }, [initData]);

  useEffect(() => {
    if (!clubId) {
      setError('Club ID is required');
      setLoading(false);
      return;
    }

    const fetchClub = async () => {
      setLoading(true);
      setError('');
      try {
        const response = await apiClient.getMyClubs();
        const found = response.clubs.find((item) => item.club_id === clubId);
        if (!found) {
          setError('Club not found');
          setClub(null);
          return;
        }
        setClub(found);
      } catch (err) {
        console.error('Failed to fetch club:', err);
        setError(err instanceof ApiError ? err.message : 'Failed to load club');
      } finally {
        setLoading(false);
      }
    };

    fetchClub();
  }, [clubId]);

  const handleRemoveClub = async () => {
    if (!club) return;

    const isOwner = club.role === 'owner';
    const actionLabel = isOwner ? 'cancel this club' : 'leave this club';
    if (!window.confirm(`Are you sure you want to ${actionLabel}?`)) {
      return;
    }

    setBusy(true);
    setError('');
    try {
      await apiClient.removeMyClub(club.club_id);
      hapticFeedback('success');
      navigate('/community', { replace: true });
    } catch (err) {
      console.error('Failed to update club:', err);
      hapticFeedback('error');
      setError(err instanceof ApiError ? err.message : 'Failed to update club.');
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="app">
        <div className="loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading club...</div>
        </div>
      </div>
    );
  }

  if (error || !club) {
    return (
      <div className="app">
        <div className="error">
          <div className="error-icon">!</div>
          <h1 className="error-title">Club not found</h1>
          <p className="error-message">{error || 'The club you are looking for does not exist.'}</p>
          <Button variant="secondary" onClick={() => navigate('/community')}>
            Back to Community
          </Button>
        </div>
      </div>
    );
  }

  const telegramReady = !!club.telegram_invite_link && ['ready', 'connected'].includes(club.telegram_status);

  return (
    <div className="app">
      <div className="club-detail-container">
        <Button variant="ghost" size="sm" onClick={() => navigate('/community')}>
          Back to Community
        </Button>

        <section className="club-detail-card">
          <div className="club-detail-header">
            <div>
              <p className="club-detail-eyebrow">{club.visibility} club · {club.role}</p>
              <h2>{club.name}</h2>
            </div>
            <span className="club-detail-status">{club.telegram_status.replace(/_/g, ' ')}</span>
          </div>

          <div className="club-detail-section">
            <span className="club-detail-label">Shared promise</span>
            <p className="club-detail-promise">{club.promise_text || 'No shared promise yet'}</p>
          </div>

          <div className="club-detail-grid">
            <div className="club-detail-section">
              <span className="club-detail-label">Members</span>
              <div className="club-detail-members-summary">
                <AvatarStack users={club.members} size={28} max={5} />
                <span>{club.member_count} {club.member_count === 1 ? 'member' : 'members'}</span>
              </div>
            </div>

            <div className="club-detail-section">
              <span className="club-detail-label">Weekly target</span>
              <p className="club-detail-value">
                {club.target_count_per_week ? `${club.target_count_per_week} times per week` : 'No weekly target'}
              </p>
            </div>
          </div>

          <div className="club-detail-section">
            <span className="club-detail-label">People</span>
            <div className="club-detail-members">
              {club.members.map((member) => (
                <span className="club-detail-member" key={member.user_id}>
                  {member.first_name || member.username || `User ${member.user_id}`}
                </span>
              ))}
              {club.member_count > club.members.length ? (
                <span className="club-detail-member">+{club.member_count - club.members.length} more</span>
              ) : null}
            </div>
          </div>

          {error ? <div className="modal-error">{error}</div> : null}

          <div className="club-detail-actions">
            {telegramReady ? (
              <a
                className="modal-button modal-button-primary club-detail-action-link"
                href={club.telegram_invite_link}
                target="_blank"
                rel="noreferrer"
              >
                Join Telegram
              </a>
            ) : (
              <button type="button" className="modal-button modal-button-secondary" disabled>
                Telegram pending
              </button>
            )}

            <Button variant="danger" onClick={handleRemoveClub} disabled={busy}>
              {busy ? 'Updating...' : club.role === 'owner' ? 'Cancel club' : 'Leave club'}
            </Button>
          </div>
        </section>
      </div>
    </div>
  );
}
