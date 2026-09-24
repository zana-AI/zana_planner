import type { UserContent } from '../types';

/** Restore the progress-derived status without resetting any learning data.
 * Matches ContentProgressService's 95% completion threshold. */
export function restoredLibraryStatus(item: Pick<UserContent, 'progress_ratio' | 'completed_at'>): 'saved' | 'in_progress' | 'completed' {
  const progress = Number(item.progress_ratio || 0);
  if (item.completed_at || progress >= 0.95) return 'completed';
  return progress > 0 ? 'in_progress' : 'saved';
}
