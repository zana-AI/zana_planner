import { getDevInitData } from './useTelegramWebApp';
import type { SessionMode } from '../types';

/**
 * Resolves the current auth context to drive mini-app specific UX decisions.
 */
export function useSessionMode(): SessionMode {
  const telegramWebApp = typeof window !== 'undefined' ? window.Telegram?.WebApp : undefined;
  const initData = telegramWebApp?.initData || '';
  const isTelegramMiniApp = !!telegramWebApp;
  const token = localStorage.getItem('telegram_auth_token');
  const hasTelegramData = !!(initData || getDevInitData());

  if (isTelegramMiniApp && hasTelegramData) {
    return 'telegram_mini_app';
  }
  if (token) {
    return 'browser_token';
  }
  return 'unauthenticated';
}
