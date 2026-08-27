import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, CheckCircle2, Layers, Timer } from 'lucide-react';
import type { PromiseData } from '../../types';
import { formatPromiseText } from '../../utils/activityFormat';
import { useTelegramWebApp } from '../../hooks/useTelegramWebApp';
import { BottomSheet } from '../ui/BottomSheet';

export interface PlayPromise {
  id: string;
  data: PromiseData;
}

interface PlaySheetProps {
  open: boolean;
  promises: PlayPromise[];
  onClose: () => void;
  onStartFocus: (promiseId: string, promiseText: string) => void;
  onCheckIn: (promiseId: string, data: PromiseData) => void;
}

type PlayAction = {
  key: string;
  label: string;
  detail: string;
  icon: JSX.Element;
  /** Marks the action as the thing actually waiting, not merely available. */
  waiting: boolean;
  run: () => void;
};

// One line under the promise title on the square. It answers "why am I looking
// at this?", so a real number always beats a generic verb.
function summarise(actions: PlayAction[], t: TFunction): string {
  const waiting = actions.filter((a) => a.waiting);
  if (waiting.length === 0) return actions.length > 0 ? t('play.ready') : t('play.nothingDue');
  if (waiting.length === 1) return waiting[0].detail || waiting[0].label;
  return t('play.thingsWaiting', { count: waiting.length });
}

export function PlaySheet({ open, promises, onClose, onStartFocus, onCheckIn }: PlaySheetProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { hapticFeedback } = useTelegramWebApp();
  const [openPromiseId, setOpenPromiseId] = useState<string | null>(null);

  const go = (to: string) => {
    onClose();
    navigate(to);
  };

  // Actions are derived per promise rather than stored: a promise offers a quiz
  // because a challenge is attached to it, decks because decks point at it, and
  // a timer because it is measured in hours. Nothing here is French-specific.
  const actionsFor = useMemo(
    () => (item: PlayPromise): PlayAction[] => {
      const { id, data } = item;
      const actions: PlayAction[] = [];

      // Every challenge on this promise, not just one — a promise that owns two
      // courses has to offer both.
      const quizzes = data.quizzes ?? (data.daily_activity ? [data.daily_activity] : []);
      for (const quiz of quizzes) {
        const due = quiz.status === 'due';
        actions.push({
          key: `quiz-${quiz.challenge_id}`,
          label: quiz.title || "Today's quiz",
          detail: due
            ? t('play.newQuestionsToday')
            : `Done today${quiz.score != null ? ` · ${Math.round(quiz.score)}%` : ''}`,
          icon: <Layers size={18} aria-hidden />,
          waiting: due,
          run: () => go(`/challenges/${quiz.challenge_id}/play`),
        });
      }

      for (const deck of data.decks ?? []) {
        const pending = deck.due + deck.new;
        actions.push({
          key: `deck-${deck.deck_id}`,
          label: deck.name,
          detail:
            pending > 0
              ? `${deck.due} due · ${deck.new} new`
              : `All caught up · ${deck.total} cards`,
          icon: <BookOpen size={18} aria-hidden />,
          waiting: pending > 0,
          run: () =>
            go(
              `/flashcards?deck=${encodeURIComponent(deck.deck_id)}` +
                `&name=${encodeURIComponent(deck.name)}`,
            ),
        });
      }

      if (data.metric_type === 'count') {
        actions.push({
          key: `checkin-${id}`,
          label: t('play.checkIn'),
          detail: t('play.logThatYouDidIt'),
          icon: <CheckCircle2 size={18} aria-hidden />,
          waiting: false,
          run: () => {
            onClose();
            onCheckIn(id, data);
          },
        });
      } else if ((data.hours_promised || 0) > 0) {
        actions.push({
          key: `focus-${id}`,
          label: t('play.startFocus'),
          detail: '25-minute timer',
          icon: <Timer size={18} aria-hidden />,
          waiting: false,
          run: () => {
            onClose();
            onStartFocus(id, data.text);
          },
        });
      }

      return actions;
    },
    // `go`, `onCheckIn` and `onStartFocus` all close the sheet first, so they are
    // stable enough for this to depend only on what changes the actions.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [promises],
  );

  const cards = useMemo(
    () =>
      promises
        .map((item) => ({ item, actions: actionsFor(item) }))
        .filter(({ actions }) => actions.length > 0)
        // Whatever is actually waiting comes first; the rest keep report order.
        .sort((a, b) => {
          const aw = a.actions.filter((x) => x.waiting).length;
          const bw = b.actions.filter((x) => x.waiting).length;
          return bw - aw;
        }),
    [promises, actionsFor],
  );

  const opened = openPromiseId
    ? cards.find(({ item }) => item.id === openPromiseId)
    : null;

  const close = () => {
    setOpenPromiseId(null);
    onClose();
  };

  if (opened) {
    return (
      <BottomSheet
        open={open}
        onClose={close}
        title={formatPromiseText(opened.item.data.text)}
        subtitle="Pick what to do"
      >
        <div className="play-actions">
          {opened.actions.map((action) => (
            <button
              key={action.key}
              type="button"
              className={`play-action${action.waiting ? ' is-waiting' : ''}`}
              onClick={() => {
                hapticFeedback('light');
                action.run();
              }}
            >
              <span className="play-action-icon">{action.icon}</span>
              <span className="play-action-body">
                <span className="play-action-label" dir="auto">{action.label}</span>
                <span className="play-action-detail" dir="auto">{action.detail}</span>
              </span>
            </button>
          ))}
        </div>
        <button
          type="button"
          className="play-back"
          onClick={() => setOpenPromiseId(null)}
        >
          ← All promises
        </button>
      </BottomSheet>
    );
  }

  return (
    <BottomSheet
      open={open}
      onClose={close}
      title={t('play.play')}
      subtitle={cards.length > 0 ? t('play.whatNeedsDoingToday') : undefined}
    >
      {cards.length === 0 ? (
        <p className="play-empty">{t('play.nothingIsWaitingRightNowAddAPromiseOrComeBac')}</p>
      ) : (
        <div className="play-grid">
          {cards.map(({ item, actions }) => {
            const waiting = actions.some((a) => a.waiting);
            return (
              <button
                key={item.id}
                type="button"
                className={`play-tile${waiting ? ' is-waiting' : ''}`}
                onClick={() => {
                  hapticFeedback('light');
                  // A promise with exactly one thing to do should not make the
                  // user pick from a list of one.
                  if (actions.length === 1) {
                    actions[0].run();
                    return;
                  }
                  setOpenPromiseId(item.id);
                }}
              >
                <span className="play-tile-title" dir="auto">
                  {formatPromiseText(item.data.text)}
                </span>
                <span className="play-tile-meta" dir="auto">{summarise(actions, t)}</span>
              </button>
            );
          })}
        </div>
      )}
      <button type="button" className="play-back" onClick={() => go('/dashboard')}>{t('play.seeAllPromises')}</button>
    </BottomSheet>
  );
}
