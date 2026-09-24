import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../api/client';
import { parseBrowserLoginCode } from '../utils/browserLogin';

// Read once, outside React's StrictMode remounts. Strip the secret immediately;
// it stays in memory, not history, storage, referrers or server request URLs.
const initialCode = window.location.pathname === '/login'
  ? parseBrowserLoginCode(window.location.href, window.location.origin) : null;
if (window.location.pathname === '/login' && window.location.hash) {
  window.history.replaceState(null, '', '/login');
}

type Account = { user_id: string; first_name: string | null; username: string | null };

export function BrowserLoginPage() {
  const { t } = useTranslation();
  const [code, setCode] = useState(initialCode);
  const [previewAttempt, setPreviewAttempt] = useState(0);
  const [input, setInput] = useState('');
  const [bot, setBot] = useState<string | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const inTelegram = !!window.Telegram?.WebApp?.initData;

  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/auth/bot-username', { signal: controller.signal })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => setBot(data.bot_username))
      .catch(() => {});
    return () => controller.abort();
  }, []);

  useEffect(() => {
    setAccount(null);
    if (!code || inTelegram) return;
    const controller = new AbortController();
    setBusy(true);
    setError('');
    fetch('/api/auth/browser-login/preview', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }), signal: controller.signal,
    }).then(async response => {
      if (!response.ok) throw new Error(response.status === 401 ? 'expired' : 'failed');
      return response.json();
    }).then(data => { if (!controller.signal.aborted) setAccount(data); }).catch(err => {
      if (!controller.signal.aborted) setError(err.message === 'expired' ? 'expired' : 'failed');
    }).finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [code, inTelegram, previewAttempt]);

  async function confirm() {
    if (!code || !account || busy) return;
    setBusy(true);
    setError('');
    try {
      const response = await fetch('/api/auth/browser-login/redeem', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, expected_user_id: Number(account.user_id) }),
      });
      if (!response.ok) throw new Error(response.status === 401 ? 'expired' : 'failed');
      const data = await response.json();
      // Keep the current account until confirmation succeeds. Reload so no old
      // account's React state or in-flight requests can bleed into the new one.
      apiClient.setAuthToken(data.session_token);
      window.location.replace('/dashboard');
    } catch (err) {
      setError(err instanceof Error && err.message === 'expired' ? 'expired' : 'failed');
      setBusy(false);
    }
  }

  return (
    <main className="browser-login-page">
      <section className="browser-login-card" aria-labelledby="browser-login-title">
        <h1 id="browser-login-title">{t('accountSwitch.title')}</h1>
        {inTelegram ? <p>{t('accountSwitch.miniApp')}</p> : <>
          {!account && <>
          <p>{t('accountSwitch.description')}</p>
          <ol>
            <li>{t('accountSwitch.chooseAccount')}</li>
            <li>{t('accountSwitch.requestLink')}</li>
            <li>{t('accountSwitch.openLink')}</li>
          </ol>
          {bot && <a className="btn btn-primary" href={`https://t.me/${bot}?start=browser_login`} target="_blank" rel="noopener noreferrer">{t('accountSwitch.openBot')}</a>}
          </>}
          <p className="browser-login-note">{t('accountSwitch.linkSafety')}</p>
          {error && <p role="alert">{t(`accountSwitch.${error}`)}</p>}
          {busy && <p role="status">{t('common.loading')}</p>}
          {account && <div className="browser-login-confirm">
            <h2>{account.first_name || account.username || t('accountSwitch.telegramAccount')}</h2>
            {account.username && <p dir="ltr">@{account.username}</p>}
            <p>{t('accountSwitch.telegramId', { id: account.user_id })}</p>
            <p>{t('accountSwitch.confirmHint')}</p>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={confirm}>{t('accountSwitch.confirm')}</button>
          </div>}
          {!account ? <form onSubmit={event => {
            event.preventDefault();
            const next = parseBrowserLoginCode(input, window.location.origin);
            if (!next) { setError('invalid'); return; }
            setAccount(null);
            setError('');
            setCode(next);
            setPreviewAttempt(attempt => attempt + 1);
            setInput('');
          }}>
            <label htmlFor="browser-login-link">{t('accountSwitch.pasteLink')}</label>
            <input id="browser-login-link" type="password" value={input} onChange={event => setInput(event.target.value)} autoComplete="off" spellCheck={false} />
            <button type="submit" className="btn" disabled={!input.trim() || busy}>{t('accountSwitch.checkLink')}</button>
          </form> : <button type="button" className="btn" disabled={busy} onClick={() => {
            setCode(null); setAccount(null); setError('');
          }}>{t('accountSwitch.changeLink')}</button>}
        </>}
        <a href="/">{t('common.cancel')}</a>
      </section>
    </main>
  );
}
