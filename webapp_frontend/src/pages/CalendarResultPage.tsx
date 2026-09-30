import { useTranslation } from 'react-i18next';

export function CalendarResultPage() {
  const { t } = useTranslation();
  const status = new URLSearchParams(window.location.search).get('status');
  const added = status === 'added';
  const messageKey = status === 'denied' ? 'permissionDenied'
    : status === 'expired' ? 'linkExpired'
    : status === 'missing' ? 'sessionMissing'
    : 'addFailed';

  return (
    <main className="page-container" style={{ maxWidth: 560, margin: '3rem auto', textAlign: 'center' }}>
      <h1>{added ? t('calendar.addedTitle') : t('calendar.notAddedTitle')}</h1>
      <p>{added ? t('calendar.addedHint') : t(`calendar.${messageKey}`)}</p>
      <p><a href="https://t.me/xaana_bot?startapp=webapp">{t('calendar.backToXaana')}</a></p>
    </main>
  );
}
