import { useEffect, useState, type MutableRefObject } from 'react';
import * as pdfjsLib from 'pdfjs-dist/legacy/build/pdf.mjs';
import pdfWorkerUrl from 'pdfjs-dist/legacy/build/pdf.worker.mjs?url';

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

interface UsePdfDocumentOptions {
  pdfBytes: Uint8Array | null;
  resumeRatioRef: MutableRefObject<number>;
  pendingScrollFractionRef: MutableRefObject<number | null>;
  setError: (message: string) => void;
}

const clampRatio = (ratio: number) => Math.max(0, Math.min(1, ratio));

export function usePdfDocument({
  pdfBytes,
  resumeRatioRef,
  pendingScrollFractionRef,
  setError,
}: UsePdfDocumentOptions) {
  const [pdfDoc, setPdfDoc] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [documentRendering, setDocumentRendering] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let loadedDoc: pdfjsLib.PDFDocumentProxy | null = null;
    if (!pdfBytes) {
      setPdfDoc(null);
      setPageCount(0);
      setPageNumber(1);
      return;
    }

    setDocumentRendering(true);
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
          setDocumentRendering(false);
        }
      });

    return () => {
      cancelled = true;
      loadedDoc?.destroy();
    };
  }, [pdfBytes, pendingScrollFractionRef, resumeRatioRef, setError]);

  return {
    pdfDoc,
    pageCount,
    pageNumber,
    setPageNumber,
    documentRendering,
  };
}

export type PdfDocumentProxy = pdfjsLib.PDFDocumentProxy;
export type RenderTask = pdfjsLib.RenderTask;
export type TextLayer = pdfjsLib.TextLayer;
