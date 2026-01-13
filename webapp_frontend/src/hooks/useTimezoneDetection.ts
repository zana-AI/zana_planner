import { useEffect, useRef } from 'react';
import { apiClient } from '../api/client';

/**
 * Hook to automatically detect and set user timezone when Mini App loads.
 * Only sends timezone if user hasn't set one yet.
 * 
 * @param enabled - Whether timezone detection is enabled (should be true when user is authenticated)
 */
export function useTimezoneDetection(enabled: boolean = true) {
  const hasDetected = useRef(false);

  useEffect(() => {
    if (!enabled || hasDetected.current) {
      return;
    }

    // Only run once
    hasDetected.current = true;

    // Detect timezone using JavaScript
    const detectAndSetTimezone = async () => {
      try {
        // Get IANA timezone name (best thing to store)
        const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        
        // Get UTC offset (minutes) - useful but changes with DST
        // Note: getTimezoneOffset() returns negative for ahead of UTC, positive for behind
        const offsetMin = new Date().getTimezoneOffset();

        // Send to backend
        const result = await apiClient.updateTimezone(tz, offsetMin);
        
        if (result.status === 'success') {
          console.log(`[Timezone] Detected and set timezone: ${tz} (offset: ${offsetMin} minutes)`);
        } else {
          console.log(`[Timezone] Timezone already set to: ${result.timezone}`);
        }
      } catch (error) {
        // Silently fail - timezone detection is not critical
        // User can still manually set timezone via /settimezone command
        console.warn('[Timezone] Failed to detect/set timezone:', error);
      }
    };

    // Small delay to ensure API client is initialized and authenticated
    const timeoutId = setTimeout(detectAndSetTimezone, 1000);

    return () => {
      clearTimeout(timeoutId);
    };
  }, [enabled]);
}
