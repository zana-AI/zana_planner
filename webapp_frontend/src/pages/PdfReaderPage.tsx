import { useEffect, useMemo, useRef, useState, type TouchEvent as ReactTouchEvent } from 'react';
import { ChevronLeft, ChevronRight, Maximize2, Minimize2, ZoomIn, ZoomOut } from 'lucide-react';
import * as pdfjsLib from 'pdfjs-dist';
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';
import { useSearchParams } from 'react-router-dom';
import { apiClient, ApiError } from '../api/client';
import { getDevInitData, useTelegramWebApp } from '../hooks/useTelegramWebApp';
import type { PdfHighlight } from '../types';

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

export function PdfReaderPage() {
  const { initData, isReady, isTelegramMiniApp, expand } = useTelegramWebApp();
  const [params] = useSearchParams();
  const contentId = params.get('content_id') || '';

  const [assetId, setAssetId] = useState('');
  const [pdfUrl, setPdfUrl] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [progressRatio, setProgressRatio] = useState(0);
  const [highlights, setHighlights] = useState<PdfHighlight[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [syncStatus, setSyncStatus] = useState<'idle' | 'pending' | 'saving' | 'saved' | 'error'>('idle');
  const [error, setError] = useState('');
  const [pdfDoc, setPdfDoc] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [scale, setScale] = useState(1);
  const [rendering, setRendering] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const [pageIndex, setPageIndex] = useState(0);
  const [selectedText, setSelectedText] = useState('');
  const [note, setNote] = useState('');
  const [color, setColor] = useState('#ffe066');
  const blobUrlRef = useRef<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const shellRef = useRef<HTMLDivElement | null>(null);
  const resumeRatioRef = useRef(0);
  const pendingScrollFractionRef = useRef<number | null>(null);
  const progressRatioRef = useRef(0);
  const savedRatioRef = useRef(0);
  const contentIdRef = useRef(contentId);
  const canLoadApiRef = useRef(false);
  const autoSaveTimeoutRef = useRef<number | null>(null);
  const isSavingProgressRef = useRef(false);
  const queuedProgressRef = useRef<number | null>(null);
  const pinchStartDistanceRef = useRef<number | null>(null);
  const pinchStartScaleRef = useRef(1);

  const canOpen = Boolean(contentId);
  const authData = initData || getDevInitData();
  const hasBrowserToken = typeof window !== 'undefined' && !!localStorage.getItem('telegram_auth_token');
  const canLoadApi = isReady && (!!authData || hasBrowserToken);
  contentIdRef.current = contentId;
  canLoadApiRef.current = canLoadApi;

  useEffect(() => {
    if (authData) {
      apiClient.setInitData(authData);
    }
  }, [authData]);

  const clampRatio = (ratio: number) => Math.max(0, Math.min(1, ratio));

  const syncProgress = async (nextRatio = progressRatioRef.current) => {
    const activeContentId = contentIdRef.current;
    if (!activeContentId || !canLoadApiRef.current) return;
    const boundedRatio = clampRatio(nextRatio);
    if (Math.abs(boundedRatio - savedRatioRef.current) < 0.002) {
      setSyncStatus('saved');
      return;
    }

    if (isSavingProgressRef.current) {
      queuedProgressRef.current = boundedRatio;
      setSyncStatus('pending');
      return;
    }

    isSavingProgressRef.current = true;
    setSaving(true);
    setSyncStatus('saving');
    setError('');
    try {
      await apiClient.postConsumeEvent({
        content_id: activeContentId,
        start_position: savedRatioRef.current,
        end_position: boundedRatio,
        position_unit: 'ratio',
        client: 'web_pdf_reader_auto',
      });
      savedRatioRef.current = boundedRatio;
      setSyncStatus('saved');
    } catch (err) {
      setSyncStatus('error');
      if (err instanceof ApiError) {
        setError(err.message || 'Failed to sync reading progress');
      } else {
        setError('Failed to sync reading progress');
      }
    } finally {
      isSavingProgressRef.current = false;
      setSaving(false);
    }

    const queuedRatio = queuedProgressRef.current;
    queuedProgressRef.current = null;
    if (queuedRatio != null && Math.abs(queuedRatio - savedRatioRef.current) >= 0.002) {
      window.setTimeout(() => {
        void syncProgress(queuedRatio);
      }, 150);
    }
  };

  const scheduleProgressSync = (nextRatio: number) => {
    if (!contentId || !canLoadApi || loading) return;
    const boundedRatio = clampRatio(nextRatio);
    if (Math.abs(boundedRatio - savedRatioRef.current) < 0.002) {
      setSyncStatus('saved');
      return;
    }
    setSyncStatus('pending');
    if (autoSaveTimeoutRef.current != null) {
      window.clearTimeout(autoSaveTimeoutRef.current);
    }
    autoSaveTimeoutRef.current = window.setTimeout(() => {
      autoSaveTimeoutRef.current = null;
      void syncProgress(boundedRatio);
    }, 1200);
  };

  const updateProgressFromReader = (nextPageNumber = pageNumber) => {
    if (!pageCount) return;
    const shell = shellRef.current;
    const maxScroll = shell ? Math.max(0, shell.scrollHeight - shell.clientHeight) : 0;
    const pageScrollRatio = maxScroll > 0 && shell ? shell.scrollTop / maxScroll : 0;
    const nextRatio = pageCount > 1
      ? ((nextPageNumber - 1) + pageScrollRatio) / pageCount
      : pageScrollRatio;
    setProgressRatio(clampRatio(nextRatio));
  };

  const getTouchDistance = (touches: ReactTouchEvent<HTMLDivElement>['touches']) => {
    if (touches.length < 2) return 0;
    const [a, b] = [touches[0], touches[1]];
    return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
  };

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
      const boundedRatio = clampRatio(ratio);
      resumeRatioRef.current = boundedRatio;
      progressRatioRef.current = boundedRatio;
      savedRatioRef.current = boundedRatio;
      setProgressRatio(boundedRatio);
      setSyncStatus('saved');

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
    const flushProgress = () => {
      if (autoSaveTimeoutRef.current != null) {
        window.clearTimeout(autoSaveTimeoutRef.current);
        autoSaveTimeoutRef.current = null;
      }
      if (Math.abs(progressRatioRef.current - savedRatioRef.current) >= 0.002) {
        void syncProgress(progressRatioRef.current);
      }
    };
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        flushProgress();
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('pagehide', flushProgress);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('pagehide', flushProgress);
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
      }
      if (autoSaveTimeoutRef.current != null) {
        window.clearTimeout(autoSaveTimeoutRef.current);
      }
      if (Math.abs(progressRatioRef.current - savedRatioRef.current) >= 0.002) {
        void syncProgress(progressRatioRef.current);
      }
    };
  }, []);

  useEffect(() => {
    progressRatioRef.current = progressRatio;
    if (!loading && pageCount > 0) {
      scheduleProgressSync(progressRatio);
    }
  }, [progressRatio, loading, pageCount]);

  useEffect(() => {
    const onFullscreenChange = () => {
      if (!document.fullscreenElement) {
        setIsFullscreen(false);
      }
    };
    document.addEventListener('fullscreenchange', onFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let loadedDoc: pdfjsLib.PDFDocumentProxy | null = null;
    if (!pdfUrl) {
      setPdfDoc(null);
      setPageCount(0);
      setPageNumber(1);
      return;
    }

    setRendering(true);
    pdfjsLib.getDocument(pdfUrl).promise
      .then((doc) => {
        if (cancelled) {
          doc.destroy();
          return;
        }
        loadedDoc = doc;
        const scaledProgress = resumeRatioRef.current * doc.numPages;
        const initialPageIndex = doc.numPages > 1
          ? Math.min(doc.numPages - 1, Math.floor(scaledProgress))
          : 0;
        const initialScrollFraction = resumeRatioRef.current >= 0.999
          ? 1
          : scaledProgress - initialPageIndex;
        pendingScrollFractionRef.current = clampRatio(initialScrollFraction);
        setPdfDoc(doc);
        setPageCount(doc.numPages);
        setPageNumber(initialPageIndex + 1);
        setPageIndex(initialPageIndex);
      })
      .catch(() => {
        if (!cancelled) {
          setError('Failed to render PDF');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setRendering(false);
        }
      });

    return () => {
      cancelled = true;
      loadedDoc?.destroy();
    };
  }, [pdfUrl]);

  useEffect(() => {
    let cancelled = false;
    let renderTask: pdfjsLib.RenderTask | null = null;

    async function renderPage() {
      if (!pdfDoc || !canvasRef.current) return;
      setRendering(true);
      try {
        const page = await pdfDoc.getPage(pageNumber);
        if (cancelled) return;
        const viewport = page.getViewport({ scale });
        const canvas = canvasRef.current;
        const context = canvas.getContext('2d');
        if (!context) return;

        const outputScale = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = Math.floor(viewport.width * outputScale);
        canvas.height = Math.floor(viewport.height * outputScale);
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;

        context.setTransform(outputScale, 0, 0, outputScale, 0, 0);
        context.clearRect(0, 0, viewport.width, viewport.height);
        renderTask = page.render({ canvas, canvasContext: context, viewport });
        await renderTask.promise;
        const pendingScrollFraction = pendingScrollFractionRef.current;
        if (!cancelled && pendingScrollFraction != null && shellRef.current) {
          pendingScrollFractionRef.current = null;
          window.requestAnimationFrame(() => {
            const shell = shellRef.current;
            if (!shell) return;
            const maxScroll = Math.max(0, shell.scrollHeight - shell.clientHeight);
            shell.scrollTop = maxScroll * pendingScrollFraction;
            updateProgressFromReader(pageNumber);
          });
        }
      } catch (err) {
        if (!cancelled && !(err instanceof Error && err.name === 'RenderingCancelledException')) {
          setError('Failed to render PDF page');
        }
      } finally {
        if (!cancelled) {
          setRendering(false);
        }
      }
    }

    renderPage();
    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [pdfDoc, pageNumber, scale]);

  const progressPct = useMemo(() => Math.round(progressRatio * 100), [progressRatio]);
  const expiresLabel = useMemo(() => {
    if (!expiresAt) return '';
    const d = new Date(expiresAt);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleTimeString();
  }, [expiresAt]);
  const syncLabel = useMemo(() => {
    if (saving || syncStatus === 'saving') return 'Syncing...';
    if (syncStatus === 'pending') return 'Sync queued';
    if (syncStatus === 'error') return 'Sync failed';
    if (syncStatus === 'saved') return `Synced at ${progressPct}%`;
    return 'Tracking automatically';
  }, [progressPct, saving, syncStatus]);

  const toggleFullscreen = async () => {
    const nextFullscreen = !isFullscreen;
    setIsFullscreen(nextFullscreen);
    if (nextFullscreen) {
      expand();
    }
    try {
      if (nextFullscreen && document.documentElement.requestFullscreen) {
        await document.documentElement.requestFullscreen();
      } else if (!nextFullscreen && document.fullscreenElement) {
        await document.exitFullscreen();
      }
    } catch {
      // Telegram iOS may reject the Fullscreen API; the fixed CSS reader still works.
    }
  };

  const goToPage = (nextPage: number) => {
    if (!pageCount) return;
    const bounded = Math.min(Math.max(nextPage, 1), pageCount);
    if (shellRef.current) {
      shellRef.current.scrollTop = 0;
    }
    pendingScrollFractionRef.current = 0;
    setPageNumber(bounded);
    setPageIndex(bounded - 1);
    setProgressRatio(clampRatio((bounded - 1) / pageCount));
  };

  const zoomBy = (delta: number) => {
    setScale((current) => Math.min(2.5, Math.max(0.65, Number((current + delta).toFixed(2)))));
  };

  const handleReaderScroll = () => {
    updateProgressFromReader();
  };

  const handleTouchStart = (event: ReactTouchEvent<HTMLDivElement>) => {
    if (event.touches.length === 2) {
      pinchStartDistanceRef.current = getTouchDistance(event.touches);
      pinchStartScaleRef.current = scale;
    }
  };

  const handleTouchMove = (event: ReactTouchEvent<HTMLDivElement>) => {
    if (event.touches.length !== 2 || !pinchStartDistanceRef.current) return;
    event.preventDefault();
    const nextDistance = getTouchDistance(event.touches);
    if (!nextDistance) return;
    const nextScale = pinchStartScaleRef.current * (nextDistance / pinchStartDistanceRef.current);
    setScale(Math.min(3, Math.max(0.55, Number(nextScale.toFixed(2)))));
  };

  const handleTouchEnd = (event: ReactTouchEvent<HTMLDivElement>) => {
    if (event.touches.length < 2) {
      pinchStartDistanceRef.current = null;
      pinchStartScaleRef.current = scale;
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
    <div className={`pdf-reader-page${isFullscreen ? ' pdf-reader-page--fullscreen' : ''}`}>
      <section className="pdf-reader-viewer">
        <div className="pdf-reader-toolbar">
          <button
            className="pdf-reader-icon-btn"
            onClick={() => goToPage(pageNumber - 1)}
            disabled={!pageCount || pageNumber <= 1}
            title="Previous page"
            type="button"
          >
            <ChevronLeft size={18} />
          </button>
          <div className="pdf-reader-page-count">
            {pageCount ? `${pageNumber} / ${pageCount}` : '0 / 0'}
          </div>
          <button
            className="pdf-reader-icon-btn"
            onClick={() => goToPage(pageNumber + 1)}
            disabled={!pageCount || pageNumber >= pageCount}
            title="Next page"
            type="button"
          >
            <ChevronRight size={18} />
          </button>
          <div className="pdf-reader-toolbar-spacer" />
          <button
            className="pdf-reader-icon-btn"
            onClick={() => zoomBy(-0.15)}
            disabled={scale <= 0.65}
            title="Zoom out"
            type="button"
          >
            <ZoomOut size={18} />
          </button>
          <div className="pdf-reader-zoom">{Math.round(scale * 100)}%</div>
          <button
            className="pdf-reader-icon-btn"
            onClick={() => zoomBy(0.15)}
            disabled={scale >= 3}
            title="Zoom in"
            type="button"
          >
            <ZoomIn size={18} />
          </button>
          <button
            className="pdf-reader-icon-btn"
            onClick={toggleFullscreen}
            title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen reader'}
            type="button"
          >
            {isFullscreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
          </button>
        </div>
        {loading ? (
          <div style={{ padding: 16, color: 'rgba(255,255,255,0.8)' }}>Loading PDF…</div>
        ) : pdfUrl ? (
          <div
            ref={shellRef}
            className="pdf-reader-canvas-shell"
            onScroll={handleReaderScroll}
            onTouchStart={handleTouchStart}
            onTouchMove={handleTouchMove}
            onTouchEnd={handleTouchEnd}
            onTouchCancel={handleTouchEnd}
          >
            <canvas ref={canvasRef} className="pdf-reader-canvas" />
            {rendering && <div className="pdf-reader-rendering">Rendering...</div>}
          </div>
        ) : (
          <div style={{ padding: 16, color: '#ff6b6b' }}>PDF URL unavailable.</div>
        )}
      </section>

      <aside className="pdf-reader-tools">
        <h2 style={{ margin: 0, fontSize: 16 }}>PDF Sync</h2>
        {expiresLabel && <p style={{ margin: 0, color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>URL expires at {expiresLabel}</p>}
        {error && <p style={{ margin: 0, color: '#ff6b6b', fontSize: 13 }}>{error}</p>}

        <div className="pdf-reader-progress-card" aria-live="polite">
          <div className="pdf-reader-progress-row">
            <span>Reading progress</span>
            <strong>{progressPct}%</strong>
          </div>
          <div className="pdf-reader-progress-track">
            <div className="pdf-reader-progress-fill" style={{ width: `${progressPct}%` }} />
          </div>
          <div className={`pdf-reader-sync-status pdf-reader-sync-status--${syncStatus}`}>
            {syncLabel}
          </div>
          <div className="pdf-reader-sync-note">
            Xaana saves progress automatically as you read.
          </div>
        </div>

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
