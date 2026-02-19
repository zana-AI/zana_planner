import { useEffect } from 'react';

interface UseTelegramBackButtonOptions {
  enabled?: boolean;
  onClick?: () => void;
}

/**
 * Binds Telegram native BackButton lifecycle with automatic cleanup.
 */
export function useTelegramBackButton({ enabled = true, onClick }: UseTelegramBackButtonOptions): void {
  useEffect(() => {
    const webApp = typeof window !== 'undefined' ? window.Telegram?.WebApp : undefined;
    const backButton = webApp?.BackButton;

    if (!enabled || !backButton) {
      return;
    }

    const handler = () => {
      if (onClick) {
        onClick();
      }
    };

    backButton.show();
    backButton.onClick(handler);

    return () => {
      backButton.offClick(handler);
      backButton.hide();
    };
  }, [enabled, onClick]);
}
