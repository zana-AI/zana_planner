import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient, ApiError } from '../../api/client';
import { BottomSheet } from '../../components/ui/BottomSheet';

const LAST_DECK_KEY = 'xaana:pdfReader:lastDeckPath';

interface AddToDeckSheetProps {
  open: boolean;
  onClose: () => void;
  /** The selected/highlighted text — the card's front. */
  text: string;
  contentId: string;
  assetId: string;
  highlightId?: string;
  pageIndex: number;
  sourceTitle?: string;
  /** ISO-639-1 language of the source, when known (drives the lookup + default deck). */
  language?: string;
  onSaved?: () => void;
}

function defaultDeckPath(language?: string): string {
  const stored = (() => {
    try {
      return localStorage.getItem(LAST_DECK_KEY) || '';
    } catch {
      return '';
    }
  })();
  if (stored) return stored;
  const label = language ? language.toUpperCase() : 'French';
  return label;
}

/**
 * One save sheet shared by the PDF reader and (eventually) the video player:
 * translate the selection, let the learner edit the back side, pick a deck
 * (defaulting to one deck per language, not one per content item — see the
 * UX discussion this was born from), and attach a reference back to where
 * the word came from.
 */
export function AddToDeckSheet({
  open,
  onClose,
  text,
  contentId,
  assetId,
  highlightId,
  pageIndex,
  sourceTitle,
  language,
  onSaved,
}: AddToDeckSheetProps) {
  const { t } = useTranslation();
  const [back, setBack] = useState('');
  const [deckPath, setDeckPath] = useState(() => defaultDeckPath(language));
  const [loadingTranslation, setLoadingTranslation] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const lookupRequestRef = useRef(0);

  useEffect(() => {
    if (!open) return;
    setBack('');
    setSaved(false);
    setError('');
    setDeckPath(defaultDeckPath(language));
    if (!text.trim()) return;
    const requestId = ++lookupRequestRef.current;
    setLoadingTranslation(true);
    apiClient
      .lookupFlashcardWord({ word: text.trim(), source_language: language || 'fr', target_language: 'fa' })
      .then((data) => {
        if (requestId !== lookupRequestRef.current) return;
        if (data.available && data.translation) setBack(data.translation);
      })
      .catch(() => {
        /* translation is a convenience; an empty back field is still editable */
      })
      .finally(() => {
        if (requestId === lookupRequestRef.current) setLoadingTranslation(false);
      });
  }, [open, text, language]);

  const save = async () => {
    if (!text.trim() || !deckPath.trim()) return;
    setSaving(true);
    setError('');
    try {
      await apiClient.createFlashcardNote({
        deck_path: deckPath.trim(),
        note_type: 'vocab',
        fields: {
          front: text.trim(),
          back: back.trim() || undefined,
          source_page: String(pageIndex + 1),
          source_title: sourceTitle,
        },
        references: [
          {
            kind: 'highlight',
            content_id: contentId,
            asset_id: assetId,
            highlight_id: highlightId,
            locator: { page: pageIndex },
            label: sourceTitle ? `${sourceTitle} · p.${pageIndex + 1}` : `p.${pageIndex + 1}`,
          },
        ],
      });
      try {
        localStorage.setItem(LAST_DECK_KEY, deckPath.trim());
      } catch {
        /* best-effort */
      }
      setSaved(true);
      onSaved?.();
      window.setTimeout(onClose, 900);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('pdfReader.failedToSaveCard'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet open={open} onClose={onClose} title={t('pdfReader.addToDeck')}>
      <div className="add-to-deck-sheet">
        <div className="add-to-deck-front" dir="auto">{text}</div>
        <label className="add-to-deck-field">
          <span>{t('pdfReader.translation')}</span>
          <textarea
            value={back}
            onChange={(event) => setBack(event.target.value)}
            placeholder={loadingTranslation ? t('pdfReader.translating') : t('pdfReader.translationOptional')}
            rows={2}
            dir="auto"
          />
        </label>
        <label className="add-to-deck-field">
          <span>{t('pdfReader.deck')}</span>
          <input
            type="text"
            value={deckPath}
            onChange={(event) => setDeckPath(event.target.value)}
            placeholder="French"
          />
        </label>
        {error && <div className="pdf-reader-inline-error">{error}</div>}
        <div className="add-to-deck-actions">
          <button type="button" className="btn btn-primary" onClick={save} disabled={saving || !text.trim() || !deckPath.trim()}>
            {saved ? t('pdfReader.saved') : saving ? t('pdfReader.saving') : t('pdfReader.saveCard')}
          </button>
        </div>
      </div>
    </BottomSheet>
  );
}
