import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient, ApiError } from '../api/client';
import { BottomSheet } from './ui/BottomSheet';
import type { ClubSharedContent, ClubSummary } from '../types';

export function ClubSharedShelf({ query, onSaved }: { query: string; onSaved: () => void }) {
  const { t } = useTranslation();
  const [clubs, setClubs] = useState<ClubSummary[]>([]);
  const [clubId, setClubId] = useState('');
  const [items, setItems] = useState<ClubSharedContent[]>([]);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState('');
  const [error, setError] = useState('');
  const [removeTarget, setRemoveTarget] = useState<ClubSharedContent | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let active = true;
    void apiClient.getMyClubs().then((response) => {
      if (active) setClubs(response.clubs);
    }).catch(() => { /* The shelf itself reports a load error. */ });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    void apiClient.getClubSharedContent({ clubId: clubId || undefined, q: query.trim() || undefined })
      .then((response) => {
        if (!active) return;
        setItems(response.items);
        setNextOffset(response.next_offset);
      })
      .catch((err) => { if (active) setError(err instanceof ApiError ? err.message : t('content.sharedShelfLoadFailed')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [clubId, query, t, version]);

  const save = async (item: ClubSharedContent) => {
    setBusyId(item.content_id);
    setError('');
    try {
      if (item.saved_status) {
        await apiClient.updateUserContent(item.content_id, { status: 'saved' });
      } else {
        await apiClient.addUserContent(item.content_id);
      }
      setItems((previous) => previous.map((current) => current.content_id === item.content_id
        ? { ...current, saved_status: 'saved' } : current));
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('content.sharedShelfSaveFailed'));
    } finally {
      setBusyId('');
    }
  };

  const remove = async () => {
    if (!removeTarget) return;
    setBusyId(removeTarget.content_id);
    setError('');
    try {
      await apiClient.removeClubContentShare(removeTarget.content_id, removeTarget.club_id);
      setRemoveTarget(null);
      setVersion((value) => value + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('content.sharedShelfRemoveFailed'));
    } finally {
      setBusyId('');
    }
  };

  const loadMore = async () => {
    if (nextOffset == null || loading) return;
    setLoading(true);
    try {
      const response = await apiClient.getClubSharedContent({ clubId: clubId || undefined, q: query.trim() || undefined, offset: nextOffset });
      setItems((previous) => [...previous, ...response.items]);
      setNextOffset(response.next_offset);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('content.sharedShelfLoadFailed'));
    } finally {
      setLoading(false);
    }
  };

  return <section className="club-shared-shelf" aria-label={t('content.sharedWithClubs')}>
    <div className="club-shared-shelf-head">
      <p>{t('content.sharedShelfHint')}</p>
      {clubs.length > 1 && <label>{t('content.club')}
        <select value={clubId} onChange={(event) => setClubId(event.target.value)}>
          <option value="">{t('content.allClubs')}</option>
          {clubs.map((club) => <option key={club.club_id} value={club.club_id}>{club.name}</option>)}
        </select>
      </label>}
    </div>
    {error && <p className="content-library-error" role="alert">{error}</p>}
    {loading && items.length === 0 ? <p className="content-library-state">{t('myContents.loadingLibrary')}</p>
      : items.length === 0 ? <p className="content-library-state">{t('content.sharedShelfEmpty')}</p>
      : <div className="club-shared-shelf-list">{items.map((item) => <article className="club-shared-item" key={`${item.club_id}:${item.content_id}`}>
        {item.thumbnail_url && <img src={item.thumbnail_url} alt="" loading="lazy" />}
        <div className="club-shared-item-body">
          <small>{item.club_name}{item.language ? ` · ${item.language.toUpperCase()}` : ''}</small>
          <strong>{item.title}</strong>
          <div className="club-shared-item-actions">
            {item.saved_status === 'saved' ? <a href={item.path}>{t('content.openSharedItem')}</a>
              : <button type="button" disabled={busyId === item.content_id} onClick={() => void save(item)}>{t(item.saved_status === 'archived' ? 'content.restoreToLibrary' : 'content.saveToLibrary')}</button>}
            {item.can_remove && <button type="button" className="club-shared-remove" onClick={() => setRemoveTarget(item)}>{t('content.removeClubShare')}</button>}
          </div>
        </div>
      </article>)}</div>}
    {nextOffset != null && <button type="button" className="content-library-load-more" disabled={loading} onClick={() => void loadMore()}>{t('content.loadMore')}</button>}
    <BottomSheet open={!!removeTarget} onClose={() => !busyId && setRemoveTarget(null)}
      title={t('content.removeClubShare')} subtitle={removeTarget?.title || ''}>
      <p className="content-library-sheet-note">{t('content.removeClubShareHint', { club: removeTarget?.club_name })}</p>
      <div className="content-library-sheet-actions">
        <button type="button" className="btn btn-ghost" onClick={() => setRemoveTarget(null)}>{t('common.cancel')}</button>
        <button type="button" className="btn btn-primary" disabled={!!busyId} onClick={() => void remove()}>{t('content.removeClubShare')}</button>
      </div>
    </BottomSheet>
  </section>;
}
