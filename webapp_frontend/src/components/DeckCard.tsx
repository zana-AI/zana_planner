import { useTranslation } from 'react-i18next';
import { GraduationCap, Layers, Play } from 'lucide-react';
import type { LibraryDeck } from '../types';

interface DeckCardProps {
  deck: LibraryDeck;
  onStudy: () => void;
}

/**
 * A deck, rendered with the same card template as everything else in Library.
 *
 * It deliberately reuses the `content-card*` classes rather than styling itself:
 * a deck and a video are both things you own and come back to, so a second card
 * shape would say they are different kinds of object when they are not. The
 * badge is the only thing that distinguishes them, which is the badge's job.
 */
export function DeckCard({ deck, onStudy }: DeckCardProps) {
  const { t } = useTranslation();
  const pending = deck.due + deck.new;
  // Mirrors the status slot on a content card: what state is this in for me?
  const status = pending > 0 ? t('content.deckDue', { count: pending }) : t('content.deckDone');
  const studied = deck.total > 0 ? Math.round(((deck.total - deck.new) / deck.total) * 100) : 0;

  return (
    <article
      className="content-card"
      role="button"
      tabIndex={0}
      onClick={onStudy}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onStudy();
        }
      }}
    >
      <div className="content-card-media" aria-hidden="true">
        <div className="content-card-media-fallback">
          <GraduationCap size={17} />
        </div>
      </div>

      <div className="content-card-body">
        <div className="content-card-meta-row">
          <span className="content-card-type content-card-type--deck">
            <Layers size={17} />
            {t('content.types.deck')}
          </span>
          <span className="content-card-status">{status}</span>
        </div>
        <h3 className="content-card-title" dir="auto">{deck.name}</h3>
        <div className="content-card-subtitle">
          {/* Two decks can share a name — there is a "Vidéos" under French and
              another under EN — so the parent is what tells them apart. */}
          {deck.parentName ? <span dir="auto">{deck.parentName}</span> : null}
          <span>{t('content.deckCards', { count: deck.total })}</span>
          <span>{t('content.deckStudied', { percent: studied })}</span>
        </div>
      </div>

      <div className="content-card-actions" onClick={(event) => event.stopPropagation()}>
        <button className="content-card-action" type="button" onClick={onStudy} title={t('content.study')}>
          <Play size={15} />
          <span>{t('content.study')}</span>
        </button>
      </div>
    </article>
  );
}
