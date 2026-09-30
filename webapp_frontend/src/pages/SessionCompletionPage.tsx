import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';
import { ApiError, apiClient } from '../api/client';
import type { UpcomingPlanSession } from '../types';
import './SessionCompletionPage.css';

export function SessionCompletionPage({ isAuthenticated }: { isAuthenticated: boolean }) {
  const { sessionId } = useParams();
  const { t, i18n } = useTranslation();
  const id = Number(sessionId);
  const [session, setSession] = useState<UpcomingPlanSession | null>(null);
  const [duration, setDuration] = useState('');
  const [state, setState] = useState<'loading' | 'ready' | 'missing' | 'unauthorized' | 'error'>('loading');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');

  useEffect(() => {
    if (!isAuthenticated || !Number.isSafeInteger(id) || id < 1) return;
    let active = true;
    apiClient.getPlanSession(id).then(result => {
      if (!active) return;
      setSession(result);
      setDuration(String(result.actual_duration_min ?? result.planned_duration_min ?? 30));
      setState('ready');
    }).catch(error => {
      if (!active) return;
      setState(error instanceof ApiError && error.status === 404 ? 'missing'
        : error instanceof ApiError && error.status === 401 ? 'unauthorized' : 'error');
    });
    return () => { active = false; };
  }, [isAuthenticated, id]);

  async function markDone() {
    const minutes = Number(duration);
    if (!session || session.status === 'done' || !Number.isSafeInteger(minutes) || minutes < 1 || minutes > 1440) return;
    setSaving(true);
    setSaveError('');
    try {
      const updated = await apiClient.updatePlanSessionStatus(session.id, 'done', false, minutes);
      setSession({ ...session, ...updated });
    } catch {
      setSaveError(t('sessionCompletion.saveFailed'));
    } finally {
      setSaving(false);
    }
  }

  function signIn() {
    localStorage.setItem('xaana_login_return_to', JSON.stringify({ path: window.location.pathname, at: Date.now() }));
    window.location.assign('/login');
  }

  const validDuration = Number.isSafeInteger(Number(duration)) && Number(duration) >= 1 && Number(duration) <= 1440;
  const scheduled = session?.planned_start
    ? new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(session.planned_start))
    : null;

  return <main className="session-completion-page">
    <section className="session-completion-card">
      <h1>{t('sessionCompletion.heading')}</h1>
      {(!isAuthenticated || state === 'unauthorized') ? <>
        <p>{t('sessionCompletion.signInHint')}</p>
        <button type="button" className="btn btn-primary" onClick={signIn}>{t('sessionCompletion.signIn')}</button>
      </> : state === 'loading' ? <p role="status">{t('common.loading')}</p>
        : state === 'missing' ? <p role="alert">{t('sessionCompletion.missing')}</p>
        : state === 'error' ? <p role="alert">{t('sessionCompletion.loadFailed')}</p>
        : session ? <>
          <h2>{session.title?.trim() || session.promise_text?.trim() || t('sessionCompletion.session')}</h2>
          {session.promise_text && session.title && <p className="session-completion-muted">{session.promise_text}</p>}
          {scheduled && <p>{t('sessionCompletion.scheduledFor', { date: scheduled })}</p>}
          {session.status === 'done' ? <p role="status" className="session-completion-done">{t('sessionCompletion.alreadyDone')}</p>
            : <>
              <p>{t('sessionCompletion.confirmHint')}</p>
              <label htmlFor="session-actual-minutes">{t('sessionCompletion.actualDuration')}</label>
              <div className="session-completion-duration">
                <input id="session-actual-minutes" type="number" min="1" max="1440" step="1" inputMode="numeric"
                  value={duration} onChange={event => setDuration(event.target.value)} />
                <span>{t('sessionCompletion.minutes')}</span>
              </div>
              {saveError && <p role="alert">{saveError}</p>}
              <button type="button" className="btn btn-primary" disabled={!validDuration || saving} onClick={markDone}>
                {saving ? t('common.saving') : t('sessionCompletion.markDone')}
              </button>
            </>}
        </> : null}
      <Link className="session-completion-back" to="/dashboard">{t('calendar.backToXaana')}</Link>
    </section>
  </main>;
}
