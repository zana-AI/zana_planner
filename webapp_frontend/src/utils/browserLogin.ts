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
