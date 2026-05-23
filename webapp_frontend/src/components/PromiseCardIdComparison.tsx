import type { PromiseData } from '../types';
import { PromiseCardV2 } from './PromiseCardV2';
import {
  PROMISE_CARD_ID_PLACEMENT_LABELS,
  PROMISE_CARD_ID_PLACEMENTS,
  readPromiseCardIdPlacement,
  writePromiseCardIdPlacement,
  type PromiseCardIdPlacement,
} from './promiseCardIdPlacement';

const SAMPLE_WEEK = ['2026-05-18', '2026-05-19', '2026-05-20', '2026-05-21', '2026-05-22', '2026-05-23', '2026-05-24'];

const SAMPLE_PROMISE: PromiseData = {
  text: 'Play Cheenva',
  hours_promised: 7,
  hours_spent: 5,
  metric_type: 'count',
  target_value: 7,
  achieved_value: 5,
  recurring: true,
  sessions: [
    { date: '2026-05-18', hours: 0 },
    { date: '2026-05-19', hours: 0 },
    { date: '2026-05-20', hours: 0 },
    { date: '2026-05-21', hours: 0 },
    { date: '2026-05-22', hours: 0 },
  ],
};

interface PromiseCardIdComparisonProps {
  onPick?: (placement: PromiseCardIdPlacement) => void;
}

export function PromiseCardIdComparison({ onPick }: PromiseCardIdComparisonProps) {
  const active = readPromiseCardIdPlacement();

  return (
    <section className="pcard-id-lab" aria-label="Promise ID placement comparison">
      <div className="pcard-id-lab-head">
        <h2>Promise ID placement</h2>
        <p>Tap a card to use that layout. Current: {PROMISE_CARD_ID_PLACEMENT_LABELS[active]}</p>
      </div>
      <div className="pcard-id-lab-grid">
        {PROMISE_CARD_ID_PLACEMENTS.map((placement) => (
          <div key={placement} className="pcard-id-lab-item">
            <p className="pcard-id-lab-label">{PROMISE_CARD_ID_PLACEMENT_LABELS[placement]}</p>
            <PromiseCardV2
              id="C01"
              data={SAMPLE_PROMISE}
              weekDays={SAMPLE_WEEK}
              idPlacement={placement}
              isComparison
              onOpenDetail={() => {}}
            />
            <button
              type="button"
              className={`btn btn-sm${active === placement ? ' btn-primary' : ' btn-secondary'}`}
              onClick={() => {
                writePromiseCardIdPlacement(placement);
                onPick?.(placement);
              }}
            >
              {active === placement ? 'Selected' : 'Use this'}
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
