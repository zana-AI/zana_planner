import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Play, Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import type { LibraryDeck } from '../types';
import './DecksPage.css';

export function DecksPage() {
  const navigate = useNavigate();
  const [decks, setDecks] = useState<LibraryDeck[]>([]);
  const [query, setQuery] = useState('');

  useEffect(() => { apiClient.getDeckTree().then(setDecks).catch(() => setDecks([])); }, []);
  const byId = useMemo(() => new Map(decks.map((deck) => [deck.deck_id, deck])), [decks]);
  const needle = query.trim().toLocaleLowerCase();
  const visible = decks.filter((deck) => deck.total > 0 && (!needle || deck.name.toLocaleLowerCase().includes(needle)));
  const path = (deck: LibraryDeck) => {
    const names = [deck.name]; let parent = deck.parent_deck_id ? byId.get(deck.parent_deck_id) : undefined;
    while (parent) { names.unshift(parent.name); parent = parent.parent_deck_id ? byId.get(parent.parent_deck_id) : undefined; }
    return names.join(' › ');
  };
  const study = (deck: LibraryDeck) => navigate(`/flashcards?deck=${encodeURIComponent(deck.deck_id)}&name=${encodeURIComponent(deck.name)}`);

  return <main className="decks-page"><header><button type="button" onClick={() => navigate('/my-contents')} aria-label="Back to library"><ArrowLeft size={20} /></button><div><h1>Decks</h1><p>Choose a deck or study a whole language.</p></div></header><label className="decks-search"><Search size={17}/><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search decks" /></label><section className="decks-list">{visible.map((deck) => <article key={deck.deck_id} className="decks-card"><div><h2 dir="auto">{deck.name}</h2><p dir="auto">{path(deck)}</p><small>{deck.due + deck.new} to study · {deck.total} cards</small></div><button type="button" onClick={() => study(deck)}><Play size={16}/> Study</button></article>)}</section></main>;
}
