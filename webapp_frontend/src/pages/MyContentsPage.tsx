import { useTranslation } from 'react-i18next';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Filter, Plus, Search } from 'lucide-react';
import { apiClient, ApiError } from '../api/client';
import { ContentCard } from '../components/ContentCard';
import { BottomSheet } from '../components/ui/BottomSheet';
import { PlanContentSheet } from '../components/sheets/PlanContentSheet';
import { AssignContentSheet } from '../components/sheets/AssignContentSheet';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import { useNavigate, useSearchParams } from 'react-router-dom';
import type { ClubSummary, MyContentsFacets, UserContentWithDetails } from '../types';
import { restoredLibraryStatus } from '../utils/libraryArchive';
import './explore.css';

type StatusFilter = 'all' | 'in_progress' | 'saved' | 'completed' | 'archived';
type TypeFilter = 'all' | 'pdf' | 'video' | 'audio' | 'text';
type SortKey = 'recent' | 'added' | 'title' | 'progress';

// "All" leads because it is the default — the selected chip should be the first
// one, not buried second.
const STATUS_FILTERS: { key: StatusFilter; label: string }[] = [
  { key: 'all', label: 'all' },
  { key: 'in_progress', label: 'continue' },
  { key: 'saved', label: 'saved' },
  { key: 'completed', label: 'completed' },
  { key: 'archived', label: 'archived' },
];

// Decks sit in this list because they are a kind of thing the library holds,
// not a separate shelf beside it. The count comes from the client rather than
// the server facets: decks are few and are not paged.
const TYPE_FILTERS: { key: TypeFilter; label: string }[] = [
  { key: 'all', label: 'allTypes' },
  { key: 'pdf', label: 'pdfs' },
  { key: 'video', label: 'videos' },
  { key: 'audio', label: 'audio' },
  { key: 'text', label: 'articles' },
];

// "Recently added" leads because it is the default: the library is somewhere you
// put things, and the thing you just put in should be the thing you see.
const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: 'added', label: 'Recently added' },
  { key: 'recent', label: 'Recently read' },
  { key: 'progress', label: 'Most progress' },
  { key: 'title', label: 'Title A-Z' },
];

function extractYouTubeVideoId(rawUrl: string | null | undefined): string | null {
  const urlText = (rawUrl || '').trim();
  if (!urlText) return null;

  const patterns = [
    /(?:youtube\.com\/watch\?v=)([a-zA-Z0-9_-]{11})/i,
    /(?:youtu\.be\/)([a-zA-Z0-9_-]{11})/i,
    /(?:youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})/i,
    /(?:youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})/i,
  ];
  for (const pattern of patterns) {
    const match = urlText.match(pattern);
    if (match?.[1]) return match[1];
  }

  try {
    const parsed = new URL(urlText);
    if (parsed.hostname.toLowerCase().includes('youtube.com')) {
      const v = parsed.searchParams.get('v');
      if (v && /^[a-zA-Z0-9_-]{11}$/.test(v)) return v;
    }
  } catch {
    return null;
  }

  return null;
}

function getInternalYouTubeWatchUrl(item: UserContentWithDetails): string | null {
  const provider = (item.provider || '').toLowerCase();
  const metadataVideoId = typeof item.metadata_json?.['video_id'] === 'string'
    ? item.metadata_json['video_id']
    : null;
  const parsedVideoId = extractYouTubeVideoId(item.original_url || item.canonical_url);
  const videoId = metadataVideoId || parsedVideoId;

  if (provider !== 'youtube' && !videoId) return null;
  if (!videoId) return null;
  const contentId = item.content_id || item.id;
  const clubId = item.club_ids?.[0];
  return `/youtube-watch?video_id=${encodeURIComponent(videoId)}${contentId ? `&content_id=${encodeURIComponent(contentId)}` : ''}${clubId ? `&club_id=${encodeURIComponent(clubId)}` : ''}`;
}

