import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';

// Captured ONCE at module load — before React Router can redirect "/" to
// "/dashboard" and wipe the query string (which would lose the deep-link param).
const INITIAL_SOURCE_KEY: string = (() => {
  try {
    const tgStartParam =
      (window.Telegram?.WebApp?.initDataUnsafe as { start_param?: string } | undefined)?.start_param;
    const params = new URLSearchParams(window.location.search);
    const urlStartParam =
      params.get('startapp') || params.get('tgWebAppStartParam') || params.get('challenge');
    return (tgStartParam || urlStartParam || '').trim();
  } catch {
    return '';
  }
})();

/**
 * Entry funnel: when the Mini App is opened from a channel post deep-link
 * (t.me/<bot>/<app>?startapp=<source_key>), resolve the source key to a
 * challenge and route straight into play — zero friction, no directory hop.
 *
 * Sources, in priority order:
 *   1. Telegram WebApp start param (initDataUnsafe.start_param)
 *   2. URL query fallback (?startapp= / ?tgWebAppStartParam= / ?challenge=)
 *      — useful for plain browser links and local testing.
 *
 * Runs once per app load (guarded), and only when authenticated enough to call the API.
 */
export function useChallengeDeepLink(enabled: boolean): void {
  const navigate = useNavigate();
  const handledRef = useRef(false);

  useEffect(() => {
    if (!enabled || handledRef.current) return;

    const sourceKey = INITIAL_SOURCE_KEY;
    if (!sourceKey) return;

    // One-shot: handledRef guards against a second fetch. We deliberately do NOT
    // cancel on cleanup — react-router's navigate identity changes on unrelated
    // re-renders, and cancelling here would drop the deep-link redirect.
    handledRef.current = true;
    (async () => {
      try {
        const challenge = await apiClient.getChallengeBySource(sourceKey);
        if (challenge?.challenge_id) {
          navigate(`/challenges/${challenge.challenge_id}/play`, { replace: true });
        }
      } catch {
        // Unknown/expired link — silently ignore and let the app land normally.
      }
    })();
  }, [enabled, navigate]);
}
