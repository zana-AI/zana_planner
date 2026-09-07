import { useTranslation } from 'react-i18next';
import { Layers, Play } from 'lucide-react';
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
 *
 * Every fact appears exactly once. A video card's thumbnail carries its
 * identity, so a deck's carries the two things a deck has instead — how big it
 * is and how far through it you are. The status slot owns what is waiting, and
 * the subtitle owns only what the title cannot say: which deck this one is,
 * when two of them share a name.
 */
export function DeckCard({ deck, onStudy }: DeckCardProps) {
  const { t } = useTranslation();
  const pending = deck.due + deck.new;
  const status = pending > 0 ? t('content.deckDue', { count: pending }) : t('content.deckDone');
  // Cards you have been introduced to. A brand-new deck reads 0, which is
  // honest and looks like an empty track rather than a broken number.
  const seenRatio = deck.total > 0 ? (deck.total - deck.new) / deck.total : 0;

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
      <div className="content-card-media deck-media" aria-hidden="true">
        <span className="deck-stack">
          <span className="deck-stack-face">
            <strong className="deck-stack-count">{deck.total}</strong>
            <span className="deck-stack-unit">{t('content.deckUnit')}</span>
          </span>
        </span>
        <span className="deck-progress">
          <span className="deck-progress-fill" style={{ width: `${Math.round(seenRatio * 100)}%` }} />
        </span>
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
        {/* Two decks can share a name — there is a "Vidéos" under French and
            another under EN — so the parent is the only thing that tells them
            apart, and the only thing this line is for. */}
        {deck.parentName ? (
          <div className="content-card-subtitle">
            <span dir="auto">{deck.parentName}</span>
          </div>
        ) : null}
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
