import { useCallback, useEffect, useMemo, useState } from 'react';
import { Filter, Plus, Search } from 'lucide-react';
import { apiClient, ApiError } from '../api/client';
import { ContentCard } from '../components/ContentCard';
import type { MyContentsFacets, UserContentWithDetails } from '../types';

type StatusFilter = 'all' | 'in_progress' | 'saved' | 'completed';
type TypeFilter = 'all' | 'pdf' | 'video' | 'audio' | 'text';
type SortKey = 'recent' | 'added' | 'title' | 'progress';

const STATUS_FILTERS: { key: StatusFilter; label: string }[] = [
  { key: 'in_progress', label: 'Continue' },
  { key: 'all', label: 'All' },
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

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: 'recent', label: 'Recently read' },
  { key: 'added', label: 'Recently added' },
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
  const [status, setStatus] = useState<StatusFilter>('in_progress');
  const [contentType, setContentType] = useState<TypeFilter>('all');
  const [sort, setSort] = useState<SortKey>('recent');
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

  const activeFilterCount = useMemo(() => {
    return [status !== 'in_progress', contentType !== 'all', Boolean(debouncedQuery)].filter(Boolean).length;
  }, [contentType, debouncedQuery, status]);

  const resetFilters = () => {
    setStatus('in_progress');
    setContentType('all');
    setQuery('');
    setSort('recent');
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
          <label className="content-library-sort">
            <span>Sort</span>
            <select value={sort} onChange={(event) => setSort(event.target.value as SortKey)}>
              {SORT_OPTIONS.map((option) => (
                <option key={option.key} value={option.key}>{option.label}</option>
              ))}
            </select>
          </label>
        </div>

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

        <div className="content-library-type-row">
          <Filter size={15} />
          <div className="content-library-type-chips">
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
          {activeFilterCount > 0 && (
            <button className="content-library-clear" type="button" onClick={resetFilters}>
              Clear
            </button>
          )}
        </div>
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
