import { useEffect, useState, useCallback } from 'react';
import type { TelegramWebApp, TelegramUser } from '../types';

// Module-level flag: SDK init must only run once across all hook instances.
// Calling tg.ready() / tg.expand() / setHeaderColor() from multiple components
// simultaneously causes Telegram's mobile WebView to malfunction (blank screen).
let _sdkInitialized = false;

interface UseTelegramWebAppResult {
  webApp: TelegramWebApp | null;
  user: TelegramUser | null;
  initData: string;
  isReady: boolean;
  colorScheme: 'light' | 'dark';
  expand: () => void;
  close: () => void;
  hapticFeedback: (type: 'success' | 'error' | 'warning' | 'light' | 'medium' | 'heavy') => void;
  isTelegramMiniApp: boolean;
  canUseBackButton: boolean;
}

/**
 * Hook to access and interact with the Telegram Web App SDK.
 * Provides user info, init data for API auth, and utility functions.
 */
export function useTelegramWebApp(): UseTelegramWebAppResult {
  const [webApp, setWebApp] = useState<TelegramWebApp | null>(null);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    const tg = window.Telegram?.WebApp;

    if (tg) {
      setWebApp(tg);

      // Only run one-time SDK setup calls once across all hook instances.
      // This hook is used in 14+ components; calling ready()/expand()/setHeaderColor()
      // from every mount simultaneously causes Telegram's mobile WebView to malfunction.
      if (\!_sdkInitialized) {
        _sdkInitialized = true;

        // Tell Telegram we're ready
        tg.ready();

        // Expand to full height
        tg.expand();

        // Set theme colors to match our dark theme (only if supported)
        try {
          if (tg.version && parseFloat(tg.version) >= 6.1) {
            tg.setHeaderColor('#0b1020');
            tg.setBackgroundColor('#0b1020');
          }
        } catch (e) {
          // Ignore if not supported
        }
      }

      setIsReady(true);
    } else {
      // Development mode - no Telegram SDK available
      console.warn('Telegram WebApp SDK not available. Running in development mode.');
      setIsReady(true);
    }
  }, []);

  const expand = useCallback(() => {
    webApp?.expand();
  }, [webApp]);

  const close = useCallback(() => {
    webApp?.close();
  }, [webApp]);

  const hapticFeedback = useCallback((type: 'success' | 'error' | 'warning' | 'light' | 'medium' | 'heavy') => {
    if (\!webApp?.HapticFeedback) return;

    // Check if HapticFeedback is supported (version 6.1+)
    try {
      if (webApp.version && parseFloat(webApp.version) < 6.1) {
        return; // Not supported in older versions
      }
    } catch (e) {
      // If version check fails, try anyway
    }

    switch (type) {
      case 'success':
      case 'error':
      case 'warning':
        webApp.HapticFeedback.notificationOccurred(type);
        break;
      case 'light':
      case 'medium':
      case 'heavy':
        webApp.HapticFeedback.impactOccurred(type);
        break;
    }
  }, [webApp]);

  return {
    webApp,
    user: webApp?.initDataUnsafe?.user || null,
    initData: webApp?.initData || '',
    isReady,
    colorScheme: webApp?.colorScheme || 'dark',
    expand,
    close,
    hapticFeedback,
    isTelegramMiniApp: \!\!webApp,
    canUseBackButton: \!\!webApp?.BackButton,
  };
}

/**
 * Get init data for development/testing.
 * In production, this comes from Telegram SDK.
 */
export function getDevInitData(): string {
  // For development, you can set this in localStorage
  return localStorage.getItem('dev_init_data') || '';
}
