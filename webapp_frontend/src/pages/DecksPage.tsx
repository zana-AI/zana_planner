import { useTranslation } from 'react-i18next';
import { useEffect, useMemo, useState } from 'react';
import { Check, ChevronDown, Minus, Play, Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import { formatNumber } from '../i18n/format';
import type { LibraryDeck } from '../types';
import './DecksPage.css';

export function DecksPage() {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [readyOnly, setReadyOnly] = useState(false);
  const [decks, setDecks] = useState<LibraryDeck[]>([]);
  const [query, setQuery] = useState('');
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [excludedIds, setExcludedIds] = useState<Set<string>>(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem('xaana-review-excluded-decks') || '[]');
      return new Set(Array.isArray(saved) ? saved.filter((id): id is string => typeof id === 'string') : []);
    } catch { return new Set(); }
  });
  useEffect(() => {
    sessionStorage.setItem('xaana-review-excluded-decks', JSON.stringify([...excludedIds]));
  }, [excludedIds]);

  const load = () => {
    setLoading(true);
    setError(false);
    apiClient.getDeckTree().then(setDecks).catch(() => setError(true)).finally(() => setLoading(false));
  };
  useEffect(load, []);

  const byId = useMemo(() => new Map(decks.map((deck) => [deck.deck_id, deck])), [decks]);
  const structure = useMemo(() => {
    const children = new Map<string, LibraryDeck[]>();
    for (const deck of decks) {
      if (!deck.parent_deck_id) continue;
      const siblings = children.get(deck.parent_deck_id) || [];
      siblings.push(deck);
      children.set(deck.parent_deck_id, siblings);
    }

    // Each row's counts cover its subtree. Select decks with direct cards;
    // a parent toggles its own cards and all descendants without duplicates.
    const directDecks = decks.map((deck) => {
      const immediate = children.get(deck.deck_id) || [];
      return {
        ...deck,
        ownTotal: Math.max(0, deck.total - immediate.reduce((sum, child) => sum + child.total, 0)),
        ownDue: Math.max(0, deck.due - immediate.reduce((sum, child) => sum + child.due, 0)),
        ownNew: Math.max(0, deck.new - immediate.reduce((sum, child) => sum + child.new, 0)),
      };
    }).filter((deck) => deck.ownTotal > 0);

    const branchIds = new Map<string, string[]>();
    for (const atom of directDecks) {
      let current: LibraryDeck | undefined = atom;
      const visited = new Set<string>();
      while (current && !visited.has(current.deck_id)) {
        visited.add(current.deck_id);
        const ids = branchIds.get(current.deck_id) || [];
        ids.push(atom.deck_id);
        branchIds.set(current.deck_id, ids);
        current = current.parent_deck_id ? byId.get(current.parent_deck_id) : undefined;
      }
    }
    return { children, directDecks, branchIds };
  }, [decks, byId]);

  const selected = structure.directDecks.filter((deck) => !excludedIds.has(deck.deck_id));
  const due = selected.reduce((sum, deck) => sum + deck.ownDue, 0);
  const fresh = selected.reduce((sum, deck) => sum + deck.ownNew, 0);
  const allSelected = selected.length === structure.directDecks.length;
  const needle = query.trim().toLocaleLowerCase();

  const path = (deck: LibraryDeck) => {
    const names = [deck.name];
    let parent = deck.parent_deck_id ? byId.get(deck.parent_deck_id) : undefined;
    const visited = new Set([deck.deck_id]);
    while (parent && !visited.has(parent.deck_id)) {
      visited.add(parent.deck_id);
      names.unshift(parent.name);
      parent = parent.parent_deck_id ? byId.get(parent.parent_deck_id) : undefined;
    }
    return names.join(' › ');
  };

  const toggle = (deckId: string) => {
    const branch = structure.branchIds.get(deckId) || [];
    setExcludedIds((previous) => {
      const next = new Set(previous);
      const allIncluded = branch.every((id) => !previous.has(id));
      for (const id of branch) {
        if (allIncluded) next.add(id);
        else next.delete(id);
      }
      return next;
    });
  };

  const review = () => {
    if (!selected.length) return;
    if (allSelected) { navigate('/flashcards'); return; }
    const included = selected.map((deck) => deck.deck_id);
    const excluded = structure.directDecks.filter((deck) => excludedIds.has(deck.deck_id)).map((deck) => deck.deck_id);
    const params = new URLSearchParams();
    if (included.length <= excluded.length) params.set('deck_ids', included.join(','));
    else params.set('exclude_deck_ids', excluded.join(','));
    navigate(`/flashcards?${params.toString()}`);
  };

  const matches = decks.filter((deck) =>
    deck.total > 0 && (!readyOnly || deck.due + deck.new > 0)
    && (!needle || path(deck).toLocaleLowerCase().includes(needle))
  );
  const visibleIds = new Set(matches.map((deck) => deck.deck_id));
  for (const deck of matches) {
    let parent = deck.parent_deck_id ? byId.get(deck.parent_deck_id) : undefined;
    const visited = new Set([deck.deck_id]);
    while (parent && !visited.has(parent.deck_id)) {
      visited.add(parent.deck_id);
      visibleIds.add(parent.deck_id);
      parent = parent.parent_deck_id ? byId.get(parent.parent_deck_id) : undefined;
    }
  }
  const visible: Array<{ deck: LibraryDeck; depth: number }> = [];
  const visited = new Set<string>();
  const appendBranch = (deck: LibraryDeck, depth: number) => {
    if (!visibleIds.has(deck.deck_id) || visited.has(deck.deck_id)) return;
    visited.add(deck.deck_id);
    visible.push({ deck, depth });
    if (needle || expandedIds.has(deck.deck_id)) {
      for (const child of structure.children.get(deck.deck_id) || []) appendBranch(child, depth + 1);
    }
  };
  for (const deck of decks) {
    if (!deck.parent_deck_id || !byId.has(deck.parent_deck_id)) appendBranch(deck, 0);
  }

  return (
    <main className="decks-page">
      <header><p>{t('learning.reviewHint')}</p></header>
      <label className="decks-search">
        <Search size={17} aria-hidden="true" />
        <input aria-label={t('deckBrowser.search')} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t('deckBrowser.search')} />
      </label>
      <div className="decks-filters">
        <button type="button" aria-pressed={!readyOnly} onClick={() => setReadyOnly(false)}>{t('deckBrowser.all')}</button>
        <button type="button" aria-pressed={readyOnly} onClick={() => setReadyOnly(true)}>{t('deckBrowser.ready')}</button>
      </div>
      {!loading && !error && structure.directDecks.length > 0 && (
        <div className="decks-selection-heading">
          <p>{t('deckBrowser.selectionHint')}</p>
          <div>
            <button type="button" onClick={() => setExcludedIds(new Set())} disabled={allSelected}>{t('deckBrowser.selectAll')}</button>
            <button type="button" onClick={() => setExcludedIds(new Set(structure.directDecks.map((deck) => deck.deck_id)))} disabled={selected.length === 0}>{t('deckBrowser.clearSelection')}</button>
          </div>
        </div>
      )}
      {loading ? <p role="status">{t('flashcards.loading')}</p> : error ? (
        <div role="alert"><p>{t('flashcards.loadFailed')}</p><button className="fc-link" onClick={load}>{t('flashcards.tryAgain')}</button></div>
      ) : (
        <section className="decks-list" aria-label={t('deckBrowser.title')}>
          {visible.map(({ deck, depth }) => {
            const branch = structure.branchIds.get(deck.deck_id) || [];
            const selectedCount = branch.filter((id) => !excludedIds.has(id)).length;
            const checked = selectedCount === 0 ? 'false' : selectedCount === branch.length ? 'true' : 'mixed';
            const hasChildren = (structure.children.get(deck.deck_id) || []).some((child) => visibleIds.has(child.deck_id));
            const expanded = Boolean(needle) || expandedIds.has(deck.deck_id);
            return <article key={deck.deck_id} className={`decks-card${checked === 'false' ? ' is-excluded' : ''}${hasChildren ? ' is-parent' : ''}`}
              style={{ marginInlineStart: `${Math.min(depth, 5) * 18}px` }}>
              <button type="button" className="decks-card-select" role="checkbox" aria-checked={checked}
                aria-label={`${deck.name}: ${selectedCount === 0 ? t('deckBrowser.excluded') : selectedCount === branch.length ? t('deckBrowser.included') : t('deckBrowser.partlyIncluded')}`}
                onClick={() => toggle(deck.deck_id)}>
                <span className="decks-card-check" aria-hidden="true">{checked === 'mixed' ? <Minus size={16} /> : checked === 'true' ? <Check size={16} /> : null}</span>
                <span className="decks-card-copy">
                  <strong dir="auto">{deck.name}</strong>
                  {needle && deck.parent_deck_id && <span className="decks-card-path" dir="auto">{path(deck)}</span>}
                  <small className="decks-card-counts" dir={i18n.dir()}>
                    <span dir="auto">{t('deckBrowser.totalCards', { value: formatNumber(deck.total) })}</span>
                    <span dir="auto">{t('deckBrowser.newCards', { value: formatNumber(deck.new) })}</span>
                    <span dir="auto">{t('deckBrowser.dueCards', { value: formatNumber(deck.due) })}</span>
                  </small>
                </span>
              </button>
              {hasChildren && !needle && <button type="button" className={`decks-card-expand${expanded ? ' is-expanded' : ''}`}
                aria-label={t(expanded ? 'deckBrowser.collapseDeck' : 'deckBrowser.expandDeck', { name: deck.name })}
                aria-expanded={expanded}
                onClick={() => setExpandedIds((previous) => {
                  const next = new Set(previous);
                  if (next.has(deck.deck_id)) next.delete(deck.deck_id);
                  else next.add(deck.deck_id);
                  return next;
                })}>
                <ChevronDown size={18} aria-hidden="true" />
              </button>}
            </article>;
          })}
          {visible.length === 0 && <div className="decks-empty"><p>{t(query ? 'deckBrowser.noMatch' : readyOnly ? 'deckBrowser.caughtUp' : 'learning.reviewEmpty')}</p>
            {!query && !readyOnly && <button type="button" className="explore-action" onClick={() => navigate('/explore?type=watch')}>{t('learning.exploreVideos')}</button>}
          </div>}
        </section>
      )}
      {!loading && !error && structure.directDecks.length > 0 && (
        <div className="decks-review-dock" role="region" aria-label={t('deckBrowser.reviewSelection')}>
          <div className="decks-review-dock-copy">
            <strong>{t('deckBrowser.selectedCount', { value: formatNumber(selected.length) })}</strong>
            <span>{t('deckBrowser.readySummary', { due: formatNumber(due), fresh: formatNumber(fresh) })}</span>
          </div>
          <button type="button" onClick={review} disabled={selected.length === 0 || due + fresh === 0}>
            <Play size={16} aria-hidden="true" />{t(selected.length > 0 && due + fresh === 0 ? 'deckBrowser.caughtUpButton' : allSelected ? 'deckBrowser.reviewAll' : 'deckBrowser.reviewSelected')}
          </button>
        </div>
      )}
    </main>
  );
}
