import { useTranslation } from 'react-i18next';
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
  onAddToDeck?: () => void;
}

export function HighlightPopover({
  draft,
  popoverPos,
  popoverRef,
  onNoteChange,
  onColorChange,
  onSave,
  onCancel,
  onAddToDeck,
}: HighlightPopoverProps) {
  const { t } = useTranslation();
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
        placeholder={t('pdfReader.addNoteOptional')}
        rows={2}
      />
      <div className="pdf-reader-selection-actions">
        <input
          aria-label={t('pdfReader.highlightColor')}
          type="color"
          value={draft.color}
          onChange={(event) => onColorChange(event.target.value)}
        />
        <button type="button" onClick={onSave}>{draft.highlightId ? t('pdfReader.saveChanges') : t('pdfReader.highlight')}</button>
        {onAddToDeck && draft.text.trim() && (
          <button type="button" onClick={onAddToDeck}>{t('pdfReader.addToDeck')}</button>
        )}
        <button type="button" onClick={onCancel}>{t('pdfReader.cancel')}</button>
      </div>
    </div>
  );
}