/** Show sharing only for content with a supported public reader. */
function canShareLibraryItem(item: UserContentWithDetails): boolean {
  const provider = (item.provider || '').toLowerCase();
  const mime = String(item.metadata_json?.['mime_type'] || '').toLowerCase();
  if (provider === 'telegram_pdf' || mime === 'application/pdf') return true;
  const metadataVideoId = typeof item.metadata_json?.['video_id'] === 'string'
    ? item.metadata_json['video_id']
    : null;
  const videoId = metadataVideoId || extractYouTubeVideoId(item.original_url || item.canonical_url);
  return provider === 'youtube' && Boolean(videoId);
}

function getInternalPdfReaderUrl(item: UserContentWithDetails): string | null {
  const provider = (item.provider || '').toLowerCase();
  const mime = String(item.metadata_json?.['mime_type'] || '').toLowerCase();
  const isPdf = provider === 'telegram_pdf' || mime === 'application/pdf';
  if (!isPdf) return null;
  const contentId = item.content_id || item.id;
  if (!contentId) return null;
  const clubId = item.club_ids?.[0];
  return `/pdf-reader?content_id=${encodeURIComponent(contentId)}${clubId ? `&club_id=${encodeURIComponent(clubId)}` : ''}`;
}

export function MyContentsPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [planning, setPlanning] = useState<UserContentWithDetails | null>(null);
  const [assigning, setAssigning] = useState<UserContentWithDetails | null>(null);
  const [sharing, setSharing] = useState<UserContentWithDetails | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<UserContentWithDetails | null>(null);
  const [shareLanguage, setShareLanguage] = useState('');
  const [shareLevel, setShareLevel] = useState('');
  const [shareIsLearning, setShareIsLearning] = useState(false);
  const [shareBusy, setShareBusy] = useState(false);
  const [shareError, setShareError] = useState('');
  const [shareStep, setShareStep] = useState<'choose' | 'club' | 'explore'>('choose');
  const [shareClubs, setShareClubs] = useState<ClubSummary[]>([]);
  const [shareClubsLoading, setShareClubsLoading] = useState(false);
  const [selectedClubId, setSelectedClubId] = useState('');
  const [plannedToast, setPlannedToast] = useState('');
  const { hapticFeedback, webApp } = useTelegramWebApp();
  const [addUrl, setAddUrl] = useState('');
  const [addOpen, setAddOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState('');
  const [items, setItems] = useState<UserContentWithDetails[]>([]);
  const [facets, setFacets] = useState<MyContentsFacets>({});
  // Opens on the whole library, not on "Continue". As a sub-page this landed on
  // what you were mid-way through; as a primary tab it has to show everything —
  // a filter that hides what you just saved reads as the save having failed.
  const [status, setStatus] = useState<StatusFilter>('all');
  const [contentType, setContentType] = useState<TypeFilter>('all');
  const [language, setLanguage] = useState('all');
  const [sort, setSort] = useState<SortKey>('added');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const mutationInFlight = useRef(false);
  const loadSequence = useRef(0);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const requestedContentId = searchParams.get('content_id');
  const sharingIsPdf = sharing && ((sharing.provider || '').toLowerCase() === 'telegram_pdf'
    || String(sharing.metadata_json?.['mime_type'] || '').toLowerCase() === 'application/pdf');

  useEffect(() => {
    if (!requestedContentId || assigning) return;
    const matchingItem = items.find((item) => (item.content_id || item.id) === requestedContentId);
    if (matchingItem) setAssigning(matchingItem);
  }, [assigning, items, requestedContentId]);

  const closeAssignment = () => {
    setAssigning(null);
    if (requestedContentId) {
      const next = new URLSearchParams(searchParams);
      next.delete('content_id');
      setSearchParams(next, { replace: true });
    }
  };

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedQuery(query.trim()), 220);
    return () => window.clearTimeout(timeout);
  }, [query]);

  const loadContents = useCallback(async (cursor?: string | null) => {
    const sequence = ++loadSequence.current;
    const isMore = Boolean(cursor);
    if (isMore) {
      setLoadingMore(true);
    } else {
      setLoading(true);
      setNextCursor(null);
    }
    setError('');
    try {
      const response = await apiClient.getMyContents(
        status === 'all' ? undefined : status,
        cursor || undefined,
        30,
        {
          q: debouncedQuery || undefined,
          content_type: contentType === 'all' ? undefined : contentType,
          language: language === 'all' ? undefined : language,
          sort,
        },
      );
      if (sequence !== loadSequence.current) return;
      setItems((prev) => (isMore ? [...prev, ...response.items] : response.items));
      setNextCursor(response.next_cursor || null);
      setFacets(response.facets || {});
    } catch (err) {
      if (sequence !== loadSequence.current) return;
      if (err instanceof ApiError) {
        setError(err.message || 'Failed to load library');
      } else {
        setError(t('myContents.failedToLoadLibrary'));
      }
    } finally {
      if (sequence === loadSequence.current) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, [contentType, debouncedQuery, language, sort, status]);

  useEffect(() => {
    void loadContents();
    return () => { loadSequence.current += 1; };
  }, [loadContents, refreshVersion]);

  // Returning from the standalone video page can restore this tab from the
  // browser's back-forward cache. Refresh once in that case so a transcript
  // cached during the watch is reflected by its Library badge immediately.
  useEffect(() => {
    const refreshAfterRestore = (event: PageTransitionEvent) => {
      if (event.persisted) void loadContents();
    };
    window.addEventListener('pageshow', refreshAfterRestore);
    return () => window.removeEventListener('pageshow', refreshAfterRestore);
  }, [loadContents]);


  const handleAddContent = async () => {
    const url = addUrl.trim();
    if (!url) return;
    setAdding(true);
    setAddError('');
    try {
      const resolved = await apiClient.resolveContent(url);
      const contentId = resolved.content_id || resolved.id;
      if (!contentId) throw new Error('No content id returned');
      await apiClient.addUserContent(contentId);
      setAddUrl('');
      setAddOpen(false);
      if (status === 'all') {
        await loadContents();
      } else {
        setStatus('all');
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setAddError(err.message || 'Failed to add content');
      } else {
        setAddError('Failed to add content');
      }
    } finally {
      setAdding(false);
    }
  };

  const openShare = (item: UserContentWithDetails) => {
    setSharing(item);
    setShareStep('choose');
    setSelectedClubId('');
    setShareLanguage((item.language || '').toLowerCase().split('-')[0]);
    const existingLevel = item.metadata_json?.['level'];
    setShareLevel(typeof existingLevel === 'string' && /^[ABC][12]$/.test(existingLevel) ? existingLevel : '');
    setShareIsLearning(typeof existingLevel === 'string' && /^[ABC][12]$/.test(existingLevel));
    setShareError('');
  };

  const openClubShare = async () => {
    setShareStep('club');
    setShareClubsLoading(true);
    setShareError('');
    try {
      const response = await apiClient.getMyClubs();
      setShareClubs(response.clubs);
    } catch (err) {
      setShareError(err instanceof ApiError ? err.message : t('content.clubLoadFailed'));
    } finally {
      setShareClubsLoading(false);
    }
  };

  const confirmClubShare = async () => {
    if (!sharing || !selectedClubId || shareBusy) return;
    setShareBusy(true);
    setShareError('');
    try {
      const result = await apiClient.shareContentToClub(sharing.content_id || sharing.id, selectedClubId);
      setSharing(null);
      setPlannedToast(t(result.already_shared ? 'content.alreadySharedWithClub' : 'content.sharedWithClub', { club: result.club_name }));
      window.setTimeout(() => setPlannedToast(''), 4000);
    } catch (err) {
      setShareError(err instanceof ApiError ? err.message : t('content.shareFailed'));
    } finally {
      setShareBusy(false);
    }
  };

  const shareItem = async (destination: 'link' | 'explore') => {
    if (!sharing || shareBusy) return;
    setShareBusy(true);
    setShareError('');
    try {
      const result = await apiClient.shareLibraryContent(sharing.content_id || sharing.id, {
        destination,
        language: destination === 'explore' && shareLanguage ? shareLanguage : undefined,
        level: destination === 'explore' && shareIsLearning && shareLevel ? shareLevel : undefined,
      });
      if (destination === 'explore') {
        setSharing(null);
        setPlannedToast(t(result.already_in_explore ? 'content.alreadyInExplore' : 'content.sharedToExplore'));
        window.setTimeout(() => setPlannedToast(''), 4000);
        if (!result.already_in_explore) setRefreshVersion((version) => version + 1);
        return;
      }
      const url = `${window.location.origin}${result.path}`;
      const telegramShareUrl = `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(sharing.title || '')}`;
      hapticFeedback('light');
      if (webApp?.openTelegramLink) {
        setSharing(null);
        webApp.openTelegramLink(telegramShareUrl);
      } else {
        const telegramWindow = window.open(telegramShareUrl, '_blank');
        if (telegramWindow) telegramWindow.opener = null;
        setSharing(null);
        if (!telegramWindow) {
          await navigator.clipboard.writeText(url);
          setPlannedToast(t('content.linkCopied'));
          window.setTimeout(() => setPlannedToast(''), 3000);
        }
      }
    } catch (err) {
      setShareError(err instanceof ApiError ? err.message : t('content.shareFailed'));
    } finally {
      setShareBusy(false);
    }
  };

  const openItem = (item: UserContentWithDetails) => {
    const pdfReaderUrl = getInternalPdfReaderUrl(item);
    if (pdfReaderUrl) {
      window.location.assign(pdfReaderUrl);
      return;
    }

    const youtubeWatchUrl = getInternalYouTubeWatchUrl(item);
    if (youtubeWatchUrl) {
      window.location.assign(`${youtubeWatchUrl}&lang=${encodeURIComponent(i18n.language)}`);
      return;
    }

    const url = item.original_url || item.canonical_url;
    if (url) window.open(url, '_blank');
  };

  // Archiving changes only Library visibility. Restore derives its status
  // from the existing progress; neither action deletes learning data.
  const setArchived = async (item: UserContentWithDetails, archived: boolean) => {
    const contentId = item.content_id || item.id;
    if (!contentId || mutationInFlight.current) return;
    mutationInFlight.current = true;
    setUpdatingId(contentId);
    setError('');
    try {
      await apiClient.updateUserContent(contentId, { status: archived ? 'archived' : restoredLibraryStatus(item) });
      setItems((prev) => prev.filter((existing) => (existing.content_id || existing.id) !== contentId));
      setPlannedToast(t(archived ? 'content.archivedNotice' : 'content.restoredNotice'));
      window.setTimeout(() => setPlannedToast(''), 4000);
      // Refetch the current filter and its counts/cursor, not a stale snapshot.
      setRefreshVersion((version) => version + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('myContents.failedToUpdateContent'));
    } finally {
      mutationInFlight.current = false;
      setUpdatingId(null);
    }
  };

  // Counted against the defaults, so landing on the page shows zero active
  // filters rather than one.
  const activeFilterCount = useMemo(() => {
    return [
      status !== 'all',
      contentType !== 'all',
      language !== 'all',
      sort !== 'added',
      Boolean(debouncedQuery),
    ].filter(Boolean).length;
  }, [contentType, debouncedQuery, language, sort, status]);

  const resetFilters = () => {
    setStatus('all');
    setContentType('all');
    setLanguage('all');
    setQuery('');
    setSort('added');
  };

  return (
    <main className="content-library-page">
      <section className="content-library-command">
        {/* Search plus one toggle. Status chips, type chips and sort used to sit
            in three permanent rows above the library, so the content itself
            started below the fold — on a phone the filters outweighed what they
            filtered. They now open on demand and the button carries a count, so
            an active filter is still visible while collapsed. */}
        <div className="content-library-search-row">
          <label className="content-library-search">
            <Search size={16} />
            <input
              type="search"
              aria-label={t('myContents.searchYourLibrary')}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t('myContents.searchYourLibrary')}
            />
          </label>
          <button
            type="button"
            className="content-library-filter-toggle content-library-add-toggle"
            aria-label={t('myContents.addToLibrary')}
            title={t('myContents.addToLibrary')}
            onClick={() => { setAddError(''); setAddOpen(true); }}
          >
            <Plus size={18} aria-hidden="true" />
          </button>
          <button
            type="button"
            className={`content-library-filter-toggle${filtersOpen ? ' is-open' : ''}`}
            onClick={() => setFiltersOpen((open) => !open)}
            aria-expanded={filtersOpen}
            aria-label={t('myContents.filters')}
          >
            <Filter size={16} aria-hidden />
            {activeFilterCount > 0 && (
              <span className="content-library-filter-count">{activeFilterCount}</span>
            )}
          </button>
        </div>

        {filtersOpen && (
          <div className="content-library-filter-panel">
            <div className="content-library-filters" aria-label={t('myContents.libraryStatusFilters')}>
              {STATUS_FILTERS.map((filter) => (
                <button
                  key={filter.key}
                  type="button"
                  className={status === filter.key ? 'is-active' : ''}
                  onClick={() => setStatus(filter.key)}
                >
                  {t(`myContents.status.${filter.label}`)}
                  {filter.key !== 'all' && facets.status?.[filter.key] != null && (
                    <span>{facets.status[filter.key]}</span>
                  )}
                </button>
              ))}
            </div>

            <div className="content-library-filters" aria-label={t('myContents.libraryTypeFilters')}>
              {TYPE_FILTERS.map((filter) => (
                <button
                  key={filter.key}
                  type="button"
                  className={contentType === filter.key ? 'is-active' : ''}
                  onClick={() => setContentType(filter.key)}
                >
                  {t(`myContents.types.${filter.label}`)}
                  {filter.key !== 'all' && facets.content_type?.[filter.key] != null && (
                        <span>{facets.content_type[filter.key]}</span>
                      )}
                </button>
              ))}
            </div>

            <div className="content-library-filter-foot">
              <label className="content-library-sort">
                <span>{t('myContents.languageFilter')}</span>
                <select value={language} onChange={(event) => setLanguage(event.target.value)}>
                  <option value="all">{t('myContents.allLanguages')}</option>
                  {Object.entries(facets.language || {}).sort(([a], [b]) => a.localeCompare(b)).map(([code, count]) => (
                    <option key={code} value={code}>{code === 'unknown' ? t('myContents.unknownLanguage') : t(`learning.languages.${code}`, { defaultValue: code.toUpperCase() })} ({count})</option>
                  ))}
                </select>
              </label>
              <label className="content-library-sort">
                <span>{t('myContents.sort')}</span>
                <select value={sort} onChange={(event) => setSort(event.target.value as SortKey)}>
                  {SORT_OPTIONS.map((option) => (
                    <option key={option.key} value={option.key}>{option.label}</option>
                  ))}
                </select>
              </label>
              {activeFilterCount > 0 && (
                <button className="content-library-clear" type="button" onClick={resetFilters}>{t('myContents.clear')}</button>
              )}
            </div>
          </div>
        )}
      </section>

      {error && <div className="content-library-error">{error}</div>}

      {loading ? (
        <div className="content-library-state">{t('myContents.loadingLibrary')}</div>
      ) : items.length > 0 ? (
        <>
          <section className="content-library-grid" aria-label={t('myContents.libraryItems')}>
            {items.map((item) => (
              <ContentCard
                key={item.user_content_id || item.content_id || item.id}
                item={item}
                onClick={() => openItem(item)}
                onPlan={item.status !== 'archived' ? () => setPlanning(item) : undefined}
                onShare={item.user_content_id && canShareLibraryItem(item) ? () => openShare(item) : undefined}
                onArchive={item.user_content_id && item.status !== 'archived' ? () => setArchiveTarget(item) : undefined}
                onRestore={item.user_content_id && item.status === 'archived' ? () => setArchived(item, false) : undefined}
                updating={updatingId !== null}
              />
            ))}
          </section>
          {nextCursor && (
            <button
              className="content-library-load-more"
              type="button"
              disabled={loadingMore}
              onClick={() => loadContents(nextCursor)}
            >
              {loadingMore ? 'Loading...' : 'Load more'}
            </button>
          )}
        </>
      ) : !error ? (
        <section className="content-library-empty">
          <div className="content-library-empty-icon" aria-hidden="true"><Plus size={22} /></div>
          <h2>{t(status === 'archived' ? 'myContents.archiveEmpty' : 'myContents.noContentHereYet')}</h2>
          <p>{status === 'archived' ? t('myContents.archiveEmptyHint') : activeFilterCount === 0
            ? t('myContents.emptyLibraryGuide')
            : t('myContents.useAddButtonOrClearFilters')}</p>
          {activeFilterCount > 0 && (
            <button type="button" onClick={resetFilters}>{t('myContents.clearFilters')}</button>
          )}
          {activeFilterCount === 0 && (
            <button type="button" onClick={() => navigate('/explore')}>{t('learning.exploreVideos')}</button>
          )}
        </section>
      ) : null}

      {plannedToast ? (
        <p className="content-library-planned-toast" role="status">{plannedToast}</p>
      ) : null}

      <BottomSheet open={!!archiveTarget} onClose={() => setArchiveTarget(null)}
        title={t('content.archiveConfirmTitle')}
        subtitle={archiveTarget?.title || t('content.untitled')}>
        <p className="content-library-sheet-note">{t('content.archiveConfirmMessage')}</p>
        <div className="content-library-sheet-actions">
          <button type="button" className="btn btn-ghost" onClick={() => setArchiveTarget(null)}>{t('common.cancel')}</button>
          <button type="button" className="btn btn-primary" disabled={updatingId !== null}
            onClick={() => { if (archiveTarget) void setArchived(archiveTarget, true); setArchiveTarget(null); }}>
            {t('content.archive')}
          </button>
        </div>
      </BottomSheet>

      <BottomSheet open={!!sharing} onClose={() => !shareBusy && setSharing(null)}
        title={t('content.share')} subtitle={sharing?.title || t('content.untitled')}>
        {shareStep === 'choose' && <>
          <p className="content-library-sheet-note">{t(sharingIsPdf ? 'content.pdfShareNotice' : 'content.videoShareNotice')}</p>
          <div className="content-library-share-options">
            <button type="button" className="plan-content-option" disabled={shareBusy} onClick={() => void shareItem('link')}>
              <span>{t('content.shareLink')}</span><small>{t('content.shareLinkHint')}</small>
            </button>
            <button type="button" className="plan-content-option" disabled={shareBusy} onClick={() => void openClubShare()}>
              <span>{t('content.shareToClub')}</span><small>{t('content.shareToClubHint')}</small>
            </button>
            <button type="button" className="plan-content-option" disabled={shareBusy} onClick={() => setShareStep('explore')}>
              <span>{t('content.shareToExplore')}</span><small>{t('content.shareToExploreHint')}</small>
            </button>
          </div>
        </>}
        {shareStep === 'club' && <>
          <button type="button" className="content-library-share-back" disabled={shareBusy} onClick={() => setShareStep('choose')}>{t('content.backToShareOptions')}</button>
          <p className="content-library-sheet-note">{t('content.clubSharePreview')}</p>
          {shareClubsLoading ? <p className="content-library-state">{t('myContents.loadingLibrary')}</p>
            : shareClubs.length === 0 ? <p className="content-library-state">{t('content.noClubsToShare')}</p>
            : <div className="content-library-share-clubs" role="radiogroup" aria-label={t('content.chooseClub')}>
              {shareClubs.map((club) => <label key={club.club_id} className={selectedClubId === club.club_id ? 'is-selected' : ''}>
                <input type="radio" name="shareClub" value={club.club_id} disabled={!['ready', 'connected'].includes(club.telegram_status)} checked={selectedClubId === club.club_id} onChange={() => setSelectedClubId(club.club_id)} />
                <span>{club.name}{!['ready', 'connected'].includes(club.telegram_status) && <small> · {t('content.clubTelegramUnavailable')}</small>}</span>
              </label>)}
            </div>}
          {selectedClubId && <p className="content-library-sheet-note">{t('content.clubShareConfirm', { club: shareClubs.find((club) => club.club_id === selectedClubId)?.name })}</p>}
          <button type="button" className="btn btn-primary btn-block" disabled={!selectedClubId || shareBusy} onClick={() => void confirmClubShare()}>{shareBusy ? t('content.sharing') : t('content.postToClub')}</button>
        </>}
        {shareStep === 'explore' && <>
          <button type="button" className="content-library-share-back" disabled={shareBusy} onClick={() => setShareStep('choose')}>{t('content.backToShareOptions')}</button>
          <p className="content-library-sheet-note">{t('content.exploreSharePreview')}</p>
          <div className="content-library-share-fields">
            <label>{t('content.contentLanguage')}
              <select value={shareLanguage} onChange={(event) => setShareLanguage(event.target.value)}>
                <option value="">{t('content.unspecified')}</option>
                {shareLanguage && !['en', 'fr', 'fa'].includes(shareLanguage) &&
                  <option value={shareLanguage}>{shareLanguage.toUpperCase()}</option>}
                {['en', 'fr', 'fa'].map((code) => <option key={code} value={code}>{t(`learning.languages.${code}`)}</option>)}
              </select>
            </label>
          </div>
          <label className="content-library-learning-toggle"><input type="checkbox" checked={shareIsLearning} onChange={(event) => setShareIsLearning(event.target.checked)} />{t('content.isLearningContent')}</label>
          {shareIsLearning && <div className="content-library-share-fields"><label>{t('content.learningLevelOptional')}
              <select value={shareLevel} onChange={(event) => setShareLevel(event.target.value)}>
                <option value="">{t('content.unspecified')}</option>
                {['A1', 'A2', 'B1', 'B2', 'C1', 'C2'].map((level) => <option key={level} value={level}>{level}</option>)}
              </select>
            </label>
          </div>}
          <button type="button" className="btn btn-primary btn-block" disabled={shareBusy} onClick={() => void shareItem('explore')}>{shareBusy ? t('content.sharing') : t('content.publishToExplore')}</button>
        </>}
        {shareError && <p className="content-library-error" role="alert">{shareError}</p>}
      </BottomSheet>

      <PlanContentSheet
        open={!!planning}
        contentId={planning?.content_id || planning?.id || null}
        title={planning?.title || t('content.untitled')}
        durationSeconds={planning?.duration_seconds}
        onClose={() => setPlanning(null)}
        onPlanned={(whenLabel) => {
          setPlannedToast(t('content.plannedFor', { when: whenLabel }));
          window.setTimeout(() => setPlannedToast(''), 4000);
        }}
      />

      <AssignContentSheet
        open={!!assigning}
        contentId={assigning?.content_id || assigning?.id || null}
        contentTitle={assigning?.title || t('content.untitled')}
        onClose={closeAssignment}
        onAssigned={(promiseId) => {
          setPlannedToast(`Assigned to #${promiseId}`);
          window.setTimeout(() => setPlannedToast(''), 4000);
          closeAssignment();
        }}
      />

      <BottomSheet
        open={addOpen}
        onClose={() => !adding && setAddOpen(false)}
        title={t('myContents.addToLibrary')}
        subtitle={t('myContents.addToLibraryHint')}
      >
        <form
          className="content-library-add-sheet"
          onSubmit={(event) => {
            event.preventDefault();
            void handleAddContent();
          }}
        >
          <input
            type="url"
            inputMode="url"
            autoFocus
            placeholder={t('myContents.pasteAPdfYoutubeArticleOrPodcastUrl')}
            value={addUrl}
            onChange={(event) => setAddUrl(event.target.value)}
          />
          {addError ? <div className="content-library-error">{addError}</div> : null}
          <button className="btn btn-primary btn-block" type="submit" disabled={adding || !addUrl.trim()}>
            <Plus size={16} />
            <span>{adding ? t('myContents.adding') : t('myContents.add')}</span>
          </button>
        </form>
      </BottomSheet>
    </main>
  );
}
