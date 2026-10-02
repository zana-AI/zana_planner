import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../api/client';
import { clubReaderDestination } from '../utils/miniAppStart';

export function ClubReaderLaunch({ startParam, initData }: { startParam: string; initData: string }) {
  const { t, i18n } = useTranslation();
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const handled = useRef(-1);
  useEffect(() => {
    if (handled.current === attempt) return;
    handled.current = attempt;
    const destination = clubReaderDestination(startParam);
    if (!initData) { setError(t('content.openInTelegram')); return; }
    if (!destination) { setError(t('content.clubOpenFailed')); return; }
    setError('');
    // Install the live Telegram identity before this child's first request.
    apiClient.setInitData(initData);
    apiClient.openClubReader({ ...destination, language: i18n.language }).then(result => {
      if (!/^\/(youtube-watch|pdf-reader)\?/.test(result.path) || !result.session_token) throw new Error('Invalid reader');
      apiClient.setAuthToken(result.session_token);
      // Same-origin navigation keeps the reader within Telegram's Mini App.
      window.location.replace(result.path + '#session_token=' + encodeURIComponent(result.session_token));
    }).catch(() => setError(t('content.clubOpenFailed')));
  }, [attempt, initData, startParam, i18n.language, t]);
  return <main className="app">
    {error ? <><p role="alert">{error}</p>{initData && <button type="button" onClick={() => setAttempt(value => value + 1)}>{t('common.tryAgain')}</button>}</>
      : <p role="status">{t('common.loading')}</p>}
  </main>;
}
