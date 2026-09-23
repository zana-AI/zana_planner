import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient, ApiError } from '../../api/client';
import { BottomSheet } from '../../components/ui/BottomSheet';

const LAST_DECK_KEY = 'xaana:pdfReader:lastDeckPath';

// Root deck names the video player already uses. A different spelling makes
// a second, unrelated root ("FR" next to "French"), so keep these in step.
const LANGUAGE_DECK: Record<string, string> = { fr: 'French', en: 'English', fa: 'Persian' };

interface AddToDeckSheetProps {
  open: boolean;
  onClose: () => void;
  /** The selected/highlighted text — the card's front. */
  text: string;
  /** Text around the selection on its page, for the card builder only. */
  passage?: string;
  contentId: string;
  assetId: string;
  highlightId?: string;
  pageIndex: number;
  sourceTitle?: string;
  /** ISO-639-1 language of the source, when known (drives the lookup + default deck). */
  language?: string;
  onSaved?: () => void;
}

interface BuiltCard {
  headword?: string;
  grammar?: string;
  sentence?: string;
  sentence_translation?: string;
  usage_note?: string;
}

function defaultDeckPath(language?: string): string {
  try {
    const stored = localStorage.getItem(LAST_DECK_KEY);
    if (stored) return stored;
  } catch {
    /* storage unavailable: fall through to the language deck */
  }
  const code = (language || 'fr').toLowerCase().split('-')[0];
  return LANGUAGE_DECK[code] || code.toUpperCase();
}

/**
 * The PDF reader's save sheet. Shows the card as it will be stored: a quick
 * gloss appears at once, then one model call fills in the headword (the whole
 * idiom when the word belongs to one), grammar, and the sentence with its
 * translation — the same card the video player builds. The learner can edit
 * the meaning before saving; a hand edit is never overwritten.
 */
export function AddToDeckSheet({
  open,
  onClose,
  text,
  passage,
  contentId,
  assetId,
  highlightId,
  pageIndex,
  sourceTitle,
  language,
  onSaved,
}: AddToDeckSheetProps) {
  const { t, i18n } = useTranslation();
  const [back, setBack] = useState('');
  const [card, setCard] = useState<BuiltCard>({});
  const [deckPath, setDeckPath] = useState(() => defaultDeckPath(language));
  const [building, setBuilding] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const requestRef = useRef(0);
  const backEditedRef = useRef(false);

  const source = (language || 'fr').toLowerCase().split('-')[0];
  const uiLanguage = (i18n.language || 'en').toLowerCase().split('-')[0];
  const target = uiLanguage === 'fa' && source !== 'fa' ? 'fa' : 'en';

  useEffect(() => {
    if (!open) return;
    setBack('');
    setCard({});
    setSaved(false);
    setError('');
    setDeckPath(defaultDeckPath(language));
    backEditedRef.current = false;
    const term = text.trim();
    if (!term) return;
    const requestId = ++requestRef.current;
    setBuilding(true);
    const context = passage || term;
    apiClient
      // The quick gloss endpoint caps context at 500 characters.
      .lookupFlashcardWord({ word: term, context: context.slice(0, 480), source_language: source, target_language: target })
      .then((data) => {
        if (requestId !== requestRef.current || backEditedRef.current) return;
        if (data.available && data.translation) setBack((current) => current || data.translation || '');
      })
      .catch(() => undefined);
    apiClient
      .enrichFlashcard({ word: term, context, source_language: source, target_language: target })
      .then((data) => {
        if (requestId !== requestRef.current || !data.available) return;
        setCard(data);
        if (!backEditedRef.current && data.translation) setBack(data.translation);
      })
      .catch(() => undefined)
      .finally(() => {
        if (requestId === requestRef.current) setBuilding(false);
      });
  }, [open, text, passage, language, source, target]);

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
          headword: card.headword,
          grammar: card.grammar,
          example: card.sentence,
          source_sentence: card.sentence,
          sentence_translation: card.sentence_translation,
          usage_note: card.usage_note,
          translation_language: target,
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

  const headwordLine = [card.headword, card.grammar].filter(Boolean).join(' · ');

  return (
    <BottomSheet open={open} onClose={onClose} title={t('pdfReader.addToDeck')}>
      <div className="add-to-deck-sheet">
        <div>
          <div className="add-to-deck-front" dir="auto">{text}</div>
          {headwordLine && <div className="add-to-deck-headword" dir="auto">{headwordLine}</div>}
        </div>
        <label className="add-to-deck-field">
          <span>{t('pdfReader.translation')}</span>
          <textarea
            value={back}
            onChange={(event) => {
              backEditedRef.current = true;
              setBack(event.target.value);
            }}
            placeholder={building ? t('pdfReader.translating') : t('pdfReader.translationOptional')}
            rows={2}
            dir="auto"
          />
        </label>
        {card.sentence && (
          <div className="add-to-deck-sentence">
            <p dir="auto">{card.sentence}</p>
            {card.sentence_translation && <p dir="auto">{card.sentence_translation}</p>}
          </div>
        )}
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
