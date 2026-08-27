import { useTranslation } from 'react-i18next';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient, ApiError } from '../api/client';
import type { WeeklyReportData } from '../types';
import { DurationWheelPicker } from '../components/DurationWheelPicker';
import { Button } from '../components/ui/Button';
import './FocusPage.css';

export function FocusPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [promisesData, setPromisesData] = useState<WeeklyReportData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [loadingPromises, setLoadingPromises] = useState(true);
  const [selectedPromiseId, setSelectedPromiseId] = useState('');
  const [selectedDuration, setSelectedDuration] = useState(25);

  useEffect(() => {
    const loadPromises = async () => {
      setLoadingPromises(true);
      try {
        const data = await apiClient.getWeeklyReport();
        setPromisesData(data);
      } catch (err) {
        console.error('Failed to load promises:', err);
        setError(t('focus.failedToLoadPromisesPleaseTryAgain'));
      } finally {
        setLoadingPromises(false);
      }
    };
    loadPromises();
  }, []);

  const getAvailablePromises = (): Array<{ id: string; text: string }> => {
    if (!promisesData) return [];
    return Object.entries(promisesData.promises)
      .filter(([_, data]) => data.hours_promised > 0)
      .map(([id, data]) => ({ id, text: data.text }));
  };

  const handleStart = async () => {
    if (!selectedPromiseId) {
      setError(t('focus.pleaseSelectAPromise'));
      return;
    }

    setLoading(true);
    setError('');
    try {
      await apiClient.startFocus(selectedPromiseId, selectedDuration);
      if ('Notification' in window && Notification.permission === 'default') {
        await Notification.requestPermission();
      }
      navigate('/dashboard');
    } catch (err) {
      console.error('Failed to start focus:', err);
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(t('focus.failedToStartFocusSession'));
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => navigate('/dashboard');

  return (
    <div className="focus-page">
      <div className="focus-page-container">
        {loadingPromises ? (
          <div className="focus-page-content">
            <div className="focus-loading-message">{t('focus.loadingPromises')}</div>
          </div>
        ) : (
          <div className="focus-page-content">
            <div className="focus-page-section">
              <label htmlFor="promise-select">{t('focus.selectPromise')}</label>
              <select
                id="promise-select"
                value={selectedPromiseId}
                onChange={(e) => setSelectedPromiseId(e.target.value)}
                className="focus-page-select"
                disabled={loadingPromises}
              >
                <option value="">{t('focus.chooseAPromise')}</option>
                {getAvailablePromises().map((promise) => (
                  <option key={promise.id} value={promise.id}>
                    {promise.text}
                  </option>
                ))}
              </select>
            </div>

            <div className="focus-page-section">
              <label>{t('focus.duration')}</label>
              <DurationWheelPicker value={selectedDuration} onChange={setSelectedDuration} min={1} max={120} />
            </div>

            {error ? <div className="focus-page-error">{error}</div> : null}

            <div className="focus-page-actions">
              <Button variant="primary" fullWidth onClick={handleStart} disabled={loading || !selectedPromiseId || loadingPromises}>
                {loading ? t('focus.starting') : t('focus.startFocusSession')}
              </Button>
              <Button variant="secondary" fullWidth onClick={handleCancel}>{t('focus.cancel')}</Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
