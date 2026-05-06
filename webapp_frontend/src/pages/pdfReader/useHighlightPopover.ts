import { useLayoutEffect, useState, type RefObject } from 'react';
import type { PopoverPosition, SelectionDraft } from './types';

interface UseHighlightPopoverOptions {
  selectionDraft: SelectionDraft | null;
  popoverRef: RefObject<HTMLDivElement>;
  pageFrameRef: RefObject<HTMLDivElement>;
  shellRef: RefObject<HTMLDivElement>;
  scale: number;
  pageNumber: number;
}

export function useHighlightPopover({
  selectionDraft,
  popoverRef,
  pageFrameRef,
  shellRef,
  scale,
  pageNumber,
}: UseHighlightPopoverOptions) {
  const [popoverPos, setPopoverPos] = useState<PopoverPosition | null>(null);

  useLayoutEffect(() => {
    if (!selectionDraft) {
      setPopoverPos(null);
      return;
    }
    const popover = popoverRef.current;
    const pageFrame = pageFrameRef.current;
    const shell = shellRef.current;
    if (!popover || !pageFrame || !shell) return;

    const popoverBox = popover.getBoundingClientRect();
    const pageBox = pageFrame.getBoundingClientRect();
    const shellBox = shell.getBoundingClientRect();
    const margin = 8;
    const gap = 6;

    const selTopClient = pageBox.top + selectionDraft.bounds.top;
    const selBottomClient = pageBox.top + selectionDraft.bounds.bottom;
    const selCenterClient = pageBox.left + selectionDraft.bounds.centerX;

    const spaceAbove = selTopClient - shellBox.top;
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
  }, [selectionDraft, popoverRef, pageFrameRef, shellRef, scale, pageNumber]);

  return popoverPos;
}
