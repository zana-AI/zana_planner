import { useCallback, useEffect, useMemo, useState } from 'react';
import { Filter, Plus, Search } from 'lucide-react';
import { apiClient, ApiError } from '../api/client';
import { ContentCard } from '../components/ContentCard';
import type { MyContentsFacets, UserContentWithDetails } from '../types';

type StatusFilter = 'all' | 'in_progress' | 'saved' | 'completed';
type TypeFilter = 'all' | 'pdf' | 'video' | 'audio' | 'text';
type SortKey = 'recent' | 'added' | 'title' | 'progress';

// "All" leads because it is the default — the selected chip should be the first
// one, not buried second.
const STATUS_FILTERS: { key: StatusFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'in_progress', label: 'Continue' },
  { key: 'saved', label: 'Saved' },
  { key: 'completed', label: 'Completed' },
];

const TYPE_FILTERS: { key: TypeFilter; label: string }[] = [
  { key: 'all', label: 'All types' },
  { key: 'pdf', label: 'PDFs' },
  { key: 'video', label: 'Videos' },
  { key: 'audio', label: 'Audio' },
  { key: 'text', label: 'Articles' },
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
  return `/youtube-watch?video_id=${encodeURIComponent(videoId)}`;
}

function getInternalPdfReaderUrl(item: UserContentWithDetails): string | null {
  const provider = (item.provider || '').toLowerCase();
  const mime = String(item.metadata_json?.['mime_type'] || '').toLowerCase();
  const isPdf = provider === 'telegram_pdf' || mime === 'application/pdf';
  if (!isPdf) return null;
  const contentId = item.content_id || item.id;
  if (!contentId) return null;
  return `/pdf-reader?content_id=${encodeURIComponent(contentId)}`;
}

