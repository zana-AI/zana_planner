import { useTranslation } from 'react-i18next';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiClient } from '../api/client';
import type {
  FlashcardCounts,
  FlashcardFields,
  FlashcardNote,
  FlashcardQueueCard,
  FlashcardRating,
} from '../types';
import './FlashcardsPage.css';

/**
 * UI copy is English — the app chrome is English everywhere, and the study
 * content itself carries whatever language the deck is in. Nothing here is
 * specific to French.
 */
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
function RichText({ text }: { text: string }): ReactNode {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const token = match[0];
    if (token.startsWith('**')) {
      nodes.push(<strong key={key++}>{token.slice(2, -2)}</strong>);
    } else {
      nodes.push(<em key={key++}>{token.slice(1, -1)}</em>);
    }
    last = match.index + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return <>{nodes}</>;
}

function CountsBar({ counts }: { counts: FlashcardCounts | null }) {
  if (!counts) return null;
  return (
    <div className="fc-counts">
      <span className="fc-count fc-count-due">{counts.due} due</span>
      <span className="fc-count fc-count-new">{counts.new} new</span>
      {counts.studied > 0 ? (
        <span className="fc-count fc-count-studied">{counts.studied} studied</span>
      ) : null}
      <span className="fc-count fc-count-total">{counts.total} total</span>
    </div>
  );
}

// --- review ---------------------------------------------------------------

function ReviewPane({
  deckId,
  onCountsChange,
}: {
  deckId?: string;
  onCountsChange: (c: FlashcardCounts) => void;
}) {
  const { t } = useTranslation();
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
      const queue = await apiClient.getFlashcardQueue(deckId);
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
  }, [deckId, onCountsChange]);

  useEffect(() => { load(); }, [load]);

  const card = cards[index];

  const rate = useCallback(async (rating: FlashcardRating) => {
    if (!card || submitting) return;
    setSubmitting(true);
    try {
      const result = await apiClient.reviewFlashcard(
        card.card_id, rating, Date.now() - shownAt.current
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
  }, [card, cards.length, index, load, onCountsChange, submitting]);

  // Space reveals, 1-4 rates — the keyboard shortcuts Anki users expect.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!card) return;
      if (e.code === 'Space' || e.code === 'Enter') {
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
  const isReversed =
    card.note_type !== 'grammar' && Boolean(card.fields.back) && card.reps % 2 === 1;

  return (
    <div className="fc-review">
      <div className="fc-progress">
        <span>{card.deck}</span>
        <span>{index + 1} / {cards.length}</span>
      </div>

      <div
        className={`fc-card ${revealed ? 'is-revealed' : ''}`}
        onClick={() => !revealed && setRevealed(true)}
        role="button"
        tabIndex={0}
      >
        {isReversed ? (
          <span className="fc-direction">produce the word</span>
        ) : null}

        <div className="fc-card-front" dir="auto">
          <RichText text={isReversed ? card.fields.back! : card.fields.front} />
        </div>

        {revealed ? (
          <div className="fc-card-back">
            {isReversed ? (
              <p className="fc-definition" dir="auto"><RichText text={card.fields.front} /></p>
            ) : card.fields.back ? (
              <p className="fc-definition" dir="auto"><RichText text={card.fields.back} /></p>
            ) : null}
            {/* The example usually contains the target word, so it stays on the
                answer side in both directions — as a prompt it would give the
                answer away. */}
            {card.fields.example ? (
              <p className="fc-example" dir="auto"><RichText text={card.fields.example} /></p>
            ) : null}
            {card.fields.note_fa ? (
              <p className="fc-note-fa" dir="auto">{card.fields.note_fa}</p>
            ) : null}
            {card.fields.source_page ? (
              <p className="fc-source">{t('flashcards.page', { page: card.fields.source_page })}</p>
            ) : null}
          </div>
        ) : (
          <div className="fc-reveal-hint">{t('flashcards.tapToReveal')}</div>
        )}
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
        <button className="fc-show" onClick={() => setRevealed(true)}>
          Show answer
        </button>
      )}
    </div>
  );
}

// --- authoring ------------------------------------------------------------

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

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setNotes(await apiClient.getFlashcardNotes({
        deckId,
        search: search || undefined,
      }));
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

      {error ? <div className="fc-inline-error">{error}</div> : null}

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
            <p className="fc-hint">
              Editing the content won’t reset this card’s schedule.
            </p>
          )}
          <div className="fc-editor-actions">
            <button className="fc-secondary" onClick={() => setEditing(null)} disabled={busy}>
              Cancel
            </button>
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

// --- page -----------------------------------------------------------------

export function FlashcardsPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const deckId = params.get('deck') || undefined;
  const deckName = params.get('name') || undefined;

  const [tab, setTab] = useState<'review' | 'manage'>('review');
  const [counts, setCounts] = useState<FlashcardCounts | null>(null);

  const refreshCounts = useCallback(async () => {
    try {
      const queue = await apiClient.getFlashcardQueue(deckId, 1);
      setCounts(queue.counts);
    } catch {
      /* counts are decorative; a failure here must not break the page */
    }
  }, [deckId]);

  useEffect(() => { refreshCounts(); }, [refreshCounts]);

  return (
    <div className="fc-page">
      <div className="fc-container">
        <header className="fc-header">
          <h1>{deckName || t('flashcards.study')}</h1>
          <CountsBar counts={counts} />
        </header>

        <div className="fc-tabs">
          <button
            className={tab === 'review' ? 'is-active' : ''}
            onClick={() => setTab('review')}
          >
            {t('flashcards.reviewTab')}
          </button>
          <button
            className={tab === 'manage' ? 'is-active' : ''}
            onClick={() => setTab('manage')}
          >
            {t('flashcards.myCards')}
          </button>
        </div>

        {tab === 'review' ? (
          <ReviewPane deckId={deckId} onCountsChange={setCounts} />
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
