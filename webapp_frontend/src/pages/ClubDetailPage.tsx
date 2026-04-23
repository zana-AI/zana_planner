import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { apiClient, ApiError } from '../api/client';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import type { ClubSummary } from '../types';
import { Button } from '../components/ui/Button';

export function ClubDetailPage() {
  const { clubId } = useParams<{ clubId: string }>();
  const navigate = useNavigate();
  const { initData, hapticFeedback } = useTelegramWebApp();
  const [club, setClub] = useState<ClubSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [editingPromise, setEditingPromise] = useState(false);
  const [editText, setEditText] = useState('');
  const [editTarget, setEditTarget] = useState<number | ''>('');
  const [editingSettings, setEditingSettings] = useState(false);
  const [editReminderTime, setEditReminderTime] = useState('');
  const [botUsername, setBotUsername] = useState('');

  useEffect(() => {
    if (initData) {
      apiClient.setInitData(initData);
    }
  }, [initData]);

  useEffect(() => {
    fetch('/api/auth/bot-username')
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (d?.bot_username) setBotUsername(d.bot_username.trim()); })
      .catch(() => {});
  }, []);

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

  const handleEditPromise = () => {
    if (!club) return;
    setEditText(club.promise_text || '');
    setEditTarget(club.target_count_per_week ?? '');
    setEditingPromise(true);
  };

  const maybeSyncDescription = async (clubId: string, hasTelegram: boolean) => {
    if (!hasTelegram) return;
    if (window.confirm('Update the Telegram group description with the latest promise and reminder?')) {
      try {
        await apiClient.syncClubDescription(clubId);
      } catch {
        setError('Saved, but failed to update group description.');
      }
    }
  };

  const handleSavePromise = async () => {
    if (!club?.promise_uuid) return;
    setBusy(true);
    setError('');
    try {
      const updated = await apiClient.updateClubPromise(club.club_id, club.promise_uuid, {
        promise_text: editText || undefined,
        target_count_per_week: editTarget !== '' ? Number(editTarget) : undefined,
      });
      setClub(updated);
      setEditingPromise(false);
      hapticFeedback('success');
      await maybeSyncDescription(club.club_id, telegramReady);
    } catch (err) {
      hapticFeedback('error');
      setError(err instanceof ApiError ? err.message : 'Failed to update promise.');
    } finally {
      setBusy(false);
    }
  };

  const handleEditSettings = () => {
    if (!club) return;
    setEditReminderTime(club.reminder_time || '21:00');
    setEditingSettings(true);
  };

  const handleSaveSettings = async () => {
    if (!club) return;
    setBusy(true);
    setError('');
    try {
      const updated = await apiClient.updateClub(club.club_id, { reminder_time: editReminderTime });
      setClub(updated);
      setEditingSettings(false);
      hapticFeedback('success');
      await maybeSyncDescription(club.club_id, telegramReady);
    } catch (err) {
      hapticFeedback('error');
      setError(err instanceof ApiError ? err.message : 'Failed to save settings.');
    } finally {
      setBusy(false);
    }
  };

  const handleDeletePromise = async () => {
    if (!club?.promise_uuid) return;
    if (!window.confirm('Delete this club promise? This cannot be undone.')) return;
    setBusy(true);
    setError('');
    try {
      await apiClient.deleteClubPromise(club.club_id, club.promise_uuid);
      setClub({ ...club, promise_uuid: undefined, promise_text: undefined, target_count_per_week: undefined });
      hapticFeedback('success');
    } catch (err) {
      hapticFeedback('error');
      setError(err instanceof ApiError ? err.message : 'Failed to delete promise.');
    } finally {
      setBusy(false);
    }
  };

  const handleInvite = () => {
    if (!club || !botUsername) return;
    const botLink = `https://t.me/${botUsername}?start=invite_${club.club_id}`;
    const groupLink = club.telegram_invite_link;
    const mainUrl = groupLink || botLink;
    const textLines = [`Join me in "${club.name}" on Xaana!`];
    if (groupLink) textLines.push(`Open in app: ${botLink}`);
    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(mainUrl)}&text=${encodeURIComponent(textLines.join('\n'))}`;
    window.Telegram?.WebApp?.openTelegramLink(shareUrl);
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
        </div>
      </div>
    );
  }

  const isAdmin = club.role === 'owner';
  const telegramReady = !!club.telegram_invite_link && ['ready', 'connected'].includes(club.telegram_status);
  const statusLabel = club.telegram_status.replace(/_/g, ' ');
  const promiseLine = club.promise_text
    ? `${club.promise_text}${club.target_count_per_week ? ` · ${club.target_count_per_week}×/week` : ''}`
    : null;

  return (
    <div className="app">
      <div className="club-detail-container">
        <section className="club-detail-card">

          {/* Header */}
          <div className="club-detail-header2">
            <div className="club-detail-title-row">
              <h2 className="club-detail-name">{club.name}</h2>
              <div className="club-detail-badges">
                <span className="club-badge club-badge--visibility">{club.visibility}</span>
                <span className={`club-badge club-badge--status club-badge--${club.telegram_status}`}>{statusLabel}</span>
              </div>
            </div>
            <p className="club-detail-role">{club.role}</p>
          </div>

          {/* Promise */}
          <div className="club-detail-section">
            <div className="club-detail-label-row">
              <span className="club-detail-label">Promise</span>
              {isAdmin && !editingPromise && (
                <span className="club-detail-admin-actions">
                  {club.promise_uuid && club.promise_text ? (
                    <>
                      <button type="button" className="club-detail-action-btn" onClick={handleEditPromise} disabled={busy}>Edit</button>
                      <button type="button" className="club-detail-action-btn club-detail-action-btn--danger" onClick={handleDeletePromise} disabled={busy}>Delete</button>
                    </>
                  ) : (
                    <button type="button" className="club-detail-action-btn" onClick={handleEditPromise} disabled={busy}>+ Add</button>
                  )}
                </span>
              )}
            </div>
            {editingPromise ? (
              <div className="club-detail-edit-form">
                <input className="club-detail-edit-input" value={editText} onChange={(e) => setEditText(e.target.value)} maxLength={160} placeholder="What will the group do?" />
                <input className="club-detail-edit-input" type="number" min={1} max={21} value={editTarget} onChange={(e) => setEditTarget(e.target.value === '' ? '' : Number(e.target.value))} placeholder="Times per week" />
                <div className="club-detail-edit-buttons">
                  <button type="button" className="modal-button modal-button-primary" onClick={handleSavePromise} disabled={busy || !editText.trim()}>{busy ? 'Saving…' : 'Save'}</button>
                  <button type="button" className="modal-button modal-button-secondary" onClick={() => setEditingPromise(false)} disabled={busy}>Cancel</button>
                </div>
              </div>
            ) : promiseLine ? (
              <p className="club-detail-promise">{promiseLine}</p>
            ) : (
              <p className="club-detail-empty">No promise set yet.</p>
            )}
          </div>

          {/* Members */}
          <div className="club-detail-section">
            <span className="club-detail-label">Members · {club.member_count}</span>
            <div className="club-detail-members">
              {club.members.map((member) => (
                <span className="club-detail-member" key={member.user_id}>
                  {member.first_name || member.username || 'Member'}
                </span>
              ))}
              {club.member_count > club.members.length && (
                <span className="club-detail-member">+{club.member_count - club.members.length} more</span>
              )}
            </div>
          </div>

          {/* Reminder (admin only) */}
          {isAdmin && (
            <div className="club-detail-section">
              <div className="club-detail-label-row">
                <span className="club-detail-label">Daily reminder</span>
                {!editingSettings && (
                  <button type="button" className="club-detail-action-btn" onClick={handleEditSettings} disabled={busy}>Edit</button>
                )}
              </div>
              {editingSettings ? (
                <div className="club-detail-edit-form">
                  <input className="club-detail-edit-input" type="time" value={editReminderTime} onChange={(e) => setEditReminderTime(e.target.value)} />
                  <p className="club-detail-hint">In your local timezone.</p>
                  <div className="club-detail-edit-buttons">
                    <button type="button" className="modal-button modal-button-primary" onClick={handleSaveSettings} disabled={busy || !editReminderTime}>{busy ? 'Saving…' : 'Save'}</button>
                    <button type="button" className="modal-button modal-button-secondary" onClick={() => setEditingSettings(false)} disabled={busy}>Cancel</button>
                  </div>
                </div>
              ) : (
                <p className="club-detail-promise">{club.reminder_time ?? '21:00'} daily</p>
              )}
            </div>
          )}

          {error && <div className="modal-error">{error}</div>}

          {/* Actions */}
          <div className="club-detail-actions">
            {telegramReady ? (
              <a className="modal-button modal-button-primary club-detail-action-link" href={club.telegram_invite_link} target="_blank" rel="noreferrer">
                Join Telegram
              </a>
            ) : (
              <button type="button" className="modal-button modal-button-secondary" disabled>
                {club.telegram_status === 'not_connected' ? 'No Telegram group' : 'Telegram pending…'}
              </button>
            )}
            {botUsername && (
              <button type="button" className="modal-button modal-button-secondary" onClick={handleInvite}>
                Invite
              </button>
            )}
            <Button variant="danger" onClick={handleRemoveClub} disabled={busy}>
              {busy ? 'Updating…' : isAdmin ? 'Cancel club' : 'Leave club'}
            </Button>
          </div>

        </section>
      </div>
    </div>
  );
}
