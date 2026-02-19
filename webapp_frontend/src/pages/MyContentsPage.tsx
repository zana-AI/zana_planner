import { useState, useEffect, useCallback } from 'react';
import { apiClient, ApiError } from '../api/client';
import { ContentCard } from '../components/ContentCard';
import type { UserContentWithDetails, MyContentsResponse } from '../types';

type StatusFilter = 'in_progress' | 'saved' | 'completed' | '';

const SECTION_STATUSES: { key: StatusFilter; label: string }[] = [
  { key: 'in_progress', label: 'Continue' },
  { key: 'saved', label: 'Saved' },
  { key: 'completed', label: 'Completed' },
];

export function MyContentsPage() {
  const [addUrl, setAddUrl] = useState('');
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState('');
  const [sections, setSections] = useState<Record<StatusFilter, UserContentWithDetails[]>>({
    in_progress: [],
    saved: [],
    completed: [],
    '': [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [inProgressRes, savedRes, completedRes] = await Promise.all([
        apiClient.getMyContents('in_progress'),
        apiClient.getMyContents('saved'),
        apiClient.getMyContents('completed'),
      ]);
      setSections({
        in_progress: inProgressRes.items,
        saved: savedRes.items,
        completed: completedRes.items,
        '': [],
      });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message || 'Failed to load contents');
      } else {
        setError('Failed to load contents');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

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
      await fetchAll();
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

  return (
    <div style={{ padding: '1rem', maxWidth: 1200, margin: '0 auto' }}>
      <h1 style={{ margin: '0 0 1rem', fontSize: '1.5rem', color: '#fff' }}>My Contents</h1>

      <div style={{ marginBottom: '1.5rem', display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          type="url"
          placeholder="Paste URL (YouTube, article, podcast...)"
          value={addUrl}
          onChange={(e) => setAddUrl(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAddContent()}
          style={{
            flex: 1,
            minWidth: 200,
            padding: '10px 12px',
            borderRadius: 8,
            border: '1px solid rgba(255,255,255,0.2)',
            background: 'rgba(255,255,255,0.08)',
            color: '#fff',
            fontSize: 14,
          }}
        />
        <button
          onClick={handleAddContent}
          disabled={adding || !addUrl.trim()}
          style={{
            padding: '10px 20px',
            borderRadius: 8,
            border: 'none',
            background: 'var(--tg-theme-button-color, #2481cc)',
            color: 'var(--tg-theme-button-text-color, #fff)',
            fontWeight: 600,
            cursor: adding ? 'wait' : 'pointer',
          }}
        >
          {adding ? 'Adding…' : 'Add'}
        </button>
      </div>
      {addError && (
        <p style={{ color: '#ff6b6b', fontSize: 14, margin: '0 0 1rem' }}>{addError}</p>
      )}

      {loading && (
        <p style={{ color: 'rgba(255,255,255,0.7)' }}>Loading…</p>
      )}
      {error && !loading && (
        <p style={{ color: '#ff6b6b' }}>{error}</p>
      )}
      {!loading && !error && (
        <>
          {SECTION_STATUSES.map(({ key, label }) => {
            const items = sections[key] ?? [];
            if (items.length === 0) return null;
            return (
              <section key={key} style={{ marginBottom: '2rem' }}>
                <h2 style={{ margin: '0 0 0.75rem', fontSize: '1.1rem', color: 'rgba(255,255,255,0.9)' }}>
                  {label}
                </h2>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
                    gap: 16,
                  }}
                >
                  {items.map((item) => (
                    <ContentCard
                      key={item.user_content_id || item.content_id || item.id}
                      item={item}
                      onClick={() => {
                        const url = item.original_url || item.canonical_url;
                        if (url) window.open(url, '_blank');
                      }}
                    />
                  ))}
                </div>
              </section>
            );
          })}
          {SECTION_STATUSES.every(({ key }) => (sections[key] ?? []).length === 0) && (
            <p style={{ color: 'rgba(255,255,255,0.6)' }}>
              No content yet. Paste a URL above to add a video, article, or podcast.
            </p>
          )}
        </>
      )}
    </div>
  );
}
