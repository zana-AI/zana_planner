import { useTranslation } from 'react-i18next';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { apiClient } from '../api/client';
import { formatNumber } from '../i18n/format';
import type {
  FlashcardCounts,
  FlashcardDeck,
  FlashcardDeckSelection,
  FlashcardFields,
  FlashcardNote,
  FlashcardQueueCard,
  FlashcardRating,
} from '../types';
import './FlashcardsPage.css';

/** Study content keeps the language of its deck; controls use the app locale. */
/**
 * Cards mined from video know the second at which their word is spoken, so the
 * answer side can offer the clip. The link points at our own watch page rather
 * than youtube.com: it keeps the viewer inside the app, and that page already
 * knows how to seek and to record watch progress.
 */
function currentAppPath() {
  if (typeof window === 'undefined') return '/my-contents';
  return `${window.location.pathname}${window.location.search}`;
}

function videoMomentUrl(fields: FlashcardFields, language: string): string | null {
  const url = typeof fields.source_url === 'string' ? fields.source_url : '';
  const start = typeof fields.source_start === 'number' ? fields.source_start : NaN;
  const match = url.match(/[?&]v=([\w-]{6,20})/);
  if (!match || !Number.isFinite(start)) return null;
  // Start a beat early: seeking exactly on the cue clips the first syllable.
  const at = Math.max(0, Math.floor(start) - 1);
  // The word travels too: the player highlights it inside the spoken line.
  const word = encodeURIComponent(typeof fields.original_front === 'string' ? fields.original_front : fields.front || '');
  return `/youtube-watch?video_id=${match[1]}&start=${at}&word=${word}&lang=${encodeURIComponent(language)}&return_to=${encodeURIComponent(currentAppPath())}`;
}

function pdfSourceUrl(card: FlashcardQueueCard): string | null {
  const reference = card.references.find((item) => item.content_id && typeof item.locator?.page === 'number');
  if (!reference?.content_id) return null;
  const page = Number(reference.locator.page);
  return `/pdf-reader?content_id=${encodeURIComponent(reference.content_id)}${Number.isFinite(page) ? `&page=${Math.max(1, Math.floor(page))}` : ''}&return_to=${encodeURIComponent(currentAppPath())}`;
}

