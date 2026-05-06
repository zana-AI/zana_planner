import { useEffect, useLayoutEffect, useMemo, useRef, useState, type TouchEvent as ReactTouchEvent } from 'react';
import { ArrowLeft, ChevronLeft, ChevronRight, FileText, Maximize2, MoreHorizontal, PanelRight, ScanLine, Trash2, X, ZoomIn, ZoomOut } from 'lucide-react';
import * as pdfjsLib from 'pdfjs-dist/legacy/build/pdf.mjs';
import pdfWorkerUrl from 'pdfjs-dist/legacy/build/pdf.worker.mjs?url';
import { useSearchParams } from 'react-router-dom';
import { apiClient, ApiError } from '../api/client';
import { HeatmapBar } from '../components/HeatmapBar';
import { getDevInitData, useTelegramWebApp } from '../hooks/useTelegramWebApp';
import type { PdfHighlight, PdfHighlightRect } from '../types';

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

const PDF_READ_BUCKET_COUNT = 120;
const PDF_READ_DWELL_SECONDS = 15;

interface SelectionDraft {
  text: string;
  rects: PdfHighlightRect[];
  // Selection's bounding box in page-relative pixels — used to position the
  // popover after measuring its actual size in a useLayoutEffect.
  bounds: { top: number; bottom: number; centerX: number };
  note: string;
  color: string;
}

