import type { PublicActivityItem } from '../types';

export function formatRelativeTimestamp(timestampUtc?: string): string {
  if (!timestampUtc) return 'just now';

  const timestamp = new Date(timestampUtc);
  if (Number.isNaN(timestamp.getTime())) return 'just now';

  const diffMs = Date.now() - timestamp.getTime();
  const diffSeconds = Math.max(0, Math.floor(diffMs / 1000));

  if (diffSeconds < 60) return 'just now';

  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes}m ago`;

  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;

  const diffWeeks = Math.floor(diffDays / 7);
  if (diffWeeks < 5) return `${diffWeeks}w ago`;

  const diffMonths = Math.floor(diffDays / 30);
  if (diffMonths < 12) return `${diffMonths}mo ago`;

  const diffYears = Math.floor(diffDays / 365);
  return `${Math.max(1, diffYears)}y ago`;
}

export function formatDurationMinutes(durationMinutes?: number): string | null {
  if (!durationMinutes || durationMinutes <= 0) return null;
  if (durationMinutes < 60) return `${durationMinutes}m`;

  const hours = durationMinutes / 60;
  if (Number.isInteger(hours)) return `${hours}h`;
  return `${hours.toFixed(1)}h`;
}

/** Replace underscores with spaces for display – promise texts may be stored with underscores. */
export function formatPromiseText(text: string): string {
  return text.replace(/_/g, ' ');
}

export function buildActivitySummary(item: PublicActivityItem): string {
  const base = (item.action_label || 'updated progress').trim();
  const promiseText = item.promise_text?.trim();
  if (!promiseText) return base;
  return `${base} on ${formatPromiseText(promiseText)}`;
}
