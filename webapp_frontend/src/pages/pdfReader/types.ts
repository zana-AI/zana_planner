import type { PdfHighlightRect } from '../../types';

export interface SelectionDraft {
  text: string;
  rects: PdfHighlightRect[];
  // Selection bounds in page-relative pixels. The popover hook measures the
  // real popover size before deciding above/below placement.
  bounds: { top: number; bottom: number; centerX: number };
  note: string;
  color: string;
}

export interface PopoverPosition {
  left: number;
  top: number;
  placement: 'above' | 'below';
}

export interface ViewportAnchor {
  xRatio: number;
  yRatio: number;
  viewportX: number;
  viewportY: number;
}

export interface PinchPreview {
  scale: number;
  originX: number;
  originY: number;
}

export type TextDirection = 'ltr' | 'rtl';

export interface SelectionClientRect {
  left: number;
  right: number;
  top: number;
  bottom: number;
  direction: TextDirection;
}
