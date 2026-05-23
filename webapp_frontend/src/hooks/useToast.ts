import { useCallback, useEffect, useState } from 'react';

export function useToast(durationMs = 1800) {
  const [message, setMessage] = useState<string | null>(null);

  const showToast = useCallback((text: string) => {
    setMessage(text);
  }, []);

  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(() => setMessage(null), durationMs);
    return () => window.clearTimeout(timer);
  }, [durationMs, message]);

  return { message, showToast };
}
