import { useCallback, useEffect, useState, type RefObject } from 'react';
import type { SelectionClientRect, SelectionDraft, TextDirection } from './types';

const clampRatio = (ratio: number) => Math.max(0, Math.min(1, ratio));

export const clearNativeSelection = () => {
  const selection = window.getSelection();
  if (selection) {
    selection.removeAllRanges();
  }
};

const getElementTextDirection = (element: Element | null): TextDirection | null => {
  if (!(element instanceof HTMLElement)) return null;
  if (element.dir === 'rtl' || element.getAttribute('dir') === 'rtl') return 'rtl';
  if (element.dir === 'ltr' || element.getAttribute('dir') === 'ltr') return 'ltr';
  return null;
};

export const detectTextLayerDirection = (textLayer: HTMLElement): TextDirection => {
  let rtlWeight = 0;
  let ltrWeight = 0;
  textLayer.querySelectorAll<HTMLElement>('span[dir]').forEach((span) => {
    const direction = getElementTextDirection(span);
    if (!direction) return;
    const weight = Math.max(1, span.textContent?.trim().length || 0);
    if (direction === 'rtl') {
      rtlWeight += weight;
    } else {
      ltrWeight += weight;
    }
  });
  return rtlWeight > ltrWeight ? 'rtl' : 'ltr';
};

const getSelectionRectDirection = (
  rect: DOMRect,
  textLayer: HTMLElement,
  fallbackDirection: TextDirection,
): TextDirection => {
  const centerX = Math.max(0, Math.min(window.innerWidth - 1, (rect.left + rect.right) / 2));
  const centerY = Math.max(0, Math.min(window.innerHeight - 1, (rect.top + rect.bottom) / 2));
  const pointElement = document
    .elementsFromPoint(centerX, centerY)
    .find((element) => textLayer.contains(element));
  const pointDirection = getElementTextDirection(pointElement?.closest('[dir]') || null);
  if (pointDirection) return pointDirection;

  let bestDirection: TextDirection | null = null;
  let bestOverlap = 0;
  textLayer.querySelectorAll<HTMLElement>('span[dir]').forEach((span) => {
    const direction = getElementTextDirection(span);
    if (!direction) return;
    const spanBox = span.getBoundingClientRect();
    const overlapX = Math.max(0, Math.min(rect.right, spanBox.right) - Math.max(rect.left, spanBox.left));
    const overlapY = Math.max(0, Math.min(rect.bottom, spanBox.bottom) - Math.max(rect.top, spanBox.top));
    const overlap = overlapX * overlapY;
    if (overlap > bestOverlap) {
      bestOverlap = overlap;
      bestDirection = direction;
    }
  });
  return bestDirection || fallbackDirection;
};

const sortAndMergeSelectionRects = (rects: SelectionClientRect[], pageDirection: TextDirection) => {
  const sorted = [...rects].sort((a, b) => {
    const topDelta = a.top - b.top;
    if (Math.abs(topDelta) > 2) return topDelta;
    return pageDirection === 'rtl' ? b.right - a.right : a.left - b.left;
  });
  const lines: SelectionClientRect[][] = [];

  for (const rect of sorted) {
    const rectHeight = rect.bottom - rect.top;
    const rectCenterY = (rect.top + rect.bottom) / 2;
    const line = lines.find((candidate) => {
      const lineTop = Math.min(...candidate.map((item) => item.top));
      const lineBottom = Math.max(...candidate.map((item) => item.bottom));
      const lineHeight = lineBottom - lineTop;
      const lineCenterY = (lineTop + lineBottom) / 2;
      const overlap = Math.min(rect.bottom, lineBottom) - Math.max(rect.top, lineTop);
      return (
        Math.abs(rectCenterY - lineCenterY) <= Math.max(4, Math.min(rectHeight, lineHeight) * 0.75) ||
        overlap >= Math.min(rectHeight, lineHeight) * 0.35
      );
    });
    if (line) {
      line.push(rect);
    } else {
      lines.push([rect]);
    }
  }

  return lines.map((line) => {
    const directionWeights = line.reduce(
      (weights, rect) => {
        weights[rect.direction] += rect.right - rect.left;
        return weights;
      },
      { ltr: 0, rtl: 0 },
    );
    const lineDirection: TextDirection = directionWeights.rtl > directionWeights.ltr ? 'rtl' : 'ltr';
    // Collapse the entire line into one bounding-box rectangle.
    // This avoids multiple fragmented boxes per line, which is especially
    // problematic for Arabic/Persian PDFs where characters are tightly joined
    // but pdf.js emits many small per-glyph rects.
    return {
      left: Math.min(...line.map((r) => r.left)),
      right: Math.max(...line.map((r) => r.right)),
      top: Math.min(...line.map((r) => r.top)),
      bottom: Math.max(...line.map((r) => r.bottom)),
      direction: lineDirection,
    };
  });
};

interface UseTextSelectionOptions {
  pageFrameRef: RefObject<HTMLDivElement>;
  textLayerRef: RefObject<HTMLDivElement>;
  pageNumber: number;
  scale: number;
  color: string;
}

export function useTextSelection({
  pageFrameRef,
  textLayerRef,
  pageNumber,
  scale,
  color,
}: UseTextSelectionOptions) {
  const [selectionDraft, setSelectionDraft] = useState<SelectionDraft | null>(null);

  const captureTextSelection = useCallback(() => {
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
    const pageDirection = textLayer.dir === 'rtl' ? 'rtl' : 'ltr';
    const rangeRects = Array.from(selection.getRangeAt(0).getClientRects());
    const selectionRects = rangeRects
      .map((rect) => {
        const left = Math.max(rect.left, pageBox.left);
        const right = Math.min(rect.right, pageBox.right);
        const top = Math.max(rect.top, pageBox.top);
        const bottom = Math.min(rect.bottom, pageBox.bottom);
        if (right - left < 2 || bottom - top < 2) return null;
        return {
          left,
          right,
          top,
          bottom,
          direction: getSelectionRectDirection(rect, textLayer, pageDirection),
        };
      })
      .filter((rect): rect is SelectionClientRect => Boolean(rect));

    const rects = sortAndMergeSelectionRects(selectionRects, pageDirection).map((rect) => ({
      x: clampRatio((rect.left - pageBox.left) / pageBox.width),
      y: clampRatio((rect.top - pageBox.top) / pageBox.height),
      width: clampRatio((rect.right - rect.left) / pageBox.width),
      height: clampRatio((rect.bottom - rect.top) / pageBox.height),
    }));

    if (rects.length === 0) return;
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
  }, [color, pageFrameRef, textLayerRef]);

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
  }, [captureTextSelection, pageNumber, scale]);

  return { selectionDraft, setSelectionDraft, clearNativeSelection };
}
