import { useTranslation } from 'react-i18next';
import { useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent, type WheelEvent } from 'react';
import { ArrowLeft, ChevronLeft, ChevronRight, FileText, MoreHorizontal, PanelRight, ScanLine, Trash2, Users, X, ZoomIn, ZoomOut } from 'lucide-react';
import * as pdfjsLib from 'pdfjs-dist/legacy/build/pdf.mjs';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { apiClient, ApiError } from '../api/client';
import { HeatmapBar } from '../components/HeatmapBar';
import { getDevInitData, useTelegramWebApp } from '../hooks/useTelegramWebApp';
import type { ContentCoReader, ContentWord, PdfHighlight } from '../types';
import { AddToDeckSheet } from './pdfReader/AddToDeckSheet';
import { HighlightLayer } from './pdfReader/HighlightLayer';
import { HighlightPopover } from './pdfReader/HighlightPopover';
import { useHighlightPopover } from './pdfReader/useHighlightPopover';
import { usePdfDocument } from './pdfReader/usePdfDocument';
import { usePinchZoom } from './pdfReader/usePinchZoom';
import { clearNativeSelection, detectTextLayerDirection, useTextSelection } from './pdfReader/useTextSelection';
import type { ViewportAnchor } from './pdfReader/types';

const PDF_READ_BUCKET_COUNT = 120;
const PDF_READ_DWELL_SECONDS = 15;
const MAX_CANVAS_PIXELS = 16_000_000;
const MAX_PDF_SCALE = 4;

type PageRasterCacheEntry = {
  scale: number;
  width: number;
  height: number;
  canvas: HTMLCanvasElement;
};

const getCanvasOutputScale = (viewportWidth: number, viewportHeight: number) => {
  const targetDpr = window.devicePixelRatio || 1;
  const baseArea = viewportWidth * viewportHeight;
  const budgetScale = baseArea > 0 ? Math.sqrt(MAX_CANVAS_PIXELS / baseArea) : 3;
  return Math.max(1, Math.min(targetDpr, 3, budgetScale));
};

const applyRasterCacheToCanvas = (target: HTMLCanvasElement, entry: PageRasterCacheEntry) => {
  target.width = entry.canvas.width;
  target.height = entry.canvas.height;
  target.style.width = entry.canvas.style.width;
  target.style.height = entry.canvas.style.height;
  const context = target.getContext('2d');
  if (context) {
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.drawImage(entry.canvas, 0, 0);
  }
};

/** The deck most of a document's words were saved into, for "Review". */
function mostCommonDeck(words: ContentWord[]): ContentWord | null {
  const counts = new Map<string, number>();
  words.forEach((word) => counts.set(word.deck_id, (counts.get(word.deck_id) || 0) + 1));
  let best: ContentWord | null = null;
  words.forEach((word) => {
    if (!best || (counts.get(word.deck_id) || 0) > (counts.get(best.deck_id) || 0)) best = word;
  });
  return best;
}