function formatMoment(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

const RATINGS: Array<{ value: FlashcardRating; tone: 'again' | 'hard' | 'good' | 'easy' }> = [
  { value: 1, tone: 'again' },
  { value: 2, tone: 'hard' },
  { value: 3, tone: 'good' },
  { value: 4, tone: 'easy' },
];

/**
 * Render the `**bold**` / `*italic*` that authored definitions carry.
 *
 * Deliberately builds React nodes rather than setting innerHTML: the text is
 * user-authored, so injecting it as markup would be an XSS hole.
 */
function renderRichText(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  // Imported cards contain both Markdown emphasis and legacy HTML emphasis
  // from the Zotero/vocabulary pipeline. Render both without innerHTML.
  const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*|<\s*(?:strong|b|em|i)\s*>[\s\S]*?<\s*\/(?:strong|b|em|i)\s*>|<\s*br\s*\/?>)/gi;
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const token = match[0];
    if (token.startsWith('**')) {
      nodes.push(<strong key={key++}>{token.slice(2, -2)}</strong>);
    } else if (/^<\s*br\s*\/?>$/i.test(token)) {
      nodes.push(<br key={key++} />);
    } else if (/^<\s*(?:strong|b)\b/i.test(token)) {
      nodes.push(<strong key={key++}>{renderRichText(token.replace(/^<\s*(?:strong|b)\s*>|<\s*\/\s*(?:strong|b)\s*>$/gi, ''))}</strong>);
    } else if (/^<\s*(?:em|i)\b/i.test(token)) {
      nodes.push(<em key={key++}>{renderRichText(token.replace(/^<\s*(?:em|i)\s*>|<\s*\/\s*(?:em|i)\s*>$/gi, ''))}</em>);
    } else {
      nodes.push(<em key={key++}>{token.slice(1, -1)}</em>);
    }
    last = match.index + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

/** Bold the first occurrence of the card's word inside its sentence. */
function boldTerm(sentence: string, term: string): string {
  const clean = term.trim();
  if (!clean) return sentence;
  const escaped = clean.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return sentence.replace(new RegExp(escaped, 'i'), (match) => `<b>${match}</b>`);
}

function RichText({ text }: { text: string }): ReactNode {
  return <>{renderRichText(text)}</>;
}

function CountsBar({ counts }: { counts: FlashcardCounts | null }) {
  const { t } = useTranslation();
  if (!counts) return null;
  return (
    <div className="fc-counts">
      <span className="fc-count fc-count-total">{t('flashcards.totalCount', { value: formatNumber(counts.total) })}</span>
      <span className="fc-count fc-count-new">{t('flashcards.newCount', { value: formatNumber(counts.new) })}</span>
      <span className="fc-count fc-count-due">{t('flashcards.dueValue', { value: formatNumber(counts.due) })}</span>
      {counts.studied > 0 ? (
        <span className="fc-count fc-count-studied">{t('flashcards.studiedCount', { value: formatNumber(counts.studied) })}</span>
      ) : null}
    </div>
  );
}

// --- review ---------------------------------------------------------------

function ReviewPane({
  deckId,
  selection,
  direction,
  onCountsChange,
}: {
  deckId?: string;
  selection?: FlashcardDeckSelection;
  direction: 'recognition' | 'production';
  onCountsChange: (c: FlashcardCounts) => void;
}) {
  const { t, i18n } = useTranslation();
  const [cards, setCards] = useState<FlashcardQueueCard[]>([]);
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const shownAt = useRef<number>(Date.now());

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const queue = await apiClient.getFlashcardQueue(deckId, 50, selection);
      setCards(queue.cards);
      setIndex(0);
      setRevealed(false);
      shownAt.current = Date.now();
      onCountsChange(queue.counts);
    } catch (err) {
      console.error('Failed to load flashcard queue:', err);
      setError(t('flashcards.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [deckId, selection, onCountsChange]);

  useEffect(() => { load(); }, [load]);

  const card = cards[index];

  const rate = useCallback(async (rating: FlashcardRating) => {
    if (!card || submitting) return;
    setSubmitting(true);
    try {
      const result = await apiClient.reviewFlashcard(
        card.card_id, rating, Date.now() - shownAt.current, selection,
      );
      onCountsChange(result.counts);
      if (index + 1 < cards.length) {
        setIndex(index + 1);
        setRevealed(false);
        shownAt.current = Date.now();
      } else {
        await load();   // refill: cards rated "Again" come back in this session
      }
    } catch (err) {
      console.error('Failed to submit review:', err);
      setError(t('flashcards.ratingFailed'));
    } finally {
      setSubmitting(false);
    }
  }, [card, cards.length, index, load, onCountsChange, selection, submitting]);

  // Space reveals, 1-4 rates — the keyboard shortcuts Anki users expect.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!card || (e.target instanceof HTMLElement && e.target.closest('input, select, textarea, summary, a, [contenteditable]'))) return;
      if (e.code === 'Space' || e.code === 'Enter') {
        if (e.target instanceof HTMLElement && e.target.closest('button')) return;
        e.preventDefault();
        if (!revealed) setRevealed(true);
        return;
      }
      if (revealed && ['1', '2', '3', '4'].includes(e.key)) {
        e.preventDefault();
        rate(Number(e.key) as FlashcardRating);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [card, revealed, rate]);

  if (loading) return <div className="fc-message">{t('flashcards.loading')}</div>;
  if (error) {
    return (
      <div className="fc-message fc-error">
        {error}
        <button className="fc-link" onClick={load}>{t('flashcards.tryAgain')}</button>
      </div>
    );
  }
  if (!card) {
    return (
      <div className="fc-message fc-done">
        <div className="fc-done-mark">✓</div>
        <p>{t('flashcards.nothingToReview')}</p>
        <button className="fc-link" onClick={load}>{t('flashcards.refresh')}</button>
      </div>
    );
  }

  // Reverse direction (definition/translation -> word) is a *presentation*
  // choice, not a second card: one card, one FSRS state, shown each way on
  // alternating reviews. `reps` is stable until the card is rated, so the
  // direction cannot flip while it is on screen.
  //
  // Grammar notes are never reversed — "here is the rule, name it" is not a
  // useful recall target.
  //
  // Recognising a word and producing it are different skills, so a single
  // stability value is a blend of the two. That is the accepted cost of not
  // splitting them into separate cards.
  const isReversed = card.note_type !== 'grammar' && Boolean(card.fields.back) && direction === 'production';

  const momentUrl = videoMomentUrl(card.fields, i18n.language);
  const pdfUrl = pdfSourceUrl(card);
  // `source_sentence` is the cleaned-up transcript line; `example` is whatever
  // the original import carried. Prefer the sentence when a card has one.
  const spokenLine =
    (typeof card.fields.source_sentence === 'string' ? card.fields.source_sentence : '') ||
    card.fields.example ||
    '';
  // Recognition cards are asked in context: the sentence sits on the front
  // with the word in bold. It would give the answer away when producing the
  // word, so there it stays on the back as before.
  const sentenceOnFront = !isReversed && Boolean(spokenLine);
  // "battre en brèche · loc. verbale": what to memorise, which is the whole
  // idiom when the tapped word belongs to one.
  const headwordLine = [card.fields.headword, card.fields.grammar].filter(Boolean).join(' · ');

  return (
    <div className="fc-review">
      <div className="fc-progress">
        <span>{card.deck}</span>
        <span>{index + 1} / {cards.length}</span>
      </div>

      <div
        className={`fc-card ${revealed ? 'is-revealed' : ''}`}
        onClick={() => !revealed && setRevealed(true)}
        role={revealed ? undefined : 'button'}
        tabIndex={revealed ? undefined : 0}
        aria-label={revealed ? undefined : t('flashcards.showAnswer')}
        onKeyDown={(event) => {
          if (!revealed && (event.key === 'Enter' || event.key === ' ')) {
            event.preventDefault();
            setRevealed(true);
          }
        }}
      >
        {isReversed ? (
          <span className="fc-direction">produce the word</span>
        ) : null}

        <div className="fc-card-front" dir="auto">
          <RichText text={isReversed ? card.fields.back! : card.fields.front} />
        </div>
        {sentenceOnFront ? (
          <p className="fc-front-sentence" dir="auto">
            <RichText text={boldTerm(spokenLine, card.fields.source_url && typeof card.fields.original_front === 'string' ? card.fields.original_front : card.fields.front)} />
          </p>
        ) : null}

        {revealed ? (
          <div className="fc-card-back">
            {card.fields.headword ? (
              <p className="fc-headword" dir="auto">{headwordLine}</p>
            ) : null}
            {isReversed ? (
              <p className="fc-definition" dir="auto"><RichText text={card.fields.front} /></p>
            ) : card.fields.back ? (
              <p className="fc-definition" dir="auto"><RichText text={card.fields.back} /></p>
            ) : null}
            {/* In production mode the example contains the answer, so it only
                ever appears on the back there. */}
            {spokenLine && !sentenceOnFront ? (
              <p className="fc-example" dir="auto"><RichText text={spokenLine} /></p>
            ) : null}
            {card.fields.sentence_translation ? (
              <p className="fc-sentence-translation" dir="auto">{card.fields.sentence_translation}</p>
            ) : null}
            {card.fields.usage_note ? (
              <p className="fc-note-fa" dir="auto">{card.fields.usage_note}</p>
            ) : null}
            {card.fields.note_fa ? (
              <p className="fc-note-fa" dir="auto">{card.fields.note_fa}</p>
            ) : null}
            {card.fields.source_page ? (
              <p className="fc-source">{t('flashcards.page', { page: card.fields.source_page })}</p>
            ) : null}
            {/* Words mined from video get the line as it was actually spoken,
                plus a link to hear it. Hearing the word in its own sentence is
                the whole reason we kept the timestamp. */}
            {momentUrl ? (
              <a
                className="fc-moment"
                href={momentUrl}
                target="_blank"
                rel="noreferrer"
                onClick={(event) => event.stopPropagation()}
              >
                <span className="fc-moment-play" aria-hidden="true">&#9654;</span>
                <span className="fc-moment-text">
                  {t('flashcards.watchMoment', { time: formatMoment(card.fields.source_start as number) })}
                  {card.fields.source_title ? (
                    <span className="fc-moment-title">{card.fields.source_title as string}</span>
                  ) : null}
                </span>
              </a>
            ) : null}
            {pdfUrl ? (
              <a className="fc-moment" href={pdfUrl} onClick={(event) => event.stopPropagation()}>
                <span className="fc-moment-play" aria-hidden="true">↗</span>
                <span className="fc-moment-text">Open source PDF</span>
              </a>
            ) : null}
          </div>
        ) : null}
      </div>

      {revealed ? (
        <div className="fc-ratings">
          {RATINGS.map((r) => (
            <button
              key={r.value}
              className={`fc-rating fc-rating-${r.tone}`}
              disabled={submitting}
              onClick={() => rate(r.value)}
              aria-label={`${t(`flashcards.rating.${r.tone}`)} — ${t(`flashcards.rating.${r.tone}Hint`)} (${r.value})`}
              aria-keyshortcuts={String(r.value)}
            >
              <span className="fc-rating-label">{t(`flashcards.rating.${r.tone}`)}</span>
              <span className="fc-rating-hint">{t(`flashcards.rating.${r.tone}Hint`)}</span>
            </button>
          ))}
        </div>
      ) : (
        <button className="fc-show" onClick={() => setRevealed(true)}>{t('flashcards.showAnswer')}</button>
      )}
    </div>
  );
}

// --- authoring ------------------------------------------------------------

type DraftFields = Record<'front' | 'back' | 'example' | 'note_fa', string>;
type ReviewedSuggestion = {
  id: string;
  original: DraftFields;
  fields: DraftFields;
  warning: string;
};

function editableFields(fields: FlashcardFields): DraftFields {
  return {
    front: fields.front || '', back: fields.back || '',
    example: fields.example || '', note_fa: fields.note_fa || '',
  };
}

function ManagePane({
  deckId,
  defaultDeckPath,
  onChanged,
}: {
  deckId?: string;
  defaultDeckPath: string;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const [notes, setNotes] = useState<FlashcardNote[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<string | null>(null);  // note_id, or 'new'
  const [draft, setDraft] = useState(() => emptyDraft(defaultDeckPath));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [suggestions, setSuggestions] = useState<ReviewedSuggestion[]>([]);
  const [approvedIds, setApprovedIds] = useState<string[]>([]);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiMessage, setAiMessage] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const loaded = await apiClient.getFlashcardNotes({
        deckId,
        search: search || undefined,
      });
      setNotes(loaded);
      const visible = new Set(loaded.map((note) => note.note_id));
      setSelectedIds((ids) => ids.filter((id) => visible.has(id)));
    } catch (err) {
      console.error('Failed to load notes:', err);
      setError(t('flashcards.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [deckId, search]);

  useEffect(() => {
    const t = setTimeout(load, search ? 250 : 0);   // debounce typing
    return () => clearTimeout(t);
  }, [load, search]);

  const deckCount = useMemo(
    () => new Set(notes.map((n) => n.deck_id)).size,
    [notes],
  );

  const draftNew = async () => {
    if (!draft.front.trim()) { setError('Enter a word or phrase first.'); return; }
    setAiBusy(true); setError(''); setAiMessage('');
    try {
      const result = await apiClient.draftFlashcards({ new_fields: editableFields(draft) });
      const proposed = result.suggestions[0];
      if (!proposed) throw new Error('No suggestion returned');
      setDraft({ ...draft, ...editableFields(proposed.fields) });
      setAiMessage(proposed.warning || 'AI suggestion added. Review and edit it before saving.');
    } catch (err) {
      console.error('Card drafting failed:', err);
      setError(err instanceof Error ? err.message : 'Could not draft this card. Please try again.');
    } finally { setAiBusy(false); }
  };

  const draftSelected = async (ids = selectedIds) => {
    if (!ids.length || ids.length > 10) {
      setError('Select 1–10 cards to improve at a time.'); return;
    }
    setAiBusy(true); setError(''); setAiMessage(''); setSuggestions([]); setApprovedIds([]);
    try {
      const result = await apiClient.draftFlashcards({ note_ids: ids });
      const byId = new Map(notes.map((note) => [note.note_id, note]));
      setSuggestions(result.suggestions.map((item) => ({
        id: item.id,
        original: editableFields(byId.get(item.id)!.fields),
        fields: editableFields(item.fields),
        warning: item.warning,
      })));
      setAiMessage('Review each suggestion, edit it if needed, then choose which cards to apply.');
    } catch (err) {
      console.error('Card drafting failed:', err);
      setError(err instanceof Error ? err.message : 'Could not generate suggestions. No cards were changed.');
    } finally { setAiBusy(false); }
  };

  const applySelected = async () => {
    const chosen = suggestions.filter((item) => approvedIds.includes(item.id));
    if (!chosen.length) return;
    if (chosen.length > 1 && !window.confirm(`Apply reviewed changes to ${chosen.length} cards?`)) return;
    setAiBusy(true); setError('');
    try {
      await apiClient.applyFlashcardDrafts(chosen.map((item) => ({
        note_id: item.id, expected_fields: item.original, fields: item.fields,
      })));
      setSuggestions([]); setSelectedIds([]); setApprovedIds([]);
      setAiMessage(`${chosen.length} card${chosen.length === 1 ? '' : 's'} updated. Review schedules were preserved.`);
      await load(); onChanged();
    } catch (err) {
      console.error('Could not apply card drafts:', err);
      setError(err instanceof Error ? err.message : 'Cards were not changed. Reload and try again.');
    } finally { setAiBusy(false); }
  };

  const startNew = () => { setDraft(emptyDraft(defaultDeckPath)); setEditing('new'); setError(''); };
  const startEdit = (note: FlashcardNote) => {
    setDraft({
      front: note.fields.front || '',
      back: note.fields.back || '',
      note_fa: note.fields.note_fa || '',
      example: note.fields.example || '',
      deck_path: defaultDeckPath,
    });
    setEditing(note.note_id);
    setError('');
  };

  const save = async () => {
    if (!draft.front.trim()) { setError(t('flashcards.frontRequired')); return; }
    setBusy(true);
    setError('');
    const fields: FlashcardFields = { front: draft.front.trim() };
    if (draft.back.trim()) fields.back = draft.back.trim();
    if (draft.note_fa.trim()) fields.note_fa = draft.note_fa.trim();
    if (draft.example.trim()) fields.example = draft.example.trim();
    try {
      if (editing === 'new') {
        await apiClient.createFlashcardNote({ deck_path: draft.deck_path, fields });
      } else if (editing) {
        // Scheduling is intentionally preserved by the API on edit.
        await apiClient.updateFlashcardNote(editing, { fields });
      }
      setEditing(null);
      await load();
      onChanged();
    } catch (err) {
      console.error('Failed to save note:', err);
      setError(t('flashcards.saveFailed'));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (note: FlashcardNote) => {
    if (!window.confirm(`Delete “${note.fields.front}” and its review history?`)) return;
    setBusy(true);
    try {
      await apiClient.deleteFlashcardNote(note.note_id);
      await load();
      onChanged();
    } catch (err) {
      console.error('Failed to delete note:', err);
      setError(t('flashcards.deleteFailed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fc-manage">
      <div className="fc-toolbar">
        <input
          className="fc-search"
          placeholder={t('flashcards.search')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          dir="auto"
        />
        <button className="fc-add" onClick={startNew}>+ Add</button>
      </div>

      {notes.length > 0 ? (
        <div className="fc-ai-toolbar">
          <span>{selectedIds.length} selected · up to 10 per batch</span>
          <button className="fc-secondary" onClick={() => setSelectedIds([])} disabled={!selectedIds.length || aiBusy}>Clear</button>
          <button className="fc-primary" onClick={() => draftSelected()} disabled={!selectedIds.length || selectedIds.length > 10 || aiBusy}>
            {aiBusy ? 'Drafting…' : '✨ Improve selected'}
          </button>
        </div>
      ) : null}

      {error ? <div className="fc-inline-error">{error}</div> : null}
      {aiMessage ? <p className="fc-hint fc-ai-message">{aiMessage}</p> : null}

      {suggestions.length ? (
        <section className="fc-ai-review" aria-label="Review AI suggestions">
          <div className="fc-ai-review-head">
            <h3>Review suggestions</h3>
            <button className="fc-secondary" onClick={() => { setSuggestions([]); setApprovedIds([]); }} disabled={aiBusy}>Discard all</button>
          </div>
          {suggestions.map((item) => (
            <div className="fc-ai-suggestion" key={item.id}>
              <label className="fc-ai-approve">
                <input type="checkbox" checked={approvedIds.includes(item.id)} onChange={(event) => setApprovedIds(event.target.checked ? [...approvedIds, item.id] : approvedIds.filter((id) => id !== item.id))} />
                Apply this card
              </label>
              <div className="fc-ai-comparison">
                <div className="fc-ai-original"><strong>Current</strong><span dir="auto">{item.original.front}</span><small dir="auto">{item.original.back}</small><small dir="auto">{item.original.example}</small><small dir="auto">{item.original.note_fa}</small></div>
                <div className="fc-ai-proposed"><strong>Suggested · editable</strong>
                  {(['front', 'back', 'example', 'note_fa'] as const).map((field) => (
                    <label key={field}>{field === 'note_fa' ? 'Persian meaning' : field}
                      <input dir="auto" value={item.fields[field]} onChange={(event) => setSuggestions((current) => current.map((row) => row.id === item.id ? { ...row, fields: { ...row.fields, [field]: event.target.value } } : row))} />
                    </label>
                  ))}
                </div>
              </div>
              {item.warning ? <p className="fc-ai-warning">Check this card: {item.warning}</p> : null}
            </div>
          ))}
          <button className="fc-primary" onClick={applySelected} disabled={!approvedIds.length || aiBusy}>Apply {approvedIds.length} selected</button>
        </section>
      ) : null}

      {editing ? (
        <div className="fc-editor">
          <label>
            Front
            <input
              value={draft.front}
              onChange={(e) => setDraft({ ...draft, front: e.target.value })}
              dir="auto"
              autoFocus
            />
          </label>
          <label>
            Definition
            <textarea
              value={draft.back}
              onChange={(e) => setDraft({ ...draft, back: e.target.value })}
              rows={3}
              dir="auto"
            />
          </label>
          <label>
            Example <span className="fc-optional">(optional)</span>
            <input
              value={draft.example}
              onChange={(e) => setDraft({ ...draft, example: e.target.value })}
              dir="auto"
            />
          </label>
          <label>
            Your note <span className="fc-optional">(optional)</span>
            <input
              value={draft.note_fa}
              onChange={(e) => setDraft({ ...draft, note_fa: e.target.value })}
              dir="auto"
            />
          </label>
          {editing === 'new' ? (
            <label>
              Deck <span className="fc-optional">(use :: to nest)</span>
              <input
                value={draft.deck_path}
                onChange={(e) => setDraft({ ...draft, deck_path: e.target.value })}
                dir="auto"
              />
            </label>
          ) : (
            <p className="fc-hint">{t('flashcards.editingTheContentWonTResetThisCardSSchedule')}</p>
          )}
          <div className="fc-editor-actions">
            <button className="fc-secondary" onClick={() => setEditing(null)} disabled={busy}>{t('flashcards.cancel')}</button>
            {editing === 'new' ? <button className="fc-secondary" onClick={draftNew} disabled={busy || aiBusy || !draft.front.trim()}>{aiBusy ? 'Drafting…' : '✨ Draft with AI'}</button> : null}
            <button className="fc-primary" onClick={save} disabled={busy}>
              {busy ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      ) : null}

      {loading ? (
        <div className="fc-message">{t('flashcards.loading')}</div>
      ) : notes.length === 0 ? (
        <div className="fc-message">
          {search ? t('flashcards.noMatches') : t('flashcards.noCards')}
        </div>
      ) : (
        <>
          <div className="fc-list-meta">
            {t('flashcards.cardCount', { count: notes.length })}
            {deckCount > 1 ? ` · ${t('flashcards.deckCount', { count: deckCount })}` : ''}
          </div>
          <ul className="fc-list">
            {notes.map((note) => (
              <li key={note.note_id} className="fc-item">
                <input className="fc-select-note" type="checkbox" aria-label={`Select ${note.fields.front}`} checked={selectedIds.includes(note.note_id)} onChange={(event) => setSelectedIds(event.target.checked ? [...selectedIds, note.note_id] : selectedIds.filter((id) => id !== note.note_id))} />
                <div className="fc-item-main">
                  <div className="fc-item-front" dir="auto">
                    <RichText text={note.fields.front} />
                  </div>
                  {note.fields.back ? (
                    <div className="fc-item-back" dir="auto">
                      <RichText text={note.fields.back} />
                    </div>
                  ) : null}
                  {note.fields.note_fa ? (
                    <div className="fc-item-fa" dir="auto">{note.fields.note_fa}</div>
                  ) : null}
                  <div className="fc-item-stats">
                    {note.card ? (
                      <>
                        <span>{note.card.reps} review{note.card.reps === 1 ? '' : 's'}</span>
                        {note.card.lapses > 0 ? (
                          <span>{note.card.lapses} lapse{note.card.lapses === 1 ? '' : 's'}</span>
                        ) : null}
                        {note.fields.source_page ? <span>p. {note.fields.source_page}</span> : null}
                      </>
                    ) : <span>never reviewed</span>}
                  </div>
                </div>
                <div className="fc-item-actions">
                  <button onClick={() => startEdit(note)} aria-label={t('common.edit')}>✎</button>
                  <button onClick={() => remove(note)} aria-label={t('common.delete')}>🗑</button>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function emptyDraft(deckPath: string) {
  return { front: '', back: '', note_fa: '', example: '', deck_path: deckPath };
}

/**
 * Choose which deck to study.
 *
 * Single-deck links expand a whole subtree. Library's multi-deck selection
 * uses exact card-holding decks instead, and has its own selector.
 *
 * Drill-down rather than a flat list of every deck: decks nest arbitrarily, and
 * one chip per deck stops being readable as soon as a few videos are imported.
 * Selecting a deck studies everything beneath it, so stopping at any level is a
 * valid choice.
 */
function DeckPicker({ decks, deckId, onSelect }: {
  decks: FlashcardDeck[];
  deckId?: string;
  onSelect: (deck: FlashcardDeck | null) => void;
}) {
  const { t } = useTranslation();
  if (!decks.length) return null;
  const current = decks.find((deck) => deck.deck_id === deckId) || null;
  const parent = decks.find((deck) => deck.deck_id === current?.parent_deck_id) || null;
  const roots = decks.filter((deck) => !deck.parent_deck_id);
  const base = current || (roots.length === 1 ? roots[0] : null);
  const children = decks.filter((deck) => (deck.parent_deck_id || null) === (base?.deck_id || null));
  if (!current && children.length < 2) return null;
  return (
    <div className="fc-decks" role="group" aria-label={t('flashcards.chooseDeck')}>
      <button type="button" className={!current ? 'is-active' : ''} onClick={() => onSelect(null)}>{t('flashcards.allCards')}</button>
      {current && <button type="button" className="is-active" onClick={() => onSelect(parent)}>{current.name}</button>}
      {children.map((deck) => <button type="button" key={deck.deck_id} onClick={() => onSelect(deck)}>{deck.name}</button>)}
    </div>
  );
}

// --- page -----------------------------------------------------------------

export function FlashcardsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const deckId = params.get('deck') || undefined;
  const deckName = params.get('name') || undefined;
  const includedParam = params.get('deck_ids');
  const excludedParam = params.get('exclude_deck_ids');
  const selection = useMemo<FlashcardDeckSelection | undefined>(() => {
    if (includedParam) return { deckIds: includedParam.split(',').filter(Boolean) };
    if (excludedParam) return { excludeDeckIds: excludedParam.split(',').filter(Boolean) };
    return undefined;
  }, [includedParam, excludedParam]);
  const selectionKey = includedParam || excludedParam || '';
  const direction = params.get('direction') === 'production' ? 'production' : 'recognition';
  const [decks, setDecks] = useState<FlashcardDeck[]>([]);

  useEffect(() => {
    apiClient.getFlashcardDecks().then(setDecks).catch(() => {
      /* the picker is an enhancement; studying everything still works */
    });
  }, []);

  const selectDeck = useCallback((deck: FlashcardDeck | null) => {
    const next = new URLSearchParams(params);
    next.delete('deck_ids');
    next.delete('exclude_deck_ids');
    if (deck) { next.set('deck', deck.deck_id); next.set('name', deck.name); }
    else { next.delete('deck'); next.delete('name'); }
    setCounts(null);
    setParams(next, {replace: true});
  }, [params, setParams]);

  const selectDirection = (nextDirection: 'recognition' | 'production') => {
    const next = new URLSearchParams(params);
    if (nextDirection === 'recognition') next.delete('direction'); else next.set('direction', nextDirection);
    setParams(next, { replace: true });
  };

  const [tab, setTab] = useState<'review' | 'manage'>('review');
  const [counts, setCounts] = useState<FlashcardCounts | null>(null);

  const refreshCounts = useCallback(async () => {
    try {
      const queue = await apiClient.getFlashcardQueue(deckId, 1, selection);
      setCounts(queue.counts);
    } catch {
      /* counts are decorative; a failure here must not break the page */
    }
  }, [deckId, selection]);

  useEffect(() => { refreshCounts(); }, [refreshCounts]);

  return (
    <div className="fc-page">
      <div className="fc-container">
        <header className="fc-session-header">
          <div className="fc-session-heading">
            <h1 dir="auto">{selection ? t('flashcards.selectedDecks') : deckName || t('flashcards.allCards')}</h1>
          </div>
          {counts && <span className="fc-ready-count">{t('flashcards.dueCount', { count: counts.due })}</span>}
        </header>
        <details className="fc-setup">
          <summary>
            <span>{t('flashcards.studyOptions')}</span>
            <span>{t(`flashcards.${direction}`)}</span>
          </summary>
          <div className="fc-setup-body">
            {selection ? (
              <div className="fc-decks" role="group" aria-label={t('flashcards.chooseDeck')}>
                <span>{t('flashcards.selectedDecks')}</span>
                <button type="button" onClick={() => navigate('/decks')}>{t('flashcards.changeDecks')}</button>
                <button type="button" onClick={() => selectDeck(null)}>{t('flashcards.allCards')}</button>
              </div>
            ) : <DeckPicker decks={decks} deckId={deckId} onSelect={selectDeck} />}
            <div className="fc-decks" role="group" aria-label={t('flashcards.studyDirection')}>
              <button type="button" aria-pressed={direction === 'recognition'} className={direction === 'recognition' ? 'is-active' : ''} onClick={() => selectDirection('recognition')}>{t('flashcards.recognition')}</button>
              <button type="button" aria-pressed={direction === 'production'} className={direction === 'production' ? 'is-active' : ''} onClick={() => selectDirection('production')}>{t('flashcards.production')}</button>
            </div>
            <CountsBar counts={counts} />
          </div>
        </details>

        <div className="fc-tabs">
          <button className={tab === 'review' ? 'is-active' : ''} aria-pressed={tab === 'review'} onClick={() => setTab('review')}>{t('flashcards.reviewTab')}</button>
          <button className={tab === 'manage' ? 'is-active' : ''} aria-pressed={tab === 'manage'} onClick={() => setTab('manage')}>{t('flashcards.myCards')}</button>
        </div>

        {tab === 'review' ? (
          <ReviewPane key={selectionKey || deckId || 'all'} deckId={selection ? undefined : deckId} selection={selection} direction={direction} onCountsChange={setCounts} />
        ) : (
          <ManagePane
            deckId={deckId}
            defaultDeckPath={deckName || t('flashcards.myCards')}
            onChanged={refreshCounts}
          />
        )}
      </div>
    </div>
  );
}
