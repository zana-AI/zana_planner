import type { TFunction } from 'i18next';
import type { ExploreTopic } from '../types';

/**
 * Topic ids are a fixed vocabulary — courses, watch, read, decks, habits — so
 * the same five words mean the same thing in every subject. See
 * `docs/EXPLORE_CONTENT.md`.
 *
 * That is also what makes them translatable: the catalog's own titles are
 * written in English by whoever curates it, but a known id can be looked up in
 * the locale catalogs. An unknown id falls back to the curator's title, so a
 * new topic still renders rather than showing a missing-key string.
 */
export const TOPIC_IDS = ['courses', 'watch', 'read', 'decks', 'habits'] as const;

export function topicLabel(t: TFunction, topic: ExploreTopic): string {
  return (TOPIC_IDS as readonly string[]).includes(topic.id)
    ? t(`explore.topic.${topic.id}`)
    : topic.title;
}

/**
 * The badge on a card. It names what the thing *is*, which the topic already
 * decides: a course is a deck someone releases on a cadence, so the same
 * challenge row is a Course under `courses` and a Deck under `decks`.
 */
const KIND_BY_TOPIC: Record<string, string> = {
  courses: 'course',
  watch: 'video',
  read: 'book',
  decks: 'deck',
  habits: 'habit',
};

export function itemKind(topicId: string): string | null {
  return KIND_BY_TOPIC[topicId] ?? null;
}