export function PdfReaderPage() {
  const { t } = useTranslation();
  const { initData, isReady, isTelegramMiniApp, expand } = useTelegramWebApp();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const contentId = params.get('content_id') || '';
  const returnTo = params.get('return_to') || '';
  const requestedPage = Number(params.get('page'));

  const [assetId, setAssetId] = useState('');
  const [pdfUrl, setPdfUrl] = useState('');
  const [pdfBytes, setPdfBytes] = useState<Uint8Array | null>(null);
  const [expiresAt, setExpiresAt] = useState('');
  const [progressRatio, setProgressRatio] = useState(0);
  const [resumeRatio, setResumeRatio] = useState(0);
  const [coverageBuckets, setCoverageBuckets] = useState<number[]>(() => Array(PDF_READ_BUCKET_COUNT).fill(0));
  const [coverageBucketCount, setCoverageBucketCount] = useState(PDF_READ_BUCKET_COUNT);
  const [highlights, setHighlights] = useState<PdfHighlight[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [syncStatus, setSyncStatus] = useState<'idle' | 'pending' | 'saving' | 'saved' | 'error'>('idle');
  const [error, setError] = useState('');
  const [scale, setScale] = useState(1);
  const [rendering, setRendering] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [savedWords, setSavedWords] = useState<ContentWord[]>([]);
  const [pageSize, setPageSize] = useState({ width: 0, height: 0 });
  const [pageTurnDirection, setPageTurnDirection] = useState<'next' | 'prev' | null>(null);
  const [highlightsOpen, setHighlightsOpen] = useState(false);

  // Content sharing context (club_id set only when this PDF is shared to a
  // club). Drives the co-reading poll and the teacher's roster/switch-student
  // panel — see the annotation-sharing design in the UX review this came
  // from: teacher = club owner, students never see each other's highlights.
  const [contentTitle, setContentTitle] = useState('');
  const [contentLanguage, setContentLanguage] = useState('');
  const [clubId, setClubId] = useState<string | null>(null);
  const [isTeacher, setIsTeacher] = useState(false);
  const [viewingUserId, setViewingUserId] = useState<string | null>(null);
  const [coReaders, setCoReaders] = useState<ContentCoReader[]>([]);
  const [coReadersOpen, setCoReadersOpen] = useState(false);
  const [addToDeckDraft, setAddToDeckDraft] = useState<{
    text: string;
    pageIndex: number;
    highlightId?: string;
  } | null>(null);

  const [color, setColor] = useState('#ffe066');
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const pageFrameRef = useRef<HTMLDivElement | null>(null);
  const textLayerRef = useRef<HTMLDivElement | null>(null);
  const shellRef = useRef<HTMLDivElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const resumeRatioRef = useRef(0);
  const pendingScrollFractionRef = useRef<number | null>(null);
  const pendingViewportAnchorRef = useRef<ViewportAnchor | null>(null);
  const progressRatioRef = useRef(0);
  const savedRatioRef = useRef(0);
  const coverageBucketsRef = useRef<number[]>(Array(PDF_READ_BUCKET_COUNT).fill(0));
  const dwellSecondsRef = useRef<number[]>(Array(PDF_READ_BUCKET_COUNT).fill(0));
  const readSyncInFlightRef = useRef(false);
  const contentIdRef = useRef(contentId);
  const canLoadApiRef = useRef(false);
  const autoSaveTimeoutRef = useRef<number | null>(null);
  const isSavingProgressRef = useRef(false);
  const queuedProgressRef = useRef<number | null>(null);
  const pageRasterCacheRef = useRef<Map<number, PageRasterCacheEntry>>(new Map());
  const panRef = useRef<{ pointerId: number; clientX: number; clientY: number; scrollLeft: number; scrollTop: number } | null>(null);
  const wheelPageTurnLockUntilRef = useRef(0);
  const [isPanning, setIsPanning] = useState(false);

  const canOpen = Boolean(contentId);
  const authData = initData || getDevInitData();
  const hasBrowserToken = typeof window !== 'undefined' && !!localStorage.getItem('telegram_auth_token');
  const canLoadApi = isReady && (!!authData || hasBrowserToken);
  contentIdRef.current = contentId;
  canLoadApiRef.current = canLoadApi;

  const {
    pdfDoc,
    pageCount,
    pageNumber,
    setPageNumber,
    documentRendering,
  } = usePdfDocument({
    pdfBytes,
    resumeRatioRef,
    pendingScrollFractionRef,
    setError,
  });

  useEffect(() => {
    if (Number.isInteger(requestedPage) && requestedPage >= 1 && pageCount > 0) {
      setPageNumber(Math.min(pageCount, requestedPage));
    }
  }, [pageCount, requestedPage, setPageNumber]);

  const { selectionDraft, setSelectionDraft } = useTextSelection({
    pageFrameRef,
    textLayerRef,
    popoverRef,
    pageNumber,
    scale,
    color,
  });

  const popoverPos = useHighlightPopover({
    selectionDraft,
    popoverRef,
    pageFrameRef,
    shellRef,
    scale,
    pageNumber,
  });

  const {
    captureViewportAnchor,
    pinchPreview,
    clearPinchPreview,
    isPinchingRef,
    handleTouchStart,
    handleTouchMove,
    handleTouchEnd,
  } = usePinchZoom({
    scale,
    setScale,
    shellRef,
    pageFrameRef,
    pendingViewportAnchorRef,
    setSelectionDraft,
    clearNativeSelection,
  });
  const isRendering = rendering || documentRendering;

  useEffect(() => {
    if (authData) {
      apiClient.setInitData(authData);
    }
  }, [authData]);

  const clampRatio = (ratio: number) => Math.max(0, Math.min(1, ratio));
  const computeCoverageRatio = (buckets: number[]) => {
    if (!buckets.length) return 0;
    return buckets.filter((value) => (value || 0) > 0).length / buckets.length;
  };

  const normalizeBuckets = (buckets: number[] | undefined, count = PDF_READ_BUCKET_COUNT) => {
    return Array.from({ length: count }, (_, index) => buckets?.[index] ?? 0);
  };

  const mapRatioRangeToBuckets = (start: number, end: number, count: number) => {
    const boundedStart = clampRatio(start);
    const boundedEnd = clampRatio(end);
    if (boundedEnd <= boundedStart || count <= 0) return [];
    const startIndex = Math.max(0, Math.min(count - 1, Math.floor(boundedStart * count)));
    const endIndex = Math.max(0, Math.min(count - 1, Math.ceil(boundedEnd * count) - 1));
    if (startIndex > endIndex) return [];
    return Array.from({ length: endIndex - startIndex + 1 }, (_, offset) => startIndex + offset);
  };

  const groupContiguousBuckets = (indices: number[]) => {
    const sorted = Array.from(new Set(indices)).sort((a, b) => a - b);
    const groups: Array<{ start: number; end: number }> = [];
    sorted.forEach((index) => {
      const last = groups[groups.length - 1];
      if (last && index === last.end + 1) {
        last.end = index;
      } else {
        groups.push({ start: index, end: index });
      }
    });
    return groups;
  };

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
        client: 'web_pdf_reader_checkpoint',
      }, keepalive ? { keepalive: true } : {});
      savedRatioRef.current = boundedRatio;
      setSyncStatus('saved');
    } catch (err) {
      setSyncStatus('error');
      if (err instanceof ApiError) {
        setError(err.message || 'Failed to sync reading progress');
      } else {
        setError(t('pdfReader.failedToSyncReadingProgress'));
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
    const boundedRatio = clampRatio(nextRatio);
    progressRatioRef.current = boundedRatio;
    setResumeRatio(boundedRatio);
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
      setContentTitle(open.title || '');
      setContentLanguage(open.language || '');
      setClubId(open.club_id || null);
      setIsTeacher(Boolean(open.is_teacher));
      const blob = await apiClient.fetchPdfBlob(open.pdf_url);
      setPdfBytes(new Uint8Array(await blob.arrayBuffer()));
      setExpiresAt(open.expires_at);
      const resume = Number(open.last_position ?? 0);
      const boundedResume = clampRatio(resume);
      resumeRatioRef.current = boundedResume;
      progressRatioRef.current = boundedResume;
      savedRatioRef.current = boundedResume;
      setResumeRatio(boundedResume);
      setProgressRatio(clampRatio(Number(open.progress_ratio ?? 0)));
      setSyncStatus('saved');

      const heatmap = await apiClient.getContentHeatmap(contentId);
      const bucketCount = heatmap.bucket_count || PDF_READ_BUCKET_COUNT;
      const normalizedBuckets = normalizeBuckets(heatmap.buckets, bucketCount);
      coverageBucketsRef.current = normalizedBuckets;
      dwellSecondsRef.current = Array(bucketCount).fill(0);
      setCoverageBucketCount(bucketCount);
      setCoverageBuckets(normalizedBuckets);
      setProgressRatio(computeCoverageRatio(normalizedBuckets));

      const h = await apiClient.getPdfHighlights(contentId, open.asset_id, viewingUserId || undefined);
      setHighlights(h.items || []);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message || 'Failed to open PDF');
      } else {
        setError(t('pdfReader.failedToOpenPdf'));
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isReady && isTelegramMiniApp && !authData && !hasBrowserToken) {
      setLoading(false);
      setError(t('pdfReader.telegramDidNotProvideAuthenticationDataPleas'));
      return;
    }
    load();
  }, [contentId, canLoadApi, isReady, isTelegramMiniApp, authData, hasBrowserToken]);

  // The reader is always the immersive layout now; give it the full height.
  useEffect(() => {
    expand();
  }, [expand]);

  // Open a document fitted to the screen width when its page is wider than
  // the screen (every A4 page on a phone), instead of cutting the text off.
  // Only once per document, so a later manual zoom is respected.
  const autoFittedRef = useRef(false);
  useEffect(() => {
    autoFittedRef.current = false;
  }, [contentId]);
  useEffect(() => {
    const shell = shellRef.current;
    if (autoFittedRef.current || !shell || !pageSize.width) return;
    autoFittedRef.current = true;
    if (pageSize.width > shell.clientWidth - 8) fitToWidth();
  }, [pageSize.width]);

  const loadSavedWords = () => {
    if (!contentId || !canLoadApi) return;
    apiClient
      .getContentWords(contentId)
      .then((res) => setSavedWords(res.items || []))
      .catch(() => {
        /* the list is a convenience; the reader keeps working without it */
      });
  };

  useEffect(() => {
    loadSavedWords();
  }, [contentId, canLoadApi]);

  // Re-fetch highlights whenever the teacher switches which student's marks
  // they're looking at.
  useEffect(() => {
    if (!contentId || !assetId || !canLoadApi) return;
    apiClient
      .getPdfHighlights(contentId, assetId, viewingUserId || undefined)
      .then((h) => setHighlights(h.items || []))
      .catch(() => {
        /* keep showing the last-known highlights on a transient failure */
      });
  }, [viewingUserId]);

  // Live co-reading: on club-shared content, poll for the other side's
  // highlights every few seconds so a teacher and student marking up the
  // same page in parallel see each other show up without a manual refresh.
  // Polling (not a socket) keeps this to a plain HTTP endpoint for a class
  // of a handful of people; paused when the tab isn't visible.
  useEffect(() => {
    if (!clubId || !contentId || !assetId || !canLoadApi) return;
    let cancelled = false;
    const poll = () => {
      if (document.visibilityState !== 'visible') return;
      apiClient
        .getPdfHighlights(contentId, assetId, viewingUserId || undefined)
        .then((h) => {
          if (!cancelled) setHighlights(h.items || []);
        })
        .catch(() => {
          /* skip this tick; try again on the next one */
        });
    };
    const interval = window.setInterval(poll, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [clubId, contentId, assetId, canLoadApi, viewingUserId]);

  useEffect(() => {
    if (!isTeacher || !contentId || !coReadersOpen) return;
    apiClient
      .getContentCoReaders(contentId)
      .then((res) => setCoReaders(res.items || []))
      .catch(() => setCoReaders([]));
  }, [isTeacher, contentId, coReadersOpen]);

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
    if (!loading && pageCount > 0) {
      scheduleProgressSync(resumeRatio);
    }
  }, [resumeRatio, loading, pageCount]);

  useEffect(() => {
    if (!pageTurnDirection) return;
    const timeout = window.setTimeout(() => setPageTurnDirection(null), 240);
    return () => window.clearTimeout(timeout);
  }, [pageTurnDirection, pageNumber]);

  useEffect(() => {
    pageRasterCacheRef.current.clear();
  }, [scale]);

  useEffect(() => {
    if (!pdfDoc || !pageCount || loading) return;
    const doc = pdfDoc;
    let cancelled = false;

    async function prefetchPage(targetPage: number) {
      if (targetPage < 1 || targetPage > pageCount) return;
      const existing = pageRasterCacheRef.current.get(targetPage);
      if (existing?.scale === scale) return;

      try {
        const page = await doc.getPage(targetPage);
        if (cancelled) return;
        const viewport = page.getViewport({ scale });
        const outputScale = getCanvasOutputScale(viewport.width, viewport.height);
        const offscreen = document.createElement('canvas');
        offscreen.width = Math.floor(viewport.width * outputScale);
        offscreen.height = Math.floor(viewport.height * outputScale);
        offscreen.style.width = `${viewport.width}px`;
        offscreen.style.height = `${viewport.height}px`;
        const context = offscreen.getContext('2d');
        if (!context) return;
        context.setTransform(outputScale, 0, 0, outputScale, 0, 0);
        context.clearRect(0, 0, viewport.width, viewport.height);
        const task = page.render({ canvas: offscreen, canvasContext: context, viewport });
        await task.promise;
        if (cancelled) return;
        pageRasterCacheRef.current.set(targetPage, {
          scale,
          width: viewport.width,
          height: viewport.height,
          canvas: offscreen,
        });
      } catch {
        // Prefetch is best-effort; the active page render handles failures.
      }
    }

    void prefetchPage(pageNumber - 1);
    void prefetchPage(pageNumber + 1);

    return () => {
      cancelled = true;
    };
  }, [loading, pageCount, pageNumber, pdfDoc, scale]);

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
        const newWidth = viewport.width;
        const newHeight = viewport.height;
        const canvas = canvasRef.current;
        const textLayerDiv = textLayerRef.current;
        const pageFrame = pageFrameRef.current;
        const context = canvas.getContext('2d');
        if (!context) return;

        // pdf.js TextLayer CSS uses --total-scale-factor (= --scale-factor * --user-unit).
        pageFrame?.style.setProperty('--scale-factor', String(scale));

        const cachedRaster = pageRasterCacheRef.current.get(pageNumber);
        const cacheMatchesViewport = cachedRaster?.scale === scale
          && cachedRaster.width === newWidth
          && cachedRaster.height === newHeight;
        const outputScale = getCanvasOutputScale(newWidth, newHeight);

        if (!cancelled && cacheMatchesViewport) {
          applyRasterCacheToCanvas(canvas, cachedRaster);
          setPageSize({ width: newWidth, height: newHeight });
        } else {
          canvas.width = Math.floor(newWidth * outputScale);
          canvas.height = Math.floor(newHeight * outputScale);
          canvas.style.width = `${newWidth}px`;
          canvas.style.height = `${newHeight}px`;
          setPageSize({ width: newWidth, height: newHeight });
        }

        textLayerDiv.replaceChildren();
        const textContent = page.streamTextContent();
        textLayer = new pdfjsLib.TextLayer({
          textContentSource: textContent,
          container: textLayerDiv,
          viewport,
        });

        const canvasRenderPromise = (async () => {
          if (cacheMatchesViewport) return;
          context.setTransform(outputScale, 0, 0, outputScale, 0, 0);
          context.clearRect(0, 0, newWidth, newHeight);
          renderTask = page.render({ canvas, canvasContext: context, viewport });
          await renderTask.promise;
          if (cancelled) return;

          const cacheCanvas = document.createElement('canvas');
          cacheCanvas.width = canvas.width;
          cacheCanvas.height = canvas.height;
          cacheCanvas.style.width = canvas.style.width;
          cacheCanvas.style.height = canvas.style.height;
          const cacheContext = cacheCanvas.getContext('2d');
          if (cacheContext) {
            cacheContext.drawImage(canvas, 0, 0);
            pageRasterCacheRef.current.set(pageNumber, {
              scale,
              width: newWidth,
              height: newHeight,
              canvas: cacheCanvas,
            });
          }
        })();

        await Promise.all([canvasRenderPromise, textLayer.render()]);
        if (cancelled) return;

        const textDirection = detectTextLayerDirection(textLayerDiv);
        textLayerDiv.dir = textDirection;
        textLayerDiv.dataset.textDirection = textDirection;
        const finishRenderPreview = () => {
          window.requestAnimationFrame(() => clearPinchPreview());
        };
        const pendingViewportAnchor = pendingViewportAnchorRef.current;
        if (!cancelled && pendingViewportAnchor && shellRef.current && pageFrameRef.current) {
          pendingViewportAnchorRef.current = null;
          window.requestAnimationFrame(() => {
            const shell = shellRef.current;
            const pageFrame = pageFrameRef.current;
            if (!shell || !pageFrame) return;
            const maxScrollLeft = Math.max(0, shell.scrollWidth - shell.clientWidth);
            const maxScrollTop = Math.max(0, shell.scrollHeight - shell.clientHeight);
            const nextScrollLeft = pageFrame.offsetLeft + (pendingViewportAnchor.xRatio * newWidth) - pendingViewportAnchor.viewportX;
            const nextScrollTop = pageFrame.offsetTop + (pendingViewportAnchor.yRatio * newHeight) - pendingViewportAnchor.viewportY;
            shell.scrollLeft = Math.max(0, Math.min(maxScrollLeft, nextScrollLeft));
            shell.scrollTop = Math.max(0, Math.min(maxScrollTop, nextScrollTop));
            updateProgressFromReader(pageNumber);
            clearPinchPreview();
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
            clearPinchPreview();
          });
          return;
        }
        finishRenderPreview();
      } catch (err) {
        if (!cancelled && !(err instanceof Error && err.name === 'RenderingCancelledException')) {
          setError(t('pdfReader.failedToRenderPdfPage'));
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
  }, [clearPinchPreview, pdfDoc, pageNumber, scale]);

  const getVisibleReadRange = () => {
    const shell = shellRef.current;
    const pageFrame = pageFrameRef.current;
    if (!shell || !pageFrame || !pageCount) return null;
    const shellBox = shell.getBoundingClientRect();
    const pageBox = pageFrame.getBoundingClientRect();
    if (pageBox.height <= 0) return null;

    const visibleTop = Math.max(shellBox.top, pageBox.top);
    const visibleBottom = Math.min(shellBox.bottom, pageBox.bottom);
    if (visibleBottom - visibleTop < 24) return null;

    const pageStart = clampRatio((visibleTop - pageBox.top) / pageBox.height);
    const pageEnd = clampRatio((visibleBottom - pageBox.top) / pageBox.height);
    const start = ((pageNumber - 1) + pageStart) / pageCount;
    const end = ((pageNumber - 1) + pageEnd) / pageCount;
    return { start: clampRatio(start), end: clampRatio(end) };
  };

  const syncReadBuckets = async (indices: number[]) => {
    if (!contentId || !canLoadApi || indices.length === 0) return;
    const groups = groupContiguousBuckets(indices);
    readSyncInFlightRef.current = true;
    try {
      for (const group of groups) {
        const response = await apiClient.postConsumeEvent({
          content_id: contentId,
          start_position: group.start / coverageBucketCount,
          end_position: (group.end + 1) / coverageBucketCount,
          position_unit: 'ratio',
          client: 'web_pdf_reader_read',
        });
        if (typeof response.progress_ratio === 'number') {
          setProgressRatio((current) => Math.max(current, response.progress_ratio));
        }
      }
      setSyncStatus('saved');
    } catch (err) {
      setSyncStatus('error');
      if (err instanceof ApiError) {
        setError(err.message || 'Failed to sync read coverage');
      } else {
        setError(t('pdfReader.failedToSyncReadCoverage'));
      }
    } finally {
      readSyncInFlightRef.current = false;
    }
  };

  useEffect(() => {
    if (!pdfDoc || loading || !pageCount || coverageBucketCount <= 0) return;
    const interval = window.setInterval(() => {
      if (
        document.visibilityState === 'hidden' ||
        isRendering ||
        isPinchingRef.current ||
        pageTurnDirection
      ) {
        return;
      }
      const visibleRange = getVisibleReadRange();
      if (!visibleRange) return;
      const visibleBuckets = mapRatioRangeToBuckets(visibleRange.start, visibleRange.end, coverageBucketCount);
      if (visibleBuckets.length === 0) return;

      const dwell = dwellSecondsRef.current.length === coverageBucketCount
        ? [...dwellSecondsRef.current]
        : Array(coverageBucketCount).fill(0);
      const currentBuckets = coverageBucketsRef.current.length === coverageBucketCount
        ? [...coverageBucketsRef.current]
        : normalizeBuckets(coverageBucketsRef.current, coverageBucketCount);
      const newlyQualified: number[] = [];

      visibleBuckets.forEach((bucketIndex) => {
        dwell[bucketIndex] = (dwell[bucketIndex] || 0) + 1;
        if (dwell[bucketIndex] >= PDF_READ_DWELL_SECONDS && !(currentBuckets[bucketIndex] > 0)) {
          currentBuckets[bucketIndex] = 1;
          newlyQualified.push(bucketIndex);
        }
      });

      dwellSecondsRef.current = dwell;
      if (newlyQualified.length > 0) {
        coverageBucketsRef.current = currentBuckets;
        setCoverageBuckets(currentBuckets);
        setProgressRatio(computeCoverageRatio(currentBuckets));
        void syncReadBuckets(newlyQualified);
      }
    }, 1000);

    return () => window.clearInterval(interval);
  }, [coverageBucketCount, isPinchingRef, isRendering, loading, pageCount, pageNumber, pageTurnDirection, pdfDoc, scale]);

  const progressPct = useMemo(() => Math.round(progressRatio * 100), [progressRatio]);
  const highlightGroups = useMemo(() => {
    const byPage = new Map<number, PdfHighlight[]>();
    [...highlights]
      .sort((a, b) => a.page_index - b.page_index || (a.created_at || '').localeCompare(b.created_at || ''))
      .forEach((highlight) => {
        const group = byPage.get(highlight.page_index) || [];
        group.push(highlight);
        byPage.set(highlight.page_index, group);
      });
    return Array.from(byPage.entries()).map(([pageIndex, items]) => ({ pageIndex, items }));
  }, [highlights]);

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
    setResumeRatio(nextRatio);
    void syncProgress(nextRatio);
  };

  const returnToLibrary = () => {
    const historyIndex = Number(window.history.state?.idx);
    if (Number.isFinite(historyIndex) && historyIndex > 0) {
      navigate(-1);
      return;
    }
    const safeReturnPath = returnTo.startsWith('/') && !returnTo.startsWith('//')
      ? returnTo
      : '/my-contents';
    navigate(safeReturnPath, { replace: true });
  };

  const fitToWidth = () => {
    const shell = shellRef.current;
    if (!shell || !pageSize.width || !scale) return;
    const unscaledWidth = pageSize.width / scale;
    if (unscaledWidth <= 0) return;
    pendingViewportAnchorRef.current = captureViewportAnchor();
    const nextScale = (shell.clientWidth - 28) / unscaledWidth;
    setScale(Math.min(MAX_PDF_SCALE, Math.max(0.55, Number(nextScale.toFixed(2)))));
  };

  const zoomBy = (delta: number) => {
    pendingViewportAnchorRef.current = captureViewportAnchor();
    setScale((current) => Math.min(MAX_PDF_SCALE, Math.max(0.65, Number((current + delta).toFixed(2)))));
  };

  const handleReaderScroll = () => {
    updateProgressFromReader();
  };

  const handleReaderWheel = (event: WheelEvent<HTMLDivElement>) => {
    const shell = shellRef.current;
    if (!shell) return;

    const horizontalIntent = event.shiftKey || Math.abs(event.deltaX) > Math.abs(event.deltaY);
    if (horizontalIntent) return;

    if (event.deltaY === 0 || event.ctrlKey || event.metaKey || event.altKey) return;
    const maxScrollTop = Math.max(0, shell.scrollHeight - shell.clientHeight);
    const tolerance = 2;
    const direction = event.deltaY > 0 ? 1 : -1;
    const atBoundary = direction > 0
      ? shell.scrollTop >= maxScrollTop - tolerance
      : shell.scrollTop <= tolerance;
    if (!atBoundary || pageNumber + direction < 1 || pageNumber + direction > pageCount) return;
    if (Date.now() < wheelPageTurnLockUntilRef.current) {
      return;
    }
    wheelPageTurnLockUntilRef.current = Date.now() + 280;
    goToPage(pageNumber + direction);
  };

  const handleReaderKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const shell = shellRef.current;
    if (!shell || event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
    const verticalStep = Math.max(80, Math.round(shell.clientHeight * 0.82));
    const horizontalStep = Math.max(80, Math.round(shell.clientWidth * 0.72));
    const move = (left: number, top: number) => {
      event.preventDefault();
      shell.scrollBy({ left, top, behavior: 'smooth' });
    };
    if (event.key === 'ArrowDown') move(0, verticalStep);
    else if (event.key === 'ArrowUp') move(0, -verticalStep);
    else if (event.key === 'PageDown' || event.key === ' ') move(0, verticalStep);
    else if (event.key === 'PageUp') move(0, -verticalStep);
    else if (event.key === 'ArrowRight') move(horizontalStep, 0);
    else if (event.key === 'ArrowLeft') move(-horizontalStep, 0);
    else return;
  };

  const startMousePan = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 1) return;
    const shell = shellRef.current;
    if (!shell) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    panRef.current = {
      pointerId: event.pointerId, clientX: event.clientX, clientY: event.clientY,
      scrollLeft: shell.scrollLeft, scrollTop: shell.scrollTop,
    };
    setIsPanning(true);
  };

  const moveMousePan = (event: PointerEvent<HTMLDivElement>) => {
    const pan = panRef.current;
    const shell = shellRef.current;
    if (!pan || !shell || pan.pointerId !== event.pointerId) return;
    shell.scrollLeft = pan.scrollLeft - (event.clientX - pan.clientX);
    shell.scrollTop = pan.scrollTop - (event.clientY - pan.clientY);
  };

  const endMousePan = (event: PointerEvent<HTMLDivElement>) => {
    if (panRef.current?.pointerId !== event.pointerId) return;
    panRef.current = null;
    setIsPanning(false);
  };

  const saveSelectionHighlight = async () => {
    if (!contentId || !assetId || !selectionDraft) return;
    setError('');
    try {
      if (selectionDraft.highlightId) {
        await apiClient.updatePdfHighlight(contentId, selectionDraft.highlightId, {
          note: selectionDraft.note,
          color: selectionDraft.color,
        });
      } else {
        await apiClient.createPdfHighlight(contentId, {
          asset_id: assetId,
          page_index: pageNumber - 1,
          rects: selectionDraft.rects,
          selected_text: selectionDraft.text,
          note: selectionDraft.note || undefined,
          color: selectionDraft.color,
        });
      }
      setSelectionDraft(null);
      clearNativeSelection();
      const h = await apiClient.getPdfHighlights(contentId, assetId, viewingUserId || undefined);
      setHighlights(h.items || []);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message || 'Failed to save selected highlight');
      } else {
        setError(t('pdfReader.failedToSaveSelectedHighlight'));
      }
    }
  };

  // "Add to deck" from an in-progress selection: the highlight is saved
  // first (or reused if editing an existing one) so the card always keeps a
  // reference back to a real highlight, then the save sheet opens on top.
  const handleAddToDeckFromSelection = async () => {
    if (!contentId || !assetId || !selectionDraft) return;
    setError('');
    try {
      let highlightId = selectionDraft.highlightId;
      if (!highlightId) {
        const created = await apiClient.createPdfHighlight(contentId, {
          asset_id: assetId,
          page_index: pageNumber - 1,
          rects: selectionDraft.rects,
          selected_text: selectionDraft.text,
          note: selectionDraft.note || undefined,
          color: selectionDraft.color,
        });
        highlightId = created.highlight_id;
        const h = await apiClient.getPdfHighlights(contentId, assetId, viewingUserId || undefined);
        setHighlights(h.items || []);
      }
      setAddToDeckDraft({ text: selectionDraft.text, pageIndex: pageNumber - 1, highlightId });
      setSelectionDraft(null);
      clearNativeSelection();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('pdfReader.failedToSaveSelectedHighlight'));
    }
  };

  const openHighlightEditor = (highlight: PdfHighlight) => {
    const frame = pageFrameRef.current;
    const rects = highlight.rects_json || [];
    if (!frame || rects.length === 0) return;
    const left = Math.min(...rects.map((rect) => rect.x * frame.clientWidth));
    const right = Math.max(...rects.map((rect) => (rect.x + rect.width) * frame.clientWidth));
    const top = Math.min(...rects.map((rect) => rect.y * frame.clientHeight));
    const bottom = Math.max(...rects.map((rect) => (rect.y + rect.height) * frame.clientHeight));
    clearNativeSelection();
    setSelectionDraft({
      highlightId: highlight.id,
      text: highlight.selected_text || '',
      rects,
      bounds: { top, bottom, centerX: (left + right) / 2 },
      note: highlight.note || '',
      color: highlight.color || '#ffe066',
    });
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
        setError(t('pdfReader.failedToDeleteHighlight'));
      }
    }
  };

  const pageFrameStyle = useMemo<CSSProperties | undefined>(() => {
    if (!pageSize.width || !pageSize.height) return undefined;
    const style: CSSProperties = { width: pageSize.width, height: pageSize.height };
    if (pinchPreview) {
      style.transform = `scale(${pinchPreview.scale})`;
      style.transformOrigin = `${pinchPreview.originX}% ${pinchPreview.originY}%`;
    }
    return style;
  }, [pageSize.height, pageSize.width, pinchPreview]);

  if (!canOpen) {
    return <div className="pdf-reader-empty pdf-reader-empty--error">Missing content_id query param.</div>;
  }

  return (
    <div className="pdf-reader-page">
      <section className="pdf-reader-viewer" dir="ltr">
        {/* One slim row: everything else lives in the "more" menu, the footer,
            or the edge buttons, so the page gets the screen. */}
        <header className="pdf-reader-bar">
          <button className="pdf-reader-icon-btn" onClick={returnToLibrary} title={t('pdfReader.backToLibrary')} type="button">
            <ArrowLeft size={18} className="icon-directional" />
          </button>
          <div className="pdf-reader-title" dir="auto" title={contentTitle}>{contentTitle}</div>
          <label className="pdf-reader-page-count" title={t('pdfReader.jumpToPage')}>
            <input aria-label={t('pdfReader.jumpToPage')} type="number" min={1} max={pageCount || 1} value={pageNumber} disabled={!pageCount} onChange={(event) => goToPage(Number(event.target.value || 1))} />
            <span>/ {pageCount || 0}</span>
          </label>
          {isTeacher && (
            <button
              className="pdf-reader-icon-btn"
              onClick={() => setCoReadersOpen((open) => !open)}
              title={t('pdfReader.coReaders')}
              type="button"
            >
              <Users size={18} />
            </button>
          )}
          <button
            className="pdf-reader-icon-btn"
            onClick={() => setMenuOpen((open) => !open)}
            title={t('pdfReader.more')}
            aria-expanded={menuOpen}
            type="button"
          >
            <MoreHorizontal size={18} />
          </button>
          {menuOpen && (
            <div className="pdf-reader-menu" role="menu">
              <button className="pdf-reader-icon-btn" onClick={() => zoomBy(-0.25)} disabled={scale <= 0.65} title={t('pdfReader.zoomOut')} type="button">
                <ZoomOut size={18} />
              </button>
              <div className="pdf-reader-zoom">{Math.round(scale * 100)}%</div>
              <button className="pdf-reader-icon-btn" onClick={() => zoomBy(0.25)} disabled={scale >= MAX_PDF_SCALE} title={t('pdfReader.zoomIn')} type="button">
                <ZoomIn size={18} />
              </button>
              <button className="pdf-reader-menu-item" onClick={() => { fitToWidth(); setMenuOpen(false); }} disabled={!pageSize.width} type="button">
                <ScanLine size={16} />
                <span>{t('pdfReader.fitWidth')}</span>
              </button>
            </div>
          )}
        </header>
        {loading ? (
          <div className="pdf-reader-empty">{t('pdfReader.loadingPdf')}</div>
        ) : pdfUrl ? (
          <div
            ref={shellRef}
            className={`pdf-reader-canvas-shell${isPanning ? ' pdf-reader-canvas-shell--panning' : ''}`}
            onWheel={handleReaderWheel}
            onScroll={handleReaderScroll}
            onKeyDown={handleReaderKeyDown}
            onPointerDown={startMousePan}
            onPointerMove={moveMousePan}
            onPointerUp={endMousePan}
            onPointerCancel={endMousePan}
            onTouchStart={handleTouchStart}
            onTouchMove={handleTouchMove}
            onTouchEnd={handleTouchEnd}
            onTouchCancel={handleTouchEnd}
            onClick={() => setMenuOpen(false)}
            tabIndex={0}
          >
            <div
              ref={pageFrameRef}
              className={[
                'pdf-reader-page-frame',
                pinchPreview ? 'pdf-reader-page-frame--pinching' : '',
                pageTurnDirection ? `pdf-reader-page-frame--turn-${pageTurnDirection}` : '',
              ].filter(Boolean).join(' ')}
              style={pageFrameStyle}
            >
              <canvas ref={canvasRef} className="pdf-reader-canvas" />
              <div ref={textLayerRef} className="pdf-reader-text-layer textLayer" />
              <HighlightLayer highlights={highlights} pageIndex={pageNumber - 1} onHighlightClick={openHighlightEditor} />
              {selectionDraft && (
                <HighlightPopover
                  draft={selectionDraft}
                  popoverPos={popoverPos}
                  popoverRef={popoverRef}
                  onNoteChange={(note) => setSelectionDraft((draft) => draft ? { ...draft, note } : draft)}
                  onColorChange={(nextColor) => setSelectionDraft((draft) => draft ? { ...draft, color: nextColor } : draft)}
                  onSave={saveSelectionHighlight}
                  onAddToDeck={handleAddToDeckFromSelection}
                  onCancel={() => {
                    setSelectionDraft(null);
                    clearNativeSelection();
                  }}
                />
              )}
            </div>
            {isRendering && <div className="pdf-reader-rendering">{t('pdfReader.rendering')}</div>}
          </div>
        ) : (
          <div className="pdf-reader-empty pdf-reader-empty--error">{t('pdfReader.pdfUrlUnavailable')}</div>
        )}
        {/* Page turns: edge buttons, always visible (no swipe — it fights
            text selection and panning). */}
        {pdfUrl && !loading && (
          <>
            <button
              className="pdf-reader-page-zone pdf-reader-page-zone--prev"
              onClick={() => goToPage(pageNumber - 1)}
              disabled={pageNumber <= 1}
              type="button"
              aria-label={t('pdfReader.previousPage')}
            >
              <ChevronLeft size={18} />
            </button>
            <button
              className="pdf-reader-page-zone pdf-reader-page-zone--next"
              onClick={() => goToPage(pageNumber + 1)}
              disabled={pageNumber >= pageCount}
              type="button"
              aria-label={t('pdfReader.nextPage')}
            >
              <ChevronRight size={18} />
            </button>
          </>
        )}
        {/* Same idea as the bar under a video: where you have read, and what
            you kept from it, one tap from the list. */}
        <footer className="pdf-reader-footer">
          <HeatmapBar
            data={{ bucket_count: coverageBucketCount, buckets: coverageBuckets }}
            markerRatio={resumeRatio}
            ariaLabel="PDF read coverage timeline"
            className="pdf-reader-timeline"
          />
          <div className="pdf-reader-footer-row">
            <span>{t('pdfReader.percentRead', { percent: progressPct })}</span>
            {syncStatus === 'error' && <span className="pdf-reader-inline-error">{t('pdfReader.failedToSyncReadingProgress')}</span>}
            <button className="pdf-reader-footer-link" type="button" onClick={() => setHighlightsOpen((open) => !open)}>
              <PanelRight size={14} />
              <span>
                {t('pdfReader.highlightsCount', { count: highlights.length })}
                {savedWords.length > 0 ? ` · ${t('pdfReader.wordsCount', { count: savedWords.length })}` : ''}
              </span>
            </button>
          </div>
          {error && <div className="pdf-reader-inline-error">{error}</div>}
        </footer>
      </section>

      {highlightsOpen && (
        <aside className="pdf-reader-highlights-drawer" aria-label={t('pdfReader.pdfHighlights')}>
          <header>
            <div>
              <h2>{t('pdfReader.highlights')}</h2>
              <p>{t('pdfReader.highlightsCount', { count: highlights.length })}</p>
            </div>
            <button className="pdf-reader-icon-btn" type="button" onClick={() => setHighlightsOpen(false)} title={t('pdfReader.closeHighlights')}>
              <X size={18} />
            </button>
          </header>
          <div className="pdf-reader-highlights-list">
            {savedWords.length > 0 && (
              <section className="pdf-reader-words">
                <div className="pdf-reader-words-head">
                  <h3>{t('pdfReader.wordsCount', { count: savedWords.length })}</h3>
                  <button
                    type="button"
                    className="pdf-reader-footer-link"
                    onClick={() => {
                      const deck = mostCommonDeck(savedWords);
                      if (deck) navigate(`/flashcards?deck=${encodeURIComponent(deck.deck_id)}&name=${encodeURIComponent(deck.deck_name)}`);
                    }}
                  >
                    {t('pdfReader.reviewWords')}
                  </button>
                </div>
                <div className="pdf-reader-word-chips">
                  {savedWords.map((word) => (
                    <button
                      key={word.note_id}
                      type="button"
                      className="pdf-reader-word-chip"
                      onClick={() => { if (word.page != null) goToPage(word.page + 1); }}
                      title={word.page != null ? t('pdfReader.pageNumber', { page: word.page + 1 }) : undefined}
                    >
                      <span dir="auto">{word.front}</span>
                      {word.back && <span className="pdf-reader-word-chip-back" dir="auto">{word.back}</span>}
                    </button>
                  ))}
                </div>
              </section>
            )}
            {highlightGroups.map((group) => (
              <section key={group.pageIndex} className="pdf-reader-highlight-group">
                <h3>Page {group.pageIndex + 1}</h3>
                {group.items.map((h) => (
                  <article key={h.id} className="pdf-reader-highlight-card">
                    {!h.is_mine && h.author_name && (
                      <span className="pdf-reader-highlight-author">
                        {h.is_teacher_author ? t('pdfReader.teacherHighlights') : h.author_name}
                      </span>
                    )}
                    <button type="button" onClick={() => goToPage(h.page_index + 1)}>
                      <FileText size={14} />
                      <span>{t('pdfReader.openPage')}</span>
                    </button>
                    {h.selected_text && <p>{h.selected_text}</p>}
                    {h.note && <p className="pdf-reader-highlight-note">{h.note}</p>}
                    {h.is_mine !== false && h.selected_text && (
                      <button
                        type="button"
                        className="pdf-reader-highlight-add-to-deck"
                        onClick={() => setAddToDeckDraft({ text: h.selected_text || '', pageIndex: h.page_index, highlightId: h.id })}
                      >
                        {t('pdfReader.addToDeck')}
                      </button>
                    )}
                    {h.is_mine !== false && (
                      <button className="pdf-reader-highlight-delete" onClick={() => deleteHighlight(h.id)} type="button">
                        <Trash2 size={14} />{t('pdfReader.delete')}</button>
                    )}
                  </article>
                ))}
              </section>
            ))}
            {highlights.length === 0 && <div className="pdf-reader-empty">{t('pdfReader.selectTextInThePdfToSaveAHighlight')}</div>}
          </div>
        </aside>
      )}

      {coReadersOpen && (
        <aside className="pdf-reader-highlights-drawer pdf-reader-coreaders-drawer" aria-label={t('pdfReader.coReaders')}>
          <header>
            <div>
              <h2>{t('pdfReader.coReaders')}</h2>
            </div>
            <button className="pdf-reader-icon-btn" type="button" onClick={() => setCoReadersOpen(false)} title={t('pdfReader.closeHighlights')}>
              <X size={18} />
            </button>
          </header>
          <div className="pdf-reader-highlights-list">
            <button
              type="button"
              className={`pdf-reader-coreader-row${viewingUserId === null ? ' is-active' : ''}`}
              onClick={() => setViewingUserId(null)}
            >
              <span>{t('pdfReader.viewingOwnHighlights')}</span>
            </button>
            {coReaders.map((reader) => (
              <button
                key={reader.user_id}
                type="button"
                className={`pdf-reader-coreader-row${viewingUserId === reader.user_id ? ' is-active' : ''}`}
                onClick={() => setViewingUserId(reader.user_id)}
              >
                <span>{reader.name}</span>
                <span className="pdf-reader-coreader-stats">
                  {Math.round((reader.progress_ratio || 0) * 100)}% · {Math.round((reader.total_consumed_seconds || 0) / 60)}m · {reader.highlight_count}
                </span>
              </button>
            ))}
            {coReaders.length === 0 && <div className="pdf-reader-empty">{t('pdfReader.noCoReadersYet')}</div>}
          </div>
        </aside>
      )}

      {addToDeckDraft && (
        <AddToDeckSheet
          open={!!addToDeckDraft}
          onClose={() => setAddToDeckDraft(null)}
          text={addToDeckDraft.text}
          contentId={contentId}
          assetId={assetId}
          highlightId={addToDeckDraft.highlightId}
          pageIndex={addToDeckDraft.pageIndex}
          sourceTitle={contentTitle}
          language={contentLanguage}
          onSaved={loadSavedWords}
        />
      )}
    </div>
  );
}
