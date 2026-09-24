import type { ExploreCatalog, ExploreItem } from '../types';

export const EXPLORE_FILTERS = ['watch', 'all', 'courses', 'decks', 'clubs', 'read', 'habits'];

export function exploreFilter(value: string | null): string {
  return value && EXPLORE_FILTERS.includes(value) ? value : 'watch';
}

export function exploreFilterParams(type: string, subject: string): URLSearchParams {
  const params = new URLSearchParams();
  // All must be explicit now that the unfiltered landing page means Watch.
  if (type !== 'watch') params.set('type', type);
  if (type !== 'clubs' && subject !== 'all') params.set('subject', subject);
  return params;
}

export interface LearningEntry {
  item: ExploreItem;
  topicId: string;
  subjectId: string;
  subjectTitle: string;
  language?: string | null;
}

export function catalogEntries(catalog: ExploreCatalog): LearningEntry[] {
  return catalog.categories.flatMap(category => category.topics.flatMap(topic =>
    topic.items.map(item => ({ item, topicId: topic.id, subjectId: category.id, subjectTitle: category.title, language: category.language }))));
}

export function starterEntries(catalog: ExploreCatalog): LearningEntry[] {
  // A promotional description and the UI locale are not proof of subtitle readiness.
  const ready = catalogEntries(catalog).filter(({ item, topicId, language }) =>
    topicId === 'watch' && item.starter && item.subtitles_available && language &&
    item.subtitle_language?.toLowerCase().split('-')[0] === language.toLowerCase().split('-')[0]);
  // Offer one pick per language first, so the first category cannot fill Today.
  // This is a small editorial selection, not inferred user personalization.
  const languages = new Set<string>();
  const firstPicks: LearningEntry[] = [];
  const remaining: LearningEntry[] = [];
  for (const entry of ready) {
    const language = entry.language!.toLowerCase().split('-')[0];
    (languages.has(language) ? remaining : firstPicks).push(entry);
    languages.add(language);
  }
  return [...firstPicks, ...remaining];
}

export function youTubeUrlFor(item: ExploreItem): string | null {
  const videoId = item.native_ref?.match(/[?&]video_id=([a-zA-Z0-9_-]{11})(?:[&#]|$)/)?.[1];
  return videoId ? `https://www.youtube.com/watch?v=${videoId}` : null;
}

export function challengeIdFor(item: ExploreItem): string | null {
  return item.native_ref?.match(/^\/challenges\/([^/?#]+)/)?.[1] ?? null;
}

export function videoDuration(seconds?: number | null): string | null {
  if (!seconds || !Number.isFinite(seconds) || seconds <= 0) return null;
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}
