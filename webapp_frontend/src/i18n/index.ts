/**
 * App localization runtime.
 *
 * Direction is handled as a document-level effect (`<html dir>`), never as a
 * prop threaded through components. Everything else follows from CSS logical
 * properties — if you find yourself writing `isRtl ? ... : ...` in a component,
 * the stylesheet is missing a logical property instead.
 *
 * See docs/I18N_RTL_PLAN.md.
 */
import i18next from 'i18next';
import { initReactI18next } from 'react-i18next';

import en from './locales/en.json';
import fa from './locales/fa.json';

export const SUPPORTED_LANGUAGES = ['en', 'fa'] as const;
export type AppLanguage = (typeof SUPPORTED_LANGUAGES)[number];

/** Languages that render right-to-left. */
const RTL_LANGUAGES = new Set<string>(['fa', 'ar', 'he', 'ur']);

/**
 * Languages whose UI catalogs are complete enough to serve to real users.
 *
 * Persian went live 2026-08-27 once the catalogs covered the shell, the daily
 * loop, the sheets, challenges and flashcards. The copy is pending review by a
 * native speaker (plan §7) — remove 'fa' here to pull it back without a code
 * revert; the Telegram bot keeps translating regardless.
 */
export const RELEASED_UI_LANGUAGES: readonly AppLanguage[] = ['en', 'fa'];

const STORAGE_KEY = 'xaana_ui_lang';
const OVERRIDE_KEY = 'xaana_ui_lang_override';

export const DEFAULT_LANGUAGE: AppLanguage = 'en';

function isSupported(value: string | null | undefined): value is AppLanguage {
  return !!value && (SUPPORTED_LANGUAGES as readonly string[]).includes(value);
}

export function isReleased(lng: string | null | undefined): lng is AppLanguage {
  return isSupported(lng) && RELEASED_UI_LANGUAGES.includes(lng);
}

/** `fa-IR` / `FA` / `fa_IR` → `fa`. Returns null for anything unsupported. */
export function normalizeLanguage(value: string | null | undefined): AppLanguage | null {
  if (!value) return null;
  const base = String(value).toLowerCase().replace('_', '-').split('-')[0];
  return isSupported(base) ? base : null;
}

export function isRtlLanguage(lng: string): boolean {
  const base = String(lng).toLowerCase().split('-')[0];
  return RTL_LANGUAGES.has(base);
}

/* ------------------------------------------------------------------ *
 * Preview override
 *
 * `?lang=fa` is how the team previews Persian before it ships. It is stored
 * in sessionStorage so it survives client-side navigation (react-router
 * rewrites the URL and would otherwise drop the query on the first push).
 * It deliberately bypasses the release gate above.
 * ------------------------------------------------------------------ */
function readOverride(): AppLanguage | null {
  let fromQuery: string | null = null;
  try {
    fromQuery = new URLSearchParams(window.location.search).get('lang');
  } catch {
    fromQuery = null;
  }

  if (fromQuery !== null) {
    const normalized = normalizeLanguage(fromQuery);
    try {
      if (normalized) sessionStorage.setItem(OVERRIDE_KEY, normalized);
      else sessionStorage.removeItem(OVERRIDE_KEY);
    } catch {
      /* private mode — override just won't survive navigation */
    }
    return normalized;
  }

  try {
    return normalizeLanguage(sessionStorage.getItem(OVERRIDE_KEY));
  } catch {
    return null;
  }
}

export function hasPreviewOverride(): boolean {
  return readOverride() !== null;
}

function readStored(): AppLanguage | null {
  try {
    return normalizeLanguage(localStorage.getItem(STORAGE_KEY));
  } catch {
    return null;
  }
}

function readTelegramLanguage(): AppLanguage | null {
  try {
    return normalizeLanguage(window.Telegram?.WebApp?.initDataUnsafe?.user?.language_code);
  } catch {
    return null;
  }
}

function readBrowserLanguage(): AppLanguage | null {
  try {
    return normalizeLanguage(navigator.language);
  } catch {
    return null;
  }
}

/**
 * Resolution order: preview override → last known choice → Telegram account
 * language → browser language → English. Everything except the override must
 * also pass the release gate.
 */
export function resolveInitialLanguage(): AppLanguage {
  const override = readOverride();
  if (override) return override;

  const candidates = [readStored(), readTelegramLanguage(), readBrowserLanguage()];
  for (const candidate of candidates) {
    if (isReleased(candidate)) return candidate;
  }
  return DEFAULT_LANGUAGE;
}

/** Mirrors the active language onto <html lang> / <html dir>. */
export function applyDocumentLanguage(lng: string): void {
  const root = document.documentElement;
  root.lang = lng;
  root.dir = isRtlLanguage(lng) ? 'rtl' : 'ltr';
}

i18next.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    fa: { translation: fa },
  },
  lng: resolveInitialLanguage(),
  fallbackLng: DEFAULT_LANGUAGE,
  supportedLngs: SUPPORTED_LANGUAGES as unknown as string[],
  interpolation: {
    // React already escapes.
    escapeValue: false,
  },
  returnNull: false,
});

/**
 * `{{count, num}}` — locale digits for interpolated numbers.
 *
 * Without this, Persian copy renders with Latin numerals embedded in it
 * ("2 فعال"). Using a named formatter rather than a blanket interpolation hook
 * keeps `count` doing plural selection while `num` handles display.
 */
i18next.services.formatter?.add('num', (value, lng) => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return String(value);
  try {
    const isFa = normalizeLanguage(lng) === 'fa';
    return new Intl.NumberFormat(
      `${isFa ? 'fa-IR' : 'en-US'}-u-nu-${isFa ? 'arabext' : 'latn'}`,
    ).format(value);
  } catch {
    return String(value);
  }
});

applyDocumentLanguage(i18next.language);
i18next.on('languageChanged', applyDocumentLanguage);

/** Change the UI language and remember the choice for next load. */
export function setAppLanguage(lng: string): void {
  const normalized = normalizeLanguage(lng);
  if (!normalized || normalized === i18next.language) return;
  try {
    localStorage.setItem(STORAGE_KEY, normalized);
  } catch {
    /* non-fatal — the choice just won't persist */
  }
  void i18next.changeLanguage(normalized);
}

/**
 * Apply the language stored on the user's account.
 *
 * The account setting also drives the Telegram bot, where Persian and French
 * already work. The webapp only honours it for languages whose UI catalogs
 * have shipped, so selecting Persian keeps translating the bot without
 * dropping the webapp into a half-translated state.
 *
 * A preview override always wins, so `?lang=fa` is not stomped on login.
 */
export function applyServerLanguage(language: string | null | undefined): void {
  if (hasPreviewOverride()) return;
  const normalized = normalizeLanguage(language);
  if (isReleased(normalized)) setAppLanguage(normalized);
}

export default i18next;
