/**
 * Locale-aware number and date formatting.
 *
 * Everything here goes through the platform `Intl` API, which already knows the
 * Jalali (Persian) calendar and the extended Arabic-Indic digits — so Persian
 * dates cost zero bundle weight. A date *library* is only needed for an
 * interactive Jalali month grid (InlineCalendar), which is Phase 3.
 *
 * See docs/I18N_RTL_PLAN.md §2 (D1, D2).
 */
import i18next, { DEFAULT_LANGUAGE, normalizeLanguage, type AppLanguage } from './index';

/** Per-language conventions. These encode decisions D1 and D2 from the plan. */
interface LocaleConventions {
  /** BCP-47 locale used for Intl lookups. */
  base: string;
  /** `arabext` = ۰۱۲۳۴۵۶۷۸۹, `latn` = 0123456789. */
  numberingSystem: 'latn' | 'arabext';
  /** `persian` = Jalali/Shamsi. */
  calendar: 'gregory' | 'persian';
  /** Intl weekday index, Sunday = 0. Persian week starts Saturday. */
  weekStartsOn: 0 | 1 | 2 | 3 | 4 | 5 | 6;
}

const CONVENTIONS: Record<AppLanguage, LocaleConventions> = {
  en: { base: 'en-US', numberingSystem: 'latn', calendar: 'gregory', weekStartsOn: 1 },
  fa: { base: 'fa-IR', numberingSystem: 'arabext', calendar: 'persian', weekStartsOn: 6 },
};

function conventionsFor(lng?: string): LocaleConventions {
  const normalized = normalizeLanguage(lng ?? i18next.language) ?? DEFAULT_LANGUAGE;
  return CONVENTIONS[normalized];
}

/**
 * Builds the Unicode extension locale, e.g. `fa-IR-u-ca-persian-nu-arabext`.
 * Being explicit keeps output identical across browsers and OS locales.
 */
export function intlLocale(lng?: string): string {
  const c = conventionsFor(lng);
  return `${c.base}-u-ca-${c.calendar}-nu-${c.numberingSystem}`;
}

/** Which weekday the week grid should start on, for the active language. */
export function weekStartsOn(lng?: string): number {
  return conventionsFor(lng).weekStartsOn;
}

export function formatNumber(value: number, options?: Intl.NumberFormatOptions, lng?: string): string {
  if (!Number.isFinite(value)) return '';
  try {
    return new Intl.NumberFormat(intlLocale(lng), options).format(value);
  } catch {
    return String(value);
  }
}

export function formatDate(value: Date | string | number, options?: Intl.DateTimeFormatOptions, lng?: string): string {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  try {
    return new Intl.DateTimeFormat(intlLocale(lng), options).format(date);
  } catch {
    return date.toISOString().slice(0, 10);
  }
}

/**
 * A date range such as `Aug 24 – Aug 30` / `۲ شهریور – ۸ شهریور`.
 * Uses `formatRange` where available so Intl can collapse shared parts.
 */
export function formatDateRange(
  start: Date | string | number,
  end: Date | string | number,
  options: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' },
  lng?: string,
): string {
  const a = start instanceof Date ? start : new Date(start);
  const b = end instanceof Date ? end : new Date(end);
  if (Number.isNaN(a.getTime()) || Number.isNaN(b.getTime())) return '';
  try {
    // `formatRange` is ES2021; this project's tsconfig targets ES2020 lib, so
    // it is typed locally rather than widening `lib` for the whole codebase.
    const formatter = new Intl.DateTimeFormat(intlLocale(lng), options) as Intl.DateTimeFormat & {
      formatRange?: (start: Date, end: Date) => string;
    };
    if (typeof formatter.formatRange === 'function') {
      return formatter.formatRange(a, b);
    }
    return `${formatter.format(a)} – ${formatter.format(b)}`;
  } catch {
    return '';
  }
}

/**
 * Converts Persian (۰-۹) and Arabic-Indic (٠-٩) digits to ASCII, plus the
 * Arabic decimal separator and thousands mark.
 *
 * Every numeric input must run through this before its value reaches the API —
 * a Persian keyboard produces U+06F0-06F9, which `parseFloat` reads as NaN.
 */
export function toLatinDigits(value: string): string {
  if (!value) return '';
  return value
    .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0)) // Persian
    .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660)) // Arabic-Indic
    .replace(/٫/g, '.')  // Arabic decimal separator
    .replace(/٬/g, '');  // Arabic thousands separator
}

/** `toLatinDigits` then `parseFloat`. Returns null when there is no number. */
export function parseLocalizedNumber(value: string): number | null {
  const parsed = Number.parseFloat(toLatinDigits(value).replace(/,/g, ''));
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Narrow weekday labels (`M T W T F S S` / `د س چ پ ج ش ی`) in the order the
 * app's week arrays already use.
 *
 * `startDay` is a JS `getDay()` index and defaults to 1 (Monday) because the
 * backend buckets weeks Monday-first (`tm_bot/utils/time_utils.py`). This
 * localizes the *labels* only — it deliberately does not reorder the week, which
 * is decision D3 and a separate, data-affecting change.
 */
export function weekdayNarrowLabels(startDay: number = 1, lng?: string): string[] {
  // 2024-01-01 was a Monday; walk forward from the requested start day.
  const MONDAY = Date.UTC(2024, 0, 1);
  const offset = (startDay - 1 + 7) % 7;
  const out: string[] = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(MONDAY + (offset + i) * 86400000);
    out.push(formatDate(d, { weekday: 'narrow', timeZone: 'UTC' }, lng));
  }
  return out;
}

/** Full weekday names in the same ordering as `weekdayNarrowLabels`. */
export function weekdayLongLabels(startDay: number = 1, lng?: string): string[] {
  const MONDAY = Date.UTC(2024, 0, 1);
  const offset = (startDay - 1 + 7) % 7;
  const out: string[] = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(MONDAY + (offset + i) * 86400000);
    out.push(formatDate(d, { weekday: 'long', timeZone: 'UTC' }, lng));
  }
  return out;
}
