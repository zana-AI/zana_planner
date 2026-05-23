export type PromiseCardIdPlacement = 'meta' | 'badge-before' | 'badge-after' | 'title';

const STORAGE_KEY = 'xaana_pcard_id_placement';

export const PROMISE_CARD_ID_PLACEMENTS: PromiseCardIdPlacement[] = [
  'meta',
  'badge-before',
  'badge-after',
  'title',
];

export const PROMISE_CARD_ID_PLACEMENT_LABELS: Record<PromiseCardIdPlacement, string> = {
  meta: 'Stats row (left)',
  'badge-before': 'Inside badge (before status)',
  'badge-after': 'Inside badge (after status)',
  title: 'Next to title',
};

export function readPromiseCardIdPlacement(): PromiseCardIdPlacement {
  const value = localStorage.getItem(STORAGE_KEY);
  if (value && PROMISE_CARD_ID_PLACEMENTS.includes(value as PromiseCardIdPlacement)) {
    return value as PromiseCardIdPlacement;
  }
  return 'meta';
}

export function writePromiseCardIdPlacement(placement: PromiseCardIdPlacement) {
  localStorage.setItem(STORAGE_KEY, placement);
}
