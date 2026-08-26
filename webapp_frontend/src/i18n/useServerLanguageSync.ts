import { useEffect } from 'react';

import { apiClient } from '../api/client';
import { applyServerLanguage, hasPreviewOverride } from './index';

/**
 * Adopts the language stored on the user's account once per session.
 *
 * The initial language comes from localStorage / Telegram / the browser, which
 * covers the first paint without a network round-trip. This corrects it to the
 * account setting afterwards, so a user who picked Persian on one device gets
 * Persian on the next one.
 *
 * Guarded at module scope rather than with state: <Navigation> and
 * <SettingsPage> already fetch `/user` on their own, and this should not add a
 * third request per route change.
 */
let synced = false;

export function useServerLanguageSync(enabled: boolean): void {
  useEffect(() => {
    if (!enabled || synced) return;
    // A `?lang=` preview override outranks the account setting; don't spend a
    // request we would only discard.
    if (hasPreviewOverride()) {
      synced = true;
      return;
    }
    synced = true;

    let cancelled = false;
    apiClient
      .getUserInfo()
      .then((info) => {
        if (!cancelled) applyServerLanguage(info.language);
      })
      .catch(() => {
        // Language is a preference, not a blocker — the resolved default stands.
        synced = false;
      });

    return () => {
      cancelled = true;
    };
  }, [enabled]);
}
