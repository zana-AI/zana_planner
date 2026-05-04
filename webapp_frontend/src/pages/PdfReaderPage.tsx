import { useEffect, useMemo, useRef, useState, type TouchEvent as ReactTouchEvent } from 'react';
import { ChevronLeft, ChevronRight, Maximize2, X, ZoomIn, ZoomOut } from 'lucide-react';
import * as pdfjsLib from 'pdfjs-dist';
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';
import { useSearchParams } from 'react-router-dom';
import { apiClient, ApiError } from '../api/client';
import { getDevInitData, useTelegramWebApp } from '../hooks/useTelegramWebApp';
import type { PdfHighlight, PdfHighlightRect } from '../types';

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

interface SelectionDraft {
  text: string;
  rects: PdfHighlightRect[];
  left: number;
  top: number;
  note: string;
  color: string;
}

interface ViewportAnchor {
  xRatio: number;
  yRatio: number;
  viewportX: number;
  viewportY: number;
}

export function PdfReaderPage() {
  const { webApp, initData, isReady, isTelegramMiniApp, expand } = useTelegramWebApp();
  const [params] = useSearchParams();
  const contentId = params.get('content_id') || '';

  const [assetId, setAssetId] = useState('');
  const [pdfUrl, setPdfUrl] = useState('');
  const [pdfBytes, setPdfBytes] = useState<Uint8Array | null>(null);
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
  const [fullscreenControlsVisible, setFullscreenControlsVisible] = useState(true);
  const [pageSize, setPageSize] = useState({ width: 0, height: 0 });
  const [selectionDraft, setSelectionDraft] = useState<SelectionDraft | null>(null);
  const [pageTurnDirection, setPageTurnDirection] = useState<'next' | 'prev' | null>(null);

  const [pageIndex, setPageIndex] = useState(0);
  const [selectedText, setSelectedText] = useState('');
  const [note, setNote] = useState('');
  const [color, setColor] = useState('#ffe066');
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const pageFrameRef = useRef<HTMLDivElement | null>(null);
  const textLayerRef = useRef<HTMLDivElement | null>(null);
  const shellRef = useRef<HTMLDivElement | null>(null);
  const resumeRatioRef = useRef(0);
  const pendingScrollFractionRef = useRef<number | null>(null);
  const pendingViewportAnchorRef = useRef<ViewportAnchor | null>(null);
  const progressRatioRef = useRef(0);
  const savedRatioRef = useRef(0);
  const contentIdRef = useRef(contentId);
  const canLoadApiRef = useRef(false);
  const autoSaveTimeoutRef = useRef<number | null>(null);
  const isSavingProgressRef = useRef(false);
  const queuedProgressRef = useRef<number | null>(null);
  const pinchStartDistanceRef = useRef<number | null>(null);
  const pinchStartScaleRef = useRef(1);
  const fullscreenChromeTimeoutRef = useRef<number | null>(null);
  const touchStartRef = useRef<{ x: number; y: number; at: number } | null>(null);

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

  const syncProgress = async (nextRatio = progressRatioRef.current, keepalive = false) => {
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
        client: keepalive ? 'web_pdf_reader_checkpoint' : 'web_pdf_reader_auto',
      }, keepalive ? { keepalive: true } : {});
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
        void syncProgress(queuedRatio, keepalive);
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

  const captureViewportAnchor = (clientX?: number, clientY?: number): ViewportAnchor | null => {
    const shell = shellRef.current;
    const pageFrame = pageFrameRef.current;
    if (!shell || !pageFrame) return null;

    const shellBox = shell.getBoundingClientRect();
    const pageBox = pageFrame.getBoundingClientRect();
    if (pageBox.width <= 0 || pageBox.height <= 0) return null;

    const anchorClientX = clientX ?? shellBox.left + shell.clientWidth / 2;
    const anchorClientY = clientY ?? shellBox.top + shell.clientHeight / 2;
    return {
      xRatio: clampRatio((anchorClientX - pageBox.left) / pageBox.width),
      yRatio: clampRatio((anchorClientY - pageBox.top) / pageBox.height),
      viewportX: anchorClientX - shellBox.left,
      viewportY: anchorClientY - shellBox.top,
    };
  };

  const clearNativeSelection = () => {
    const selection = window.getSelection();
    if (selection) {
      selection.removeAllRanges();
    }
  };

  const captureTextSelection = () => {
    const selection = window.getSelection();
    const pageFrame = pageFrameRef.current;
    const textLayer = textLayerRef.current;
    if (!selection || selection.rangeCount === 0 || !pageFrame || !textLayer) return;

    const text = selection.toString().trim();
    if (!text) {
      setSelectionDraft(null);
      return;
    }

    const anchorNode = selection.anchorNode;
    const focusNode = selection.focusNode;
    if (
      (anchorNode && !textLayer.contains(anchorNode)) ||
      (focusNode && !textLayer.contains(focusNode))
    ) {
      return;
    }

    const pageBox = pageFrame.getBoundingClientRect();
    if (pageBox.width <= 0 || pageBox.height <= 0) return;
    const rangeRects = Array.from(selection.getRangeAt(0).getClientRects());
    const rects = rangeRects
      .map((rect) => {
        const left = Math.max(rect.left, pageBox.left);
        const right = Math.min(rect.right, pageBox.right);
        const top = Math.max(rect.top, pageBox.top);
        const bottom = Math.min(rect.bottom, pageBox.bottom);
        if (right - left < 2 || bottom - top < 2) return null;
        return {
          x: clampRatio((left - pageBox.left) / pageBox.width),
          y: clampRatio((top - pageBox.top) / pageBox.height),
          width: clampRatio((right - left) / pageBox.width),
          height: clampRatio((bottom - top) / pageBox.height),
        };
      })
      .filter((rect): rect is PdfHighlightRect => Boolean(rect));

    if (rects.length === 0) return;
    const firstRect = rects[0];
    setSelectionDraft({
      text,
      rects,
      left: Math.min(pageBox.width - 180, Math.max(8, firstRect.x * pageBox.width)),
      top: Math.max(8, firstRect.y * pageBox.height - 48),
      note: '',
      color,
    });
  };

  const load = async () => {
    if (!canOpen || !canLoadApi) return;
    setLoading(true);
    setError('');
    setPdfUrl('');
    setPdfBytes(null);
    try {
      const open = await apiClient.getPdfOpen(contentId);
      setAssetId(open.asset_id);
      setPdfUrl(open.pdf_url);
      const blob = await apiClient.fetchPdfBlob(open.pdf_url);
      setPdfBytes(new Uint8Array(await blob.arrayBuffer()));
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
        void syncProgress(progressRatioRef.current, true);
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
      if (autoSaveTimeoutRef.current != null) {
        window.clearTimeout(autoSaveTimeoutRef.current);
      }
      if (Math.abs(progressRatioRef.current - savedRatioRef.current) >= 0.002) {
        void syncProgress(progressRatioRef.current, true);
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
    let selectionTimer: number | null = null;
    const handleSelectionChange = () => {
      if (selectionTimer != null) {
        window.clearTimeout(selectionTimer);
      }
      selectionTimer = window.setTimeout(() => {
        captureTextSelection();
        selectionTimer = null;
      }, 180);
    };
    document.addEventListener('selectionchange', handleSelectionChange);
    return () => {
      document.removeEventListener('selectionchange', handleSelectionChange);
      if (selectionTimer != null) {
        window.clearTimeout(selectionTimer);
      }
    };
  }, [pageNumber, scale, color]);

  useEffect(() => {
    if (!pageTurnDirection) return;
    const timeout = window.setTimeout(() => setPageTurnDirection(null), 240);
    return () => window.clearTimeout(timeout);
  }, [pageTurnDirection, pageNumber]);

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
    if (!isFullscreen) {
      document.body.classList.remove('pdf-reader-fullscreen-active');
      setFullscreenControlsVisible(true);
      if (fullscreenChromeTimeoutRef.current != null) {
        window.clearTimeout(fullscreenChromeTimeoutRef.current);
        fullscreenChromeTimeoutRef.current = null;
      }
      return;
    }

    document.body.classList.add('pdf-reader-fullscreen-active');
    if (fullscreenChromeTimeoutRef.current != null) {
      window.clearTimeout(fullscreenChromeTimeoutRef.current);
    }
    fullscreenChromeTimeoutRef.current = window.setTimeout(() => {
      setFullscreenControlsVisible(false);
      fullscreenChromeTimeoutRef.current = null;
    }, 2200);

    return () => {
      document.body.classList.remove('pdf-reader-fullscreen-active');
      if (fullscreenChromeTimeoutRef.current != null) {
        window.clearTimeout(fullscreenChromeTimeoutRef.current);
        fullscreenChromeTimeoutRef.current = null;
      }
    };
  }, [isFullscreen, fullscreenControlsVisible, pageNumber, scale]);

  useEffect(() => {
    let cancelled = false;
    let loadedDoc: pdfjsLib.PDFDocumentProxy | null = null;
    if (!pdfBytes) {
      setPdfDoc(null);
      setPageCount(0);
      setPageNumber(1);
      return;
    }

    setRendering(true);
    pdfjsLib.getDocument({
      data: pdfBytes.slice(),
      disableAutoFetch: true,
      disableRange: true,
      disableStream: true,
      useSystemFonts: true,
    }).promise
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
  }, [pdfBytes]);

  useEffect(() => {
    let cancelled = false;
    let renderTask: pdfjsLib.RenderTask | null = null;
    let textLayer: pdfjsLib.TextLayer | null = null;

    async function renderPage() {
      if (!pdfDoc || !canvasRef.current || !textLayerRef.current) return;
      setRendering(true);
      setSelectionDraft(null);
      try {
        const page = await pdfDoc.getPage(pageNumber);
        if (cancelled) return;
        const viewport = page.getViewport({ scale });
        const canvas = canvasRef.current;
        const textLayerDiv = textLayerRef.current;
        const context = canvas.getContext('2d');
        if (!context) return;

        const outputScale = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = Math.floor(viewport.width * outputScale);
        canvas.height = Math.floor(viewport.height * outputScale);
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;
        setPageSize({ width: viewport.width, height: viewport.height });
        textLayerDiv.replaceChildren();

        context.setTransform(outputScale, 0, 0, outputScale, 0, 0);
        context.clearRect(0, 0, viewport.width, viewport.height);
        renderTask = page.render({ canvas, canvasContext: context, viewport });
        const textContent = page.streamTextContent();
        textLayer = new pdfjsLib.TextLayer({
          textContentSource: textContent,
          container: textLayerDiv,
          viewport,
        });
        await Promise.all([renderTask.promise, textLayer.render()]);
        const pendingViewportAnchor = pendingViewportAnchorRef.current;
        if (!cancelled && pendingViewportAnchor && shellRef.current && pageFrameRef.current) {
          pendingViewportAnchorRef.current = null;
          window.requestAnimationFrame(() => {
            const shell = shellRef.current;
            const pageFrame = pageFrameRef.current;
            if (!shell || !pageFrame) return;
            const maxScrollLeft = Math.max(0, shell.scrollWidth - shell.clientWidth);
            const maxScrollTop = Math.max(0, shell.scrollHeight - shell.clientHeight);
            const nextScrollLeft = pageFrame.offsetLeft + (pendingViewportAnchor.xRatio * pageFrame.offsetWidth) - pendingViewportAnchor.viewportX;
            const nextScrollTop = pageFrame.offsetTop + (pendingViewportAnchor.yRatio * pageFrame.offsetHeight) - pendingViewportAnchor.viewportY;
            shell.scrollLeft = Math.max(0, Math.min(maxScrollLeft, nextScrollLeft));
            shell.scrollTop = Math.max(0, Math.min(maxScrollTop, nextScrollTop));
            updateProgressFromReader(pageNumber);
          });
          return;
        }
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
      textLayer?.cancel();
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

  const enterFullscreen = async () => {
    setIsFullscreen(true);
    setFullscreenControlsVisible(true);
    expand();
    try {
      webApp?.requestFullscreen?.();
    } catch {
      // Telegram fullscreen is best-effort across client versions.
    }
    try {
      if (document.documentElement.requestFullscreen && !document.fullscreenElement) {
        await document.documentElement.requestFullscreen();
      }
    } catch {
      // Telegram iOS may reject the browser Fullscreen API; CSS reader mode still fills the viewport.
    }
  };

  const exitFullscreen = async () => {
    setIsFullscreen(false);
    setFullscreenControlsVisible(true);
    try {
      webApp?.exitFullscreen?.();
    } catch {
      // Ignore unsupported Telegram fullscreen exit.
    }
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      }
    } catch {
      // Ignore unsupported browser fullscreen exit.
    }
  };

  const revealFullscreenControls = () => {
    if (!isFullscreen) return;
    setFullscreenControlsVisible(true);
  };

  const goToPage = (nextPage: number) => {
    if (!pageCount) return;
    const bounded = Math.min(Math.max(nextPage, 1), pageCount);
    if (bounded === pageNumber) return;
    const nextRatio = clampRatio((bounded - 1) / pageCount);
    setPageTurnDirection(bounded > pageNumber ? 'next' : 'prev');
    if (shellRef.current) {
      shellRef.current.scrollTop = 0;
    }
    if (autoSaveTimeoutRef.current != null) {
      window.clearTimeout(autoSaveTimeoutRef.current);
      autoSaveTimeoutRef.current = null;
    }
    pendingScrollFractionRef.current = 0;
    progressRatioRef.current = nextRatio;
    setSelectionDraft(null);
    clearNativeSelection();
    setPageNumber(bounded);
    setPageIndex(bounded - 1);
    setProgressRatio(nextRatio);
    void syncProgress(nextRatio);
  };

  const turnFullscreenPage = (direction: -1 | 1) => {
    revealFullscreenControls();
    goToPage(pageNumber + direction);
  };

  const zoomBy = (delta: number) => {
    pendingViewportAnchorRef.current = captureViewportAnchor();
    setScale((current) => Math.min(2.5, Math.max(0.65, Number((current + delta).toFixed(2)))));
  };

  const handleReaderScroll = () => {
    updateProgressFromReader();
  };

  const handleTouchStart = (event: ReactTouchEvent<HTMLDivElement>) => {
    if (event.touches.length === 2) {
      pinchStartDistanceRef.current = getTouchDistance(event.touches);
      pinchStartScaleRef.current = scale;
      touchStartRef.current = null;
      return;
    }
    if (event.touches.length === 1) {
      const touch = event.touches[0];
      touchStartRef.current = { x: touch.clientX, y: touch.clientY, at: Date.now() };
    }
  };

  const handleTouchMove = (event: ReactTouchEvent<HTMLDivElement>) => {
    if (event.touches.length !== 2 || !pinchStartDistanceRef.current) return;
    event.preventDefault();
    const nextDistance = getTouchDistance(event.touches);
    if (!nextDistance) return;
    const [a, b] = [event.touches[0], event.touches[1]];
    pendingViewportAnchorRef.current = captureViewportAnchor(
      (a.clientX + b.clientX) / 2,
      (a.clientY + b.clientY) / 2,
    );
    const nextScale = pinchStartScaleRef.current * (nextDistance / pinchStartDistanceRef.current);
    setScale(Math.min(3, Math.max(0.55, Number(nextScale.toFixed(2)))));
  };

  const handleTouchEnd = (event: ReactTouchEvent<HTMLDivElement>) => {
    if (event.touches.length < 2) {
      pinchStartDistanceRef.current = null;
      pinchStartScaleRef.current = scale;
    }
    if (!isFullscreen || event.changedTouches.length === 0 || !touchStartRef.current) {
      touchStartRef.current = null;
      return;
    }
    const touch = event.changedTouches[0];
    const dx = touch.clientX - touchStartRef.current.x;
    const dy = touch.clientY - touchStartRef.current.y;
    const elapsed = Date.now() - touchStartRef.current.at;
    touchStartRef.current = null;
    if (elapsed > 700 || Math.abs(dx) < 55 || Math.abs(dy) > 80) return;
    if (dx < 0) {
      turnFullscreenPage(1);
    } else {
      turnFullscreenPage(-1);
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

  const saveSelectionHighlight = async () => {
    if (!contentId || !assetId || !selectionDraft) return;
    setError('');
    try {
      await apiClient.createPdfHighlight(contentId, {
        asset_id: assetId,
        page_index: pageNumber - 1,
        rects: selectionDraft.rects,
        selected_text: selectionDraft.text,
        note: selectionDraft.note || undefined,
        color: selectionDraft.color,
      });
      setSelectedText('');
      setNote('');
      setSelectionDraft(null);
      clearNativeSelection();
      const h = await apiClient.getPdfHighlights(contentId, assetId);
      setHighlights(h.items || []);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message || 'Failed to save selected highlight');
      } else {
        setError('Failed to save selected highlight');
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
    <div className={`pdf-reader-page${isFullscreen ? ' pdf-reader-page--fullscreen' : ''}${isFullscreen && !fullscreenControlsVisible ? ' pdf-reader-page--chrome-hidden' : ''}`}>
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
            onClick={isFullscreen ? exitFullscreen : enterFullscreen}
            title={isFullscreen ? 'Exit reader mode' : 'Reader fullscreen'}
            type="button"
          >
            {isFullscreen ? <X size={18} /> : <Maximize2 size={18} />}
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
            onClick={revealFullscreenControls}
          >
            <div
              ref={pageFrameRef}
              className={[
                'pdf-reader-page-frame',
                pageTurnDirection ? `pdf-reader-page-frame--turn-${pageTurnDirection}` : '',
              ].join(' ')}
              style={pageSize.width && pageSize.height ? { width: pageSize.width, height: pageSize.height } : undefined}
            >
              <canvas ref={canvasRef} className="pdf-reader-canvas" />
              <div ref={textLayerRef} className="pdf-reader-text-layer textLayer" />
              <div className="pdf-reader-highlight-layer" aria-hidden="true">
                {highlights
                  .filter((highlight) => highlight.page_index === pageNumber - 1)
                  .flatMap((highlight) =>
                    (highlight.rects_json || []).map((rect, rectIndex) => (
                      <div
                        key={`${highlight.id}-${rectIndex}`}
                        className="pdf-reader-highlight-rect"
                        style={{
                          left: `${rect.x * 100}%`,
                          top: `${rect.y * 100}%`,
                          width: `${rect.width * 100}%`,
                          height: `${rect.height * 100}%`,
                          backgroundColor: highlight.color || '#ffe066',
                        }}
                      />
                    )),
                  )}
              </div>
              {selectionDraft && (
                <div
                  className="pdf-reader-selection-popover"
                  style={{ left: selectionDraft.left, top: selectionDraft.top }}
                  onMouseDown={(event) => event.stopPropagation()}
                  onTouchStart={(event) => event.stopPropagation()}
                >
                  <div className="pdf-reader-selection-text">{selectionDraft.text}</div>
                  <textarea
                    value={selectionDraft.note}
                    onChange={(event) => setSelectionDraft((draft) => draft ? { ...draft, note: event.target.value } : draft)}
                    placeholder="Add note (optional)"
                    rows={2}
                  />
                  <div className="pdf-reader-selection-actions">
                    <input
                      aria-label="Highlight color"
                      type="color"
                      value={selectionDraft.color}
                      onChange={(event) => setSelectionDraft((draft) => draft ? { ...draft, color: event.target.value } : draft)}
                    />
                    <button type="button" onClick={saveSelectionHighlight}>
                      Highlight
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectionDraft(null);
                        clearNativeSelection();
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
            {rendering && <div className="pdf-reader-rendering">Rendering...</div>}
            {isFullscreen && (
              <>
                <button
                  className="pdf-reader-page-zone pdf-reader-page-zone--prev"
                  onClick={(event) => {
                    event.stopPropagation();
                    turnFullscreenPage(-1);
                  }}
                  disabled={pageNumber <= 1}
                  type="button"
                  aria-label="Previous page"
                >
                  <ChevronLeft size={18} />
                </button>
                <button
                  className="pdf-reader-page-zone pdf-reader-page-zone--next"
                  onClick={(event) => {
                    event.stopPropagation();
                    turnFullscreenPage(1);
                  }}
                  disabled={pageNumber >= pageCount}
                  type="button"
                  aria-label="Next page"
                >
                  <ChevronRight size={18} />
                </button>
                <div className="pdf-reader-fullscreen-toast">
                  Tap edges to turn page
                </div>
              </>
            )}
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
