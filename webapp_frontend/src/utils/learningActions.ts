export interface RoutineDraft {
  text: string;
  hoursPerWeek: number;
}

// Topic-based weekly budgets, not appointments. Each opens an editable draft.
export const ROUTINE_EXAMPLES = [
  { id: 'english', hoursPerWeek: 1, minutes: 60 },
  { id: 'french', hoursPerWeek: 1, minutes: 60 },
] as const;

export function saveActionKey(isVideo: boolean, state: 'idle' | 'adding' | 'added' | 'failed', joined: boolean): string {
  const done = joined || state === 'added';
  if (isVideo) return done ? 'learning.savedToLibrary' : state === 'adding' ? 'learning.savingToLibrary' : 'learning.saveToLibrary';
  return done ? 'learning.joined' : state === 'adding' ? 'learning.joining' : 'learning.join';
}
