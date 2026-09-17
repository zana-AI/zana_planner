import { useTranslation } from 'react-i18next';
import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Play, Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import type { LibraryDeck } from '../types';
import './DecksPage.css';

export function DecksPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [readyOnly, setReadyOnly] = useState(false);
  const [decks, setDecks] = useState<LibraryDeck[]>([]);
  const [query, setQuery] = useState('');

  const load = () => { setLoading(true); setError(false); apiClient.getDeckTree().then(setDecks).catch(() => setError(true)).finally(() => setLoading(false)); };
  useEffect(load, []);
  const byId = useMemo(() => new Map(decks.map((deck) => [deck.deck_id, deck])), [decks]);
  const needle = query.trim().toLocaleLowerCase();

  const path = (deck: LibraryDeck) => {
    const names = [deck.name]; let parent = deck.parent_deck_id ? byId.get(deck.parent_deck_id) : undefined;
    const visited = new Set([deck.deck_id]);
    while (parent && !visited.has(parent.deck_id)) { visited.add(parent.deck_id); names.unshift(parent.name); parent = parent.parent_deck_id ? byId.get(parent.parent_deck_id) : undefined; }
    return names.join(' › ');
  };
  const study = (deck: LibraryDeck) => navigate(`/flashcards?deck=${encodeURIComponent(deck.deck_id)}&name=${encodeURIComponent(deck.name)}`);

  const visible = decks.filter((deck) => deck.total > 0 && (!readyOnly || deck.due + deck.new > 0) && (!needle || path(deck).toLocaleLowerCase().includes(needle)));
  return (
    <main className="decks-page">
      <header>
        <button type="button" onClick={() => navigate('/my-contents')} aria-label={t('deckBrowser.back')}><ArrowLeft size={20} className="icon-directional" /></button>
        <div><h1>{t('deckBrowser.title')}</h1><p>{t('deckBrowser.subtitle')}</p></div>
      </header>
      <label className="decks-search"><Search size={17}/><input aria-label={t('deckBrowser.search')} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t('deckBrowser.search')} /></label>
      <div className="decks-filters">
        <button aria-pressed={!readyOnly} onClick={() => setReadyOnly(false)}>{t('deckBrowser.all')}</button>
        <button aria-pressed={readyOnly} onClick={() => setReadyOnly(true)}>{t('deckBrowser.ready')}</button>
      </div>
      {loading ? <p role="status">{t('flashcards.loading')}</p> : error ? <div role="alert"><p>{t('flashcards.loadFailed')}</p><button className="fc-link" onClick={load}>{t('flashcards.tryAgain')}</button></div> : (
        <section className="decks-list" aria-label={t('deckBrowser.title')}>
          {visible.map((deck) => <article key={deck.deck_id} className="decks-card">
            <div className="decks-card-copy"><h2 dir="auto">{deck.name}</h2>{deck.parent_deck_id && <p dir="auto">{path(deck)}</p>}
              <small>{t('deckBrowser.counts', { due: deck.due, fresh: deck.new, total: deck.total })}</small>
            </div>
            <button type="button" onClick={() => study(deck)} aria-label={`${t('deckBrowser.study')} ${deck.name}`}><Play size={16}/>{t('deckBrowser.study')}</button>
          </article>)}
          {visible.length === 0 && <p className="decks-empty">{t(query ? 'deckBrowser.noMatch' : readyOnly ? 'deckBrowser.caughtUp' : 'deckBrowser.empty')}</p>}
        </section>
      )}
    </main>
  );
}