interface PopoverPosition {
  left: number;
  top: number;
  placement: 'above' | 'below';
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
  const [resumeRatio, setResumeRatio] = useState(0);
  const [coverageBuckets, setCoverageBuckets] = useState<number[]>(() => Array(PDF_READ_BUCKET_COUNT).fill(0));
  const [coverageBucketCount, setCoverageBucketCount] = useState(PDF_READ_BUCKET_COUNT);
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
  const [popoverPos, setPopoverPos] = useState<PopoverPosition | null>(null);
  const [pageTurnDirection, setPageTurnDirection] = useState<'next' | 'prev' | null>(null);
  const [highlightsOpen, setHighlightsOpen] = useState(false);

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
    const boundedRatio = clampRatio(nextRatio);
    progressRatioRef.current = boundedRatio;
    setResumeRatio(boundedRatio);
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
    // Compute the selection's bounding box in page-relative pixels. Final
    // popover placement is decided in a useLayoutEffect once the popover
    // mounts and its real height is known.
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const r of rects) {
      const x1 = r.x * pageBox.width;
      const x2 = (r.x + r.width) * pageBox.width;
      const y1 = r.y * pageBox.height;
      const y2 = (r.y + r.height) * pageBox.height;
      if (x1 < minX) minX = x1;
      if (x2 > maxX) maxX = x2;
      if (y1 < minY) minY = y1;
      if (y2 > maxY) maxY = y2;
    }
    setSelectionDraft({
      text,
      rects,
      bounds: { top: minY, bottom: maxY, centerX: (minX + maxX) / 2 },
      note: '',
      color,
    });
  };

  // Position the highlight popover after it mounts so we know its real size.
  // Decides above-vs-below based on viewport space (not page bounds), centers
  // horizontally on the selection, and clamps to the visible viewport so the
  // popover never lands off-screen or covers the selected text.
  useLayoutEffect(() => {
    if (!selectionDraft) {
      setPopoverPos(null);
      return;
    }
    const popover = popoverRef.current;
    const pageFrame = pageFrameRef.current;
    const shell = shellRef.current;
    if (!popover || !pageFrame || !shell) return;

    const measure = () => {
      const popoverBox = popover.getBoundingClientRect();
      const pageBox = pageFrame.getBoundingClientRect();
      const shellBox = shell.getBoundingClientRect();
      const margin = 8;
      const gap = 6;

      const selTopClient = pageBox.top + selectionDraft.bounds.top;
      const selBottomClient = pageBox.top + selectionDraft.bounds.bottom;
      const selCenterClient = pageBox.left + selectionDraft.bounds.centerX;

      const spaceAbove = selTopClient - shellBox.top;
      const spaceBelow = shellBox.bottom - selBottomClient;
      const fitsAbove = spaceAbove >= popoverBox.height + gap + margin;
      const placement: 'above' | 'below' = fitsAbove ? 'above' : 'below';

      const topClient = placement === 'above'
        ? selTopClient - popoverBox.height - gap
        : selBottomClient + gap;

      let leftClient = selCenterClient - popoverBox.width / 2;
      const minLeft = shellBox.left + margin;
      const maxLeft = shellBox.right - popoverBox.width - margin;
      if (maxLeft >= minLeft) {
        leftClient = Math.max(minLeft, Math.min(maxLeft, leftClient));
      } else {
        leftClient = minLeft;
      }

      setPopoverPos({
        left: leftClient - pageBox.left,
        top: topClient - pageBox.top,
        placement,
      });
    };

    measure();
  }, [selectionDraft, scale, pageNumber]);

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
    if (!loading && pageCount > 0) {
      scheduleProgressSync(resumeRatio);
    }
  }, [resumeRatio, loading, pageCount]);

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
      isImageDecoderSupported: false,
      isOffscreenCanvasSupported: false,
      useWasm: false,
      useWorkerFetch: false,
      useSystemFonts: true,
      // Required for non-Latin scripts (Persian/Arabic/CJK). Without these,
      // CID-font PDFs render glyphs but selection/copy yields garbled text.
      // Files are copied to dist/pdfjs/ by vite-plugin-static-copy.
      cMapUrl: `${import.meta.env.BASE_URL}pdfjs/cmaps/`,
      cMapPacked: true,
      standardFontDataUrl: `${import.meta.env.BASE_URL}pdfjs/standard_fonts/`,
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

        // Cap canvas backing-store at a fixed pixel budget so high-DPR phones
        // get sharp text on small pages but very large/zoomed pages don't OOM.
        const MAX_CANVAS_PIXELS = 16_000_000;
        const targetDpr = window.devicePixelRatio || 1;
        const baseArea = viewport.width * viewport.height;
        const budgetScale = baseArea > 0 ? Math.sqrt(MAX_CANVAS_PIXELS / baseArea) : 3;
        const outputScale = Math.max(1, Math.min(targetDpr, 3, budgetScale));
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
        setError('Failed to sync read coverage');
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
        rendering ||
        pinchStartDistanceRef.current != null ||
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
  }, [coverageBucketCount, loading, pageCount, pageNumber, pageTurnDirection, pdfDoc, rendering, scale]);

  const progressPct = useMemo(() => Math.round(progressRatio * 100), [progressRatio]);
  const expiresLabel = useMemo(() => {
    if (!expiresAt) return '';
    const d = new Date(expiresAt);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleTimeString();
  }, [expiresAt]);
  const syncLabel = useMemo(() => {
    if (saving || syncStatus === 'saving') return 'Saving position...';
    if (syncStatus === 'pending') return 'Position queued';
    if (syncStatus === 'error') return 'Position sync failed';
    if (syncStatus === 'saved') return `Position saved at ${Math.round(resumeRatio * 100)}%`;
    return 'Tracking read coverage';
  }, [resumeRatio, saving, syncStatus]);
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
    setResumeRatio(nextRatio);
    void syncProgress(nextRatio);
  };

  const turnFullscreenPage = (direction: -1 | 1) => {
    revealFullscreenControls();
    goToPage(pageNumber + direction);
  };

  const fitToWidth = () => {
    const shell = shellRef.current;
    if (!shell || !pageSize.width || !scale) return;
    const unscaledWidth = pageSize.width / scale;
    if (unscaledWidth <= 0) return;
    pendingViewportAnchorRef.current = captureViewportAnchor();
    const nextScale = (shell.clientWidth - 28) / unscaledWidth;
    setScale(Math.min(3, Math.max(0.55, Number(nextScale.toFixed(2)))));
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
    return <div className="pdf-reader-empty pdf-reader-empty--error">Missing content_id query param.</div>;
  }

  return (
    <div className={`pdf-reader-page${isFullscreen ? ' pdf-reader-page--fullscreen' : ''}${isFullscreen && !fullscreenControlsVisible ? ' pdf-reader-page--chrome-hidden' : ''}`}>
      <section className="pdf-reader-viewer">
        <div className="pdf-reader-toolbar">
          <button className="pdf-reader-icon-btn" onClick={() => window.history.back()} title="Back to library" type="button">
            <ArrowLeft size={18} />
          </button>
          <button className="pdf-reader-icon-btn" onClick={() => goToPage(pageNumber - 1)} disabled={!pageCount || pageNumber <= 1} title="Previous page" type="button">
            <ChevronLeft size={18} />
          </button>
          <label className="pdf-reader-page-count" title="Jump to page">
            <input type="number" min={1} max={pageCount || 1} value={pageNumber} disabled={!pageCount} onChange={(event) => goToPage(Number(event.target.value || 1))} />
            <span>/ {pageCount || 0}</span>
          </label>
          <button className="pdf-reader-icon-btn" onClick={() => goToPage(pageNumber + 1)} disabled={!pageCount || pageNumber >= pageCount} title="Next page" type="button">
            <ChevronRight size={18} />
          </button>
          <div className="pdf-reader-toolbar-spacer" />
          <button className="pdf-reader-icon-btn" onClick={() => zoomBy(-0.15)} disabled={scale <= 0.65} title="Zoom out" type="button">
            <ZoomOut size={18} />
          </button>
          <div className="pdf-reader-zoom">{Math.round(scale * 100)}%</div>
          <button className="pdf-reader-icon-btn" onClick={() => zoomBy(0.15)} disabled={scale >= 3} title="Zoom in" type="button">
            <ZoomIn size={18} />
          </button>
          <button className="pdf-reader-icon-btn" onClick={fitToWidth} disabled={!pageSize.width} title="Fit width" type="button">
            <ScanLine size={18} />
          </button>
          <button className="pdf-reader-icon-btn pdf-reader-icon-btn--with-badge" onClick={() => setHighlightsOpen((open) => !open)} title="Highlights" type="button">
            <PanelRight size={18} />
            {highlights.length > 0 && <span>{highlights.length}</span>}
          </button>
          <button className="pdf-reader-icon-btn" onClick={isFullscreen ? exitFullscreen : enterFullscreen} title={isFullscreen ? 'Exit reader mode' : 'Reader fullscreen'} type="button">
            {isFullscreen ? <X size={18} /> : <Maximize2 size={18} />}
          </button>
          <button className="pdf-reader-icon-btn" title="More" type="button">
            <MoreHorizontal size={18} />
          </button>
        </div>
        <div className="pdf-reader-timeline-panel">
          <HeatmapBar
            data={{ bucket_count: coverageBucketCount, buckets: coverageBuckets }}
            markerRatio={resumeRatio}
            ariaLabel="PDF read coverage timeline"
            className="pdf-reader-timeline"
          />
          <div className="pdf-reader-timeline-meta">
            <span>{progressPct}% read</span>
            <span>{syncLabel}</span>
          </div>
          {error && <div className="pdf-reader-inline-error">{error}</div>}
        </div>
        {loading ? (
          <div className="pdf-reader-empty">Loading PDF...</div>
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
                  ref={popoverRef}
                  className={[
                    'pdf-reader-selection-popover',
                    popoverPos ? `pdf-reader-selection-popover--${popoverPos.placement}` : '',
                  ].filter(Boolean).join(' ')}
                  style={{
                    left: popoverPos ? popoverPos.left : 0,
                    top: popoverPos ? popoverPos.top : 0,
                    visibility: popoverPos ? 'visible' : 'hidden',
                  }}
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
          <div className="pdf-reader-empty pdf-reader-empty--error">PDF URL unavailable.</div>
        )}
      </section>

      {highlightsOpen && (
        <aside className="pdf-reader-highlights-drawer" aria-label="PDF highlights">
          <header>
            <div>
              <h2>Highlights</h2>
              <p>{highlights.length} saved {expiresLabel ? `- URL expires ${expiresLabel}` : ''}</p>
            </div>
            <button className="pdf-reader-icon-btn" type="button" onClick={() => setHighlightsOpen(false)} title="Close highlights">
              <X size={18} />
            </button>
          </header>
          <div className="pdf-reader-highlights-list">
            {highlightGroups.map((group) => (
              <section key={group.pageIndex} className="pdf-reader-highlight-group">
                <h3>Page {group.pageIndex + 1}</h3>
                {group.items.map((h) => (
                  <article key={h.id} className="pdf-reader-highlight-card">
                    <button type="button" onClick={() => goToPage(h.page_index + 1)}>
                      <FileText size={14} />
                      <span>Open page</span>
                    </button>
                    {h.selected_text && <p>{h.selected_text}</p>}
                    {h.note && <p className="pdf-reader-highlight-note">{h.note}</p>}
                    <button className="pdf-reader-highlight-delete" onClick={() => deleteHighlight(h.id)} type="button">
                      <Trash2 size={14} />
                      Delete
                    </button>
                  </article>
                ))}
              </section>
            ))}
            {highlights.length === 0 && <div className="pdf-reader-empty">Select text in the PDF to save a highlight.</div>}
          </div>
        </aside>
      )}
    </div>
  );
}
