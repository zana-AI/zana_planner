import { useCallback, useRef, useState, type Dispatch, type MutableRefObject, type RefObject, type SetStateAction, type TouchEvent as ReactTouchEvent } from 'react';
import type { PinchPreview, SelectionDraft, ViewportAnchor } from './types';

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
const clampRatio = (ratio: number) => clamp(ratio, 0, 1);

const getTouchDistance = (touches: ReactTouchEvent<HTMLDivElement>['touches']) => {
  if (touches.length < 2) return 0;
  const [a, b] = [touches[0], touches[1]];
  return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
};

const getTouchMidpoint = (touches: ReactTouchEvent<HTMLDivElement>['touches']) => {
  const [a, b] = [touches[0], touches[1]];
  return {
    clientX: (a.clientX + b.clientX) / 2,
    clientY: (a.clientY + b.clientY) / 2,
  };
};

interface UsePinchZoomOptions {
  scale: number;
  setScale: Dispatch<SetStateAction<number>>;
  shellRef: RefObject<HTMLDivElement>;
  pageFrameRef: RefObject<HTMLDivElement>;
  pendingViewportAnchorRef: MutableRefObject<ViewportAnchor | null>;
  setSelectionDraft: Dispatch<SetStateAction<SelectionDraft | null>>;
  clearNativeSelection: () => void;
  minScale?: number;
  maxScale?: number;
}

export function usePinchZoom({
  scale,
  setScale,
  shellRef,
  pageFrameRef,
  pendingViewportAnchorRef,
  setSelectionDraft,
  clearNativeSelection,
  minScale = 0.55,
  maxScale = 3,
}: UsePinchZoomOptions) {
  const pinchStartDistanceRef = useRef<number | null>(null);
  const pinchStartScaleRef = useRef(1);
  const pinchAnchorRef = useRef<ViewportAnchor | null>(null);
  const pinchLatestScaleRef = useRef(scale);
  const pinchLatestAnchorRef = useRef<ViewportAnchor | null>(null);
  const isPinchingRef = useRef(false);
  const [pinchPreview, setPinchPreview] = useState<PinchPreview | null>(null);

  const captureViewportAnchor = useCallback((clientX?: number, clientY?: number): ViewportAnchor | null => {
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
  }, [pageFrameRef, shellRef]);

  const handleTouchStart = useCallback((event: ReactTouchEvent<HTMLDivElement>) => {
    if (event.touches.length !== 2) return;
    const midpoint = getTouchMidpoint(event.touches);
    const anchor = captureViewportAnchor(midpoint.clientX, midpoint.clientY);
    pinchStartDistanceRef.current = getTouchDistance(event.touches);
    pinchStartScaleRef.current = scale;
    pinchLatestScaleRef.current = scale;
    pinchAnchorRef.current = anchor;
    pinchLatestAnchorRef.current = anchor;
    isPinchingRef.current = true;
    setSelectionDraft(null);
    clearNativeSelection();
    if (anchor) {
      setPinchPreview({
        scale: 1,
        originX: anchor.xRatio * 100,
        originY: anchor.yRatio * 100,
      });
    }
  }, [captureViewportAnchor, clearNativeSelection, scale, setSelectionDraft]);

  const handleTouchMove = useCallback((event: ReactTouchEvent<HTMLDivElement>) => {
    if (event.touches.length !== 2 || !pinchStartDistanceRef.current) return;
    event.preventDefault();
    const nextDistance = getTouchDistance(event.touches);
    if (!nextDistance) return;

    const midpoint = getTouchMidpoint(event.touches);
    const shell = shellRef.current;
    const shellBox = shell?.getBoundingClientRect();
    const baseAnchor = pinchAnchorRef.current || captureViewportAnchor(midpoint.clientX, midpoint.clientY);
    if (!baseAnchor) return;

    const nextScale = clamp(
      pinchStartScaleRef.current * (nextDistance / pinchStartDistanceRef.current),
      minScale,
      maxScale,
    );
    const latestAnchor = {
      ...baseAnchor,
      viewportX: shellBox ? midpoint.clientX - shellBox.left : baseAnchor.viewportX,
      viewportY: shellBox ? midpoint.clientY - shellBox.top : baseAnchor.viewportY,
    };
    pinchLatestScaleRef.current = Number(nextScale.toFixed(2));
    pinchLatestAnchorRef.current = latestAnchor;
    pendingViewportAnchorRef.current = latestAnchor;
    setPinchPreview({
      scale: nextScale / pinchStartScaleRef.current,
      originX: baseAnchor.xRatio * 100,
      originY: baseAnchor.yRatio * 100,
    });
  }, [captureViewportAnchor, maxScale, minScale, pendingViewportAnchorRef, shellRef]);

  const clearPinchPreview = useCallback(() => {
    setPinchPreview(null);
  }, []);

  const handleTouchEnd = useCallback((event: ReactTouchEvent<HTMLDivElement>) => {
    if (event.touches.length >= 2) return;
    if (pinchStartDistanceRef.current == null) {
      return;
    }
    const nextScale = pinchLatestScaleRef.current;
    pendingViewportAnchorRef.current = pinchLatestAnchorRef.current;
    pinchStartDistanceRef.current = null;
    pinchStartScaleRef.current = nextScale;
    pinchAnchorRef.current = null;
    pinchLatestAnchorRef.current = null;
    isPinchingRef.current = false;

    if (Math.abs(nextScale - scale) < 0.005) {
      clearPinchPreview();
      return;
    }
    // Let the final CSS-transform preview frame paint, then drop preview before
    // committing scale so we don't stack transform + re-rendered dimensions.
    window.requestAnimationFrame(() => {
      clearPinchPreview();
      window.requestAnimationFrame(() => {
        setScale(() => nextScale);
      });
    });
  }, [clearPinchPreview, pendingViewportAnchorRef, scale, setScale]);

  return {
    captureViewportAnchor,
    pinchPreview,
    clearPinchPreview,
    isPinchingRef,
    handleTouchStart,
    handleTouchMove,
    handleTouchEnd,
  };
}
