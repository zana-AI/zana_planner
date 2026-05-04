import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiClient, ApiError } from '../api/client';
import { getDevInitData, useTelegramWebApp } from '../hooks/useTelegramWebApp';
import type { PdfHighlight } from '../types';

export function PdfReaderPage() {
  const { initData, isReady, isTelegramMiniApp } = useTelegramWebApp();
  const [params] = useSearchParams();
  const contentId = params.get('content_id') || '';

  const [assetId, setAssetId] = useState('');
  const [pdfUrl, setPdfUrl] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [progressRatio, setProgressRatio] = useState(0);
  const [savedRatio, setSavedRatio] = useState(0);
  const [highlights, setHighlights] = useState<PdfHighlight[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const [pageIndex, setPageIndex] = useState(0);
  const [selectedText, setSelectedText] = useState('');
  const [note, setNote] = useState('');
  const [color, setColor] = useState('#ffe066');
  const blobUrlRef = useRef<string | null>(null);

  const canOpen = Boolean(contentId);
  const authData = initData || getDevInitData();
  const hasBrowserToken = typeof window !== 'undefined' && !!localStorage.getItem('telegram_auth_token');
  const canLoadApi = isReady && (!!authData || hasBrowserToken);

  useEffect(() => {
    if (authData) {
      apiClient.setInitData(authData);
    }
  }, [authData]);

  const load = async () => {
    if (!canOpen || !canLoadApi) return;
    setLoading(true);
    setError('');
    try {
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
      const open = await apiClient.getPdfOpen(contentId);
      setAssetId(open.asset_id);
      if (open.pdf_url.startsWith('/api/')) {
        const blob = await apiClient.fetchPdfBlob(open.pdf_url);
        const objectUrl = URL.createObjectURL(blob);
        blobUrlRef.current = objectUrl;
        setPdfUrl(objectUrl);
      } else {
        setPdfUrl(open.pdf_url);
      }
      setExpiresAt(open.expires_at);
      const ratio = Number(open.last_position ?? open.progress_ratio ?? 0);
      setProgressRatio(Math.max(0, Math.min(1, ratio)));
      setSavedRatio(Math.max(0, Math.min(1, ratio)));

      const h = await apiClient.getPdfHighlights(contentId, open.asset_id);
      setHighlights(h.items || []);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message || 'Failed to open PDF');
      } else {
        setError('Failed to open PDF');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isReady && isTelegramMiniApp && !authData && !hasBrowserToken) {
      setLoading(false);
      setError('Telegram did not provide authentication data. Please reopen this from the bot button.');
      return;
    }
    load();
  }, [contentId, canLoadApi, isReady, isTelegramMiniApp, authData, hasBrowserToken]);

  useEffect(() => {
    return () => {
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
      }
    };
  }, []);

  const progressPct = useMemo(() => Math.round(progressRatio * 100), [progressRatio]);
  const expiresLabel = useMemo(() => {
    if (!expiresAt) return '';
    const d = new Date(expiresAt);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleTimeString();
  }, [expiresAt]);

  const saveProgress = async () => {
    if (!contentId || saving) return;
    setSaving(true);
    setError('');
    try {
      await apiClient.postConsumeEvent({
        content_id: contentId,
        start_position: savedRatio,
        end_position: progressRatio,
        position_unit: 'ratio',
        client: 'web_pdf_reader',
      });
      setSavedRatio(progressRatio);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message || 'Failed to save progress');
      } else {
        setError('Failed to save progress');
      }
    } finally {
      setSaving(false);
    }
  };

  const createHighlight = async () => {
    if (!contentId || !assetId) return;
    setError('');
    try {
      await apiClient.createPdfHighlight(contentId, {
        asset_id: assetId,
        page_index: Math.max(0, pageIndex),
        rects: [{ x: 0, y: 0, width: 1, height: 0.05 }],
        selected_text: selectedText || undefined,
        note: note || undefined,
        color,
      });
      setSelectedText('');
      setNote('');
      const h = await apiClient.getPdfHighlights(contentId, assetId);
      setHighlights(h.items || []);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message || 'Failed to create highlight');
      } else {
        setError('Failed to create highlight');
      }
    }
  };

  const deleteHighlight = async (highlightId: string) => {
    if (!contentId) return;
    setError('');
    try {
      await apiClient.deletePdfHighlight(contentId, highlightId);
      setHighlights((prev) => prev.filter((h) => h.id !== highlightId));
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message || 'Failed to delete highlight');
      } else {
        setError('Failed to delete highlight');
      }
    }
  };

  if (!canOpen) {
    return <div style={{ padding: 16, color: '#ff6b6b' }}>Missing content_id query param.</div>;
  }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '1fr minmax(300px, 360px)',
        gap: 16,
        padding: 16,
        minHeight: 'calc(100vh - 72px)',
      }}
    >
      <section
        style={{
          border: '1px solid rgba(255,255,255,0.16)',
          borderRadius: 12,
          background: 'rgba(0,0,0,0.25)',
          overflow: 'hidden',
        }}
      >
        {loading ? (
          <div style={{ padding: 16, color: 'rgba(255,255,255,0.8)' }}>Loading PDF…</div>
        ) : pdfUrl ? (
          <iframe
            title="PDF Reader"
            src={pdfUrl}
            style={{ width: '100%', height: 'calc(100vh - 120px)', border: 'none', background: '#1f1f1f' }}
          />
        ) : (
          <div style={{ padding: 16, color: '#ff6b6b' }}>PDF URL unavailable.</div>
        )}
      </section>

      <aside
        style={{
          border: '1px solid rgba(255,255,255,0.16)',
          borderRadius: 12,
          background: 'rgba(255,255,255,0.06)',
          padding: 12,
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        <h2 style={{ margin: 0, fontSize: 16 }}>PDF Sync</h2>
        {expiresLabel && <p style={{ margin: 0, color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>URL expires at {expiresLabel}</p>}
        {error && <p style={{ margin: 0, color: '#ff6b6b', fontSize: 13 }}>{error}</p>}

        <label style={{ fontSize: 13 }}>
          Progress: {progressPct}%
          <input
            type="range"
            min={0}
            max={100}
            step={1}
            value={progressPct}
            onChange={(e) => setProgressRatio(Number(e.target.value) / 100)}
            style={{ width: '100%' }}
          />
        </label>
        <button onClick={saveProgress} disabled={saving} style={{ padding: '8px 10px' }}>
          {saving ? 'Saving…' : 'Save Progress'}
        </button>

        <hr style={{ borderColor: 'rgba(255,255,255,0.12)', width: '100%' }} />

        <h3 style={{ margin: 0, fontSize: 14 }}>Add Highlight</h3>
        <label style={{ fontSize: 12 }}>
          Page index
          <input
            type="number"
            min={0}
            value={pageIndex}
            onChange={(e) => setPageIndex(Number(e.target.value || 0))}
            style={{ width: '100%', padding: 6 }}
          />
        </label>
        <label style={{ fontSize: 12 }}>
          Selected text
          <textarea value={selectedText} onChange={(e) => setSelectedText(e.target.value)} rows={3} style={{ width: '100%' }} />
        </label>
        <label style={{ fontSize: 12 }}>
          Note
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} style={{ width: '100%' }} />
        </label>
        <label style={{ fontSize: 12 }}>
          Color
          <input type="color" value={color} onChange={(e) => setColor(e.target.value)} style={{ width: '100%' }} />
        </label>
        <button onClick={createHighlight} style={{ padding: '8px 10px' }}>
          Save Highlight
        </button>

        <hr style={{ borderColor: 'rgba(255,255,255,0.12)', width: '100%' }} />
        <h3 style={{ margin: 0, fontSize: 14 }}>Highlights ({highlights.length})</h3>
        <div style={{ overflowY: 'auto', maxHeight: '35vh', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {highlights.map((h) => (
            <div key={h.id} style={{ border: '1px solid rgba(255,255,255,0.12)', borderRadius: 8, padding: 8 }}>
              <div style={{ fontSize: 12, opacity: 0.85 }}>Page {h.page_index}</div>
              {h.selected_text && <div style={{ fontSize: 12, marginTop: 4 }}>{h.selected_text}</div>}
              {h.note && <div style={{ fontSize: 12, marginTop: 4, color: 'rgba(255,255,255,0.75)' }}>{h.note}</div>}
              <button onClick={() => deleteHighlight(h.id)} style={{ marginTop: 6, fontSize: 12 }}>
                Delete
              </button>
            </div>
          ))}
          {highlights.length === 0 && <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.65)' }}>No highlights yet.</div>}
        </div>
      </aside>
    </div>
  );
}
