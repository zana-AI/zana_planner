import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient, ApiError } from '../api/client';
import type { WeeklyReportData } from '../types';
import { DurationWheelPicker } from '../components/DurationWheelPicker';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import './FocusPage.css';

export function FocusPage() {
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
        setError('Failed to load promises. Please try again.');
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
      setError('Please select a promise');
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
        setError('Failed to start focus session');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => navigate('/dashboard');

  return (
    <div className="focus-page">
      <div className="focus-page-container">
        <PageHeader title="Start Focus Session" showBack fallbackRoute="/dashboard" onBack={handleCancel} />

        {loadingPromises ? (
          <div className="focus-page-content">
            <div className="focus-loading-message">Loading promises...</div>
          </div>
        ) : (
          <div className="focus-page-content">
            <div className="focus-page-section">
              <label htmlFor="promise-select">Select Promise:</label>
              <select
                id="promise-select"
                value={selectedPromiseId}
                onChange={(e) => setSelectedPromiseId(e.target.value)}
                className="focus-page-select"
                disabled={loadingPromises}
              >
                <option value="">-- Choose a promise --</option>
                {getAvailablePromises().map((promise) => (
                  <option key={promise.id} value={promise.id}>
                    {promise.text}
                  </option>
                ))}
              </select>
            </div>

            <div className="focus-page-section">
              <label>Duration:</label>
              <DurationWheelPicker value={selectedDuration} onChange={setSelectedDuration} min={1} max={120} />
            </div>

            {error ? <div className="focus-page-error">{error}</div> : null}

            <div className="focus-page-actions">
              <Button variant="primary" fullWidth onClick={handleStart} disabled={loading || !selectedPromiseId || loadingPromises}>
                {loading ? 'Starting...' : 'Start Focus Session'}
              </Button>
              <Button variant="secondary" fullWidth onClick={handleCancel}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