export function MyContentsPage() {
  const [addUrl, setAddUrl] = useState('');
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState('');
  const [items, setItems] = useState<UserContentWithDetails[]>([]);
  const [facets, setFacets] = useState<MyContentsFacets>({});
  // Opens on the whole library, not on "Continue". As a sub-page this landed on
  // what you were mid-way through; as a primary tab it has to show everything —
  // a filter that hides what you just saved reads as the save having failed.
  const [status, setStatus] = useState<StatusFilter>('all');
  const [contentType, setContentType] = useState<TypeFilter>('all');
  const [sort, setSort] = useState<SortKey>('added');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedQuery(query.trim()), 220);
    return () => window.clearTimeout(timeout);
  }, [query]);

  const loadContents = useCallback(async (cursor?: string | null) => {
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
          sort,
        },
      );
      setItems((prev) => (isMore ? [...prev, ...response.items] : response.items));
      setNextCursor(response.next_cursor || null);
      setFacets(response.facets || {});
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message || 'Failed to load library');
      } else {
        setError('Failed to load library');
      }
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [contentType, debouncedQuery, sort, status]);

  useEffect(() => {
    void loadContents();
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
      setStatus('saved');
      if (status === 'saved') {
        await loadContents();
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

  const openItem = (item: UserContentWithDetails) => {
    const pdfReaderUrl = getInternalPdfReaderUrl(item);
    if (pdfReaderUrl) {
      window.location.assign(pdfReaderUrl);
      return;
    }

    const youtubeWatchUrl = getInternalYouTubeWatchUrl(item);
    if (youtubeWatchUrl) {
      window.location.assign(youtubeWatchUrl);
      return;
    }

    const url = item.original_url || item.canonical_url;
    if (url) window.open(url, '_blank');
  };

  const updateStatus = async (item: UserContentWithDetails, nextStatus: 'saved' | 'in_progress' | 'completed') => {
    const contentId = item.content_id || item.id;
    if (!contentId) return;
    setError('');
    setItems((prev) => prev.map((existing) => (
      (existing.content_id || existing.id) === contentId ? { ...existing, status: nextStatus } : existing
    )));
    try {
      await apiClient.updateUserContent(contentId, { status: nextStatus });
      await loadContents();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message || 'Failed to update content');
      } else {
        setError('Failed to update content');
      }
      await loadContents();
    }
  };

  // Counted against the defaults, so landing on the page shows zero active
  // filters rather than one.
  const activeFilterCount = useMemo(() => {
    return [
      status !== 'all',
      contentType !== 'all',
      sort !== 'added',
      Boolean(debouncedQuery),
    ].filter(Boolean).length;
  }, [contentType, debouncedQuery, sort, status]);

  const resetFilters = () => {
    setStatus('all');
    setContentType('all');
    setQuery('');
    setSort('added');
  };

  return (
    <main className="content-library-page">
      <section className="content-library-command">
        <div className="content-library-add">
          <input
            type="url"
            placeholder="Paste a PDF, YouTube, article, or podcast URL"
            value={addUrl}
            onChange={(e) => setAddUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAddContent()}
          />
          <button type="button" onClick={handleAddContent} disabled={adding || !addUrl.trim()}>
            <Plus size={16} />
            <span>{adding ? 'Adding' : 'Add'}</span>
          </button>
        </div>
        {addError && <div className="content-library-error">{addError}</div>}

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
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search your library"
            />
          </label>
          <button
            type="button"
            className={`content-library-filter-toggle${filtersOpen ? ' is-open' : ''}`}
            onClick={() => setFiltersOpen((open) => !open)}
            aria-expanded={filtersOpen}
          >
            <Filter size={15} aria-hidden />
            <span>Filters</span>
            {activeFilterCount > 0 && (
              <span className="content-library-filter-count">{activeFilterCount}</span>
            )}
          </button>
        </div>

        {filtersOpen && (
          <div className="content-library-filter-panel">
            <div className="content-library-filters" aria-label="Library status filters">
              {STATUS_FILTERS.map((filter) => (
                <button
                  key={filter.key}
                  type="button"
                  className={status === filter.key ? 'is-active' : ''}
                  onClick={() => setStatus(filter.key)}
                >
                  {filter.label}
                  {filter.key !== 'all' && facets.status?.[filter.key] != null && (
                    <span>{facets.status[filter.key]}</span>
                  )}
                </button>
              ))}
            </div>

            <div className="content-library-filters" aria-label="Library type filters">
              {TYPE_FILTERS.map((filter) => (
                <button
                  key={filter.key}
                  type="button"
                  className={contentType === filter.key ? 'is-active' : ''}
                  onClick={() => setContentType(filter.key)}
                >
                  {filter.label}
                  {filter.key !== 'all' && facets.content_type?.[filter.key] != null && (
                    <span>{facets.content_type[filter.key]}</span>
                  )}
                </button>
              ))}
            </div>

            <div className="content-library-filter-foot">
              <label className="content-library-sort">
                <span>Sort</span>
                <select value={sort} onChange={(event) => setSort(event.target.value as SortKey)}>
                  {SORT_OPTIONS.map((option) => (
                    <option key={option.key} value={option.key}>{option.label}</option>
                  ))}
                </select>
              </label>
              {activeFilterCount > 0 && (
                <button className="content-library-clear" type="button" onClick={resetFilters}>
                  Clear
                </button>
              )}
            </div>
          </div>
        )}
      </section>

      {error && <div className="content-library-error">{error}</div>}

      {loading ? (
        <div className="content-library-state">Loading library...</div>
      ) : items.length > 0 ? (
        <>
          <section className="content-library-grid" aria-label="Library items">
            {items.map((item) => (
              <ContentCard
                key={item.user_content_id || item.content_id || item.id}
                item={item}
                onClick={() => openItem(item)}
                onStatusChange={(nextStatus) => updateStatus(item, nextStatus)}
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
      ) : (
        <section className="content-library-empty">
          <h2>No content here yet</h2>
          <p>Paste a link above, or clear filters to broaden the library.</p>
          {activeFilterCount > 0 && (
            <button type="button" onClick={resetFilters}>Clear filters</button>
          )}
        </section>
      )}
    </main>
  );
}
