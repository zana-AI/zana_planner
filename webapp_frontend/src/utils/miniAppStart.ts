// Capture before a router redirect can discard Telegram's launch query.
export const MINIAPP_START_PARAM = (() => {
  // A reader/PDF handoff or Back navigation already carries its destination.
  // Telegram's SDK may restore the original start_param from sessionStorage;
  // don't replay that launch and trap the reader in a navigation loop.
  if (new URLSearchParams(window.location.hash.slice(1)).has('session_token')) return '';
  const params = new URLSearchParams(window.location.search);
  return (window.Telegram?.WebApp?.initDataUnsafe?.start_param
    || params.get('tgWebAppStartParam') || params.get('startapp') || params.get('challenge') || '').trim();
})();

export function clubReaderDestination(value: string): { content_id: string; club_id: string } | null {
  const match = /^clubread_([a-f0-9]{32})_([a-f0-9]{32})$/.exec(value);
  if (!match) return null;
  const uuid = (hex: string) => `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  return { content_id: uuid(match[1]), club_id: uuid(match[2]) };
}
