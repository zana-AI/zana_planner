// Accept only our own login links, never navigate to a pasted URL.
export function parseBrowserLoginCode(input: string, origin: string): string | null {
  const value = input.trim();
  if (/^[A-Za-z0-9_-]{43}$/.test(value)) return value;
  try {
    const url = new URL(value);
    if (url.origin !== origin || url.pathname !== '/login') return null;
    const code = new URLSearchParams(url.hash.slice(1)).get('code') || '';
    return /^[A-Za-z0-9_-]{43}$/.test(code) ? code : null;
  } catch {
    return null;
  }
}

// A login may return to an item or a calendar completion page. Never accept an
// external destination or carry credentials from a URL into browser storage.
export function safeLoginReturnTo(input: string | null, origin: string): string | null {
  if (!input || !input.startsWith('/') || input.startsWith('//')) return null;
  try {
    const url = new URL(input, origin);
    if (url.origin !== origin || url.hash) return null;
    if (/^\/plan-sessions\/\d+\/complete$/.test(url.pathname)) return url.pathname;
    if (url.pathname !== '/youtube-watch' && url.pathname !== '/pdf-reader') return null;
    if (url.pathname === '/youtube-watch' && !/^[A-Za-z0-9_-]{11}$/.test(url.searchParams.get('video_id') || '')) return null;
    if (url.pathname === '/pdf-reader' && !url.searchParams.get('content_id')) return null;
    const query = new URLSearchParams();
    for (const key of ['video_id', 'content_id', 'club_id', 'lang', 'start', 'word', 'pid']) {
      const value = url.searchParams.get(key);
      if (value) query.set(key, value);
    }
    return url.pathname + (query.size ? `?${query}` : '');
  } catch { return null; }
}

export function consumeLoginReturnTo(): string {
  const saved = localStorage.getItem('xaana_login_return_to');
  localStorage.removeItem('xaana_login_return_to');
  try {
    const target = saved ? JSON.parse(saved) as { path?: string; at?: number } : null;
    if (typeof target?.at === 'number' && target.at <= Date.now() && Date.now() - target.at < 60 * 60 * 1000) {
      return safeLoginReturnTo(target.path || null, window.location.origin) || '/dashboard';
    }
  } catch { /* Ignore an invalid saved destination. */ }
  return '/dashboard';
}
