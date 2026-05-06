import type { Ref } from 'react';
import type { PopoverPosition, SelectionDraft } from './types';

interface HighlightPopoverProps {
  draft: SelectionDraft;
  popoverPos: PopoverPosition | null;
  popoverRef: Ref<HTMLDivElement>;
  onNoteChange: (note: string) => void;
  onColorChange: (color: string) => void;
  onSave: () => void;
  onCancel: () => void;
}

export function HighlightPopover({
  draft,
  popoverPos,
  popoverRef,
  onNoteChange,
  onColorChange,
  onSave,
  onCancel,
}: HighlightPopoverProps) {
  return (
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
      <div className="pdf-reader-selection-text">{draft.text}</div>
      <textarea
        value={draft.note}
        onChange={(event) => onNoteChange(event.target.value)}
        placeholder="Add note (optional)"
        rows={2}
      />
      <div className="pdf-reader-selection-actions">
        <input
          aria-label="Highlight color"
          type="color"
          value={draft.color}
          onChange={(event) => onColorChange(event.target.value)}
        />
        <button type="button" onClick={onSave}>
          Highlight
        </button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}
