import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { apiClient } from '../api/client';
import type {
  FlashcardCounts,
  FlashcardFields,
  FlashcardNote,
  FlashcardQueueCard,
  FlashcardRating,
} from '../types';
import './FlashcardsPage.css';

/** 1=Again 2=Hard 3=Good 4=Easy — FSRS ratings, learner self-assessed. */
const RATINGS: Array<{ value: FlashcardRating; label: string; hint: string; tone: string }> = [
  { value: 1, label: 'Encore', hint: 'oublié', tone: 'again' },
  { value: 2, label: 'Difficile', hint: 'avec peine', tone: 'hard' },
  { value: 3, label: 'Correct', hint: 'su', tone: 'good' },
  { value: 4, label: 'Facile', hint: 'immédiat', tone: 'easy' },
];

/**
 * Render the `**bold**` / `*italic*` used in the vocab definitions.
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
      <span className="fc-count fc-count-due">{counts.due} à revoir</span>
      <span className="fc-count fc-count-new">{counts.new} nouvelles</span>
      <span className="fc-count fc-count-total">{counts.total} au total</span>
    </div>
  );
}

// --- review ---------------------------------------------------------------

function ReviewPane({ onCountsChange }: { onCountsChange: (c: FlashcardCounts) => void }) {
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
      const queue = await apiClient.getFlashcardQueue();
      setCards(queue.cards);
      setIndex(0);
      setRevealed(false);
      shownAt.current = Date.now();
      onCountsChange(queue.counts);
    } catch (err) {
      console.error('Failed to load flashcard queue:', err);
      setError("Impossible de charger les cartes.");
    } finally {
      setLoading(false);
    }
  }, [onCountsChange]);

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
        await load();   // refill: cards rated "Encore" come back in this session
      }
    } catch (err) {
      console.error('Failed to submit review:', err);
      setError("La note n'a pas pu être enregistrée.");
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

  if (loading) return <div className="fc-message">Chargement…</div>;
  if (error) {
    return (
      <div className="fc-message fc-error">
        {error}
        <button className="fc-link" onClick={load}>Réessayer</button>
      </div>
    );
  }
  if (!card) {
    return (
      <div className="fc-message fc-done">
        <div className="fc-done-mark">✓</div>
        <p>Rien à réviser pour le moment.</p>
        <button className="fc-link" onClick={load}>Actualiser</button>
      </div>
    );
  }

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
        <div className="fc-card-front" dir="auto">
          <RichText text={card.fields.front} />
        </div>

        {revealed ? (
          <div className="fc-card-back">
            {card.fields.back ? (
              <p className="fc-definition" dir="auto"><RichText text={card.fields.back} /></p>
            ) : null}
            {card.fields.example ? (
              <p className="fc-example" dir="auto"><RichText text={card.fields.example} /></p>
            ) : null}
            {card.fields.note_fa ? (
              <p className="fc-note-fa" dir="auto">{card.fields.note_fa}</p>
            ) : null}
            {card.fields.source_page ? (
              <p className="fc-source">p. {card.fields.source_page}</p>
            ) : null}
          </div>
        ) : (
          <div className="fc-reveal-hint">Appuyer pour voir la réponse</div>
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
              aria-label={`${r.label} — ${r.hint} (touche ${r.value})`}
              aria-keyshortcuts={String(r.value)}
            >
              <span className="fc-rating-label">{r.label}</span>
              <span className="fc-rating-hint">{r.hint}</span>
            </button>
          ))}
        </div>
      ) : (
        <button className="fc-show" onClick={() => setRevealed(true)}>
          Voir la réponse
        </button>
      )}
    </div>
  );
}

// --- authoring ------------------------------------------------------------

const EMPTY_DRAFT = { front: '', back: '', note_fa: '', example: '', deck_path: 'Français::B1' };

function ManagePane({ onChanged }: { onChanged: () => void }) {
  const [notes, setNotes] = useState<FlashcardNote[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<string | null>(null);  // note_id, or 'new'
  const [draft, setDraft] = useState({ ...EMPTY_DRAFT });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setNotes(await apiClient.getFlashcardNotes({ search: search || undefined }));
    } catch (err) {
      console.error('Failed to load notes:', err);
      setError('Impossible de charger les cartes.');
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    const t = setTimeout(load, search ? 250 : 0);   // debounce typing
    return () => clearTimeout(t);
  }, [load, search]);

  const decks = useMemo(() => {
    const seen = new Set<string>();
    notes.forEach((n) => n.card && seen.add(n.deck_id));
    return seen;
  }, [notes]);

  const startNew = () => { setDraft({ ...EMPTY_DRAFT }); setEditing('new'); setError(''); };
  const startEdit = (note: FlashcardNote) => {
    setDraft({
      front: note.fields.front || '',
      back: note.fields.back || '',
      note_fa: note.fields.note_fa || '',
      example: note.fields.example || '',
      deck_path: EMPTY_DRAFT.deck_path,
    });
    setEditing(note.note_id);
    setError('');
  };

  const save = async () => {
    if (!draft.front.trim()) { setError('Le recto est obligatoire.'); return; }
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
      setError("L'enregistrement a échoué.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (note: FlashcardNote) => {
    const label = note.fields.front;
    if (!window.confirm(`Supprimer « ${label} » et tout son historique de révision ?`)) return;
    setBusy(true);
    try {
      await apiClient.deleteFlashcardNote(note.note_id);
      await load();
      onChanged();
    } catch (err) {
      console.error('Failed to delete note:', err);
      setError('La suppression a échoué.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fc-manage">
      <div className="fc-toolbar">
        <input
          className="fc-search"
          placeholder="Rechercher…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          dir="auto"
        />
        <button className="fc-add" onClick={startNew}>+ Ajouter</button>
      </div>

      {error ? <div className="fc-inline-error">{error}</div> : null}

      {editing ? (
        <div className="fc-editor">
          <label>
            Recto
            <input
              value={draft.front}
              onChange={(e) => setDraft({ ...draft, front: e.target.value })}
              placeholder="le chien"
              dir="auto"
              autoFocus
            />
          </label>
          <label>
            Définition
            <textarea
              value={draft.back}
              onChange={(e) => setDraft({ ...draft, back: e.target.value })}
              placeholder="Animal domestique…"
              rows={3}
              dir="auto"
            />
          </label>
          <label>
            Exemple <span className="fc-optional">(facultatif)</span>
            <input
              value={draft.example}
              onChange={(e) => setDraft({ ...draft, example: e.target.value })}
              dir="auto"
            />
          </label>
          <label>
            Ma note <span className="fc-optional">(facultatif)</span>
            <input
              value={draft.note_fa}
              onChange={(e) => setDraft({ ...draft, note_fa: e.target.value })}
              dir="auto"
            />
          </label>
          {editing === 'new' ? (
            <label>
              Paquet
              <input
                value={draft.deck_path}
                onChange={(e) => setDraft({ ...draft, deck_path: e.target.value })}
                dir="auto"
              />
            </label>
          ) : (
            <p className="fc-hint">
              Modifier le contenu ne remet pas à zéro la programmation de la carte.
            </p>
          )}
          <div className="fc-editor-actions">
            <button className="fc-secondary" onClick={() => setEditing(null)} disabled={busy}>
              Annuler
            </button>
            <button className="fc-primary" onClick={save} disabled={busy}>
              {busy ? 'Enregistrement…' : 'Enregistrer'}
            </button>
          </div>
        </div>
      ) : null}

      {loading ? (
        <div className="fc-message">Chargement…</div>
      ) : notes.length === 0 ? (
        <div className="fc-message">
          {search ? 'Aucun résultat.' : 'Aucune carte pour le moment.'}
        </div>
      ) : (
        <>
          <div className="fc-list-meta">
            {notes.length} carte{notes.length > 1 ? 's' : ''}
            {decks.size > 1 ? ` · ${decks.size} paquets` : ''}
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
                        <span>{note.card.reps} révision{note.card.reps > 1 ? 's' : ''}</span>
                        {note.card.lapses > 0 ? <span>{note.card.lapses} oubli{note.card.lapses > 1 ? 's' : ''}</span> : null}
                        {note.fields.source_page ? <span>p. {note.fields.source_page}</span> : null}
                      </>
                    ) : <span>jamais révisée</span>}
                  </div>
                </div>
                <div className="fc-item-actions">
                  <button onClick={() => startEdit(note)} aria-label="Modifier">✎</button>
                  <button onClick={() => remove(note)} aria-label="Supprimer">🗑</button>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

// --- page -----------------------------------------------------------------

export function FlashcardsPage() {
  const [tab, setTab] = useState<'review' | 'manage'>('review');
  const [counts, setCounts] = useState<FlashcardCounts | null>(null);

  const refreshCounts = useCallback(async () => {
    try {
      const queue = await apiClient.getFlashcardQueue(undefined, 1);
      setCounts(queue.counts);
    } catch {
      /* counts are decorative; a failure here must not break the page */
    }
  }, []);

  useEffect(() => { refreshCounts(); }, [refreshCounts]);

  return (
    <div className="fc-page">
      <div className="fc-container">
        <header className="fc-header">
          <h1>Vocabulaire</h1>
          <CountsBar counts={counts} />
        </header>

        <div className="fc-tabs">
          <button
            className={tab === 'review' ? 'is-active' : ''}
            onClick={() => setTab('review')}
          >
            Réviser
          </button>
          <button
            className={tab === 'manage' ? 'is-active' : ''}
            onClick={() => setTab('manage')}
          >
            Mes cartes
          </button>
        </div>

        {tab === 'review'
          ? <ReviewPane onCountsChange={setCounts} />
          : <ManagePane onChanged={refreshCounts} />}
      </div>
    </div>
  );
}
