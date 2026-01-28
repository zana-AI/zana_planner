import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient, ApiError } from '../api/client';
import type { WeeklyReportData } from '../types';
import { DurationWheelPicker } from '../components/DurationWheelPicker';
import './FocusPage.css';

export function FocusPage() {
  const navigate = useNavigate();
  const [promisesData, setPromisesData] = useState<WeeklyReportData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [loadingPromises, setLoadingPromises] = useState(true);
  const [selectedPromiseId, setSelectedPromiseId] = useState<string>('');
  const [selectedDuration, setSelectedDuration] = useState<number>(25);

  useEffect(() => {
    // Load promises data
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
      .filter(([_, data]) => data.hours_promised > 0) // Only time-based promises
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
      
      // Request notification permission
      if ('Notification' in window && Notification.permission === 'default') {
        await Notification.requestPermission();
      }

      // Navigate back to dashboard
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

  const handleCancel = () => {
    navigate('/dashboard');
  };

  return (
    <div className="focus-page">
      <div className="focus-page-container">
        <div className="focus-page-header">
          <button 
            className="focus-back-button"
            onClick={handleCancel}
            aria-label="Go back to dashboard"
          >
            ← Back
          </button>
          <h1>Start Focus Session</h1>
        </div>

        {loadingPromises ? (
          <div className="focus-page-content">
            <div style={{ textAlign: 'center', padding: '2rem', color: 'rgba(255, 255, 255, 0.8)' }}>
              Loading promises...
            </div>
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
                {getAvailablePromises().map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.text}
                  </option>
                ))}
              </select>
            </div>

            <div className="focus-page-section">
              <label>Duration:</label>
              <DurationWheelPicker
                value={selectedDuration}
                onChange={setSelectedDuration}
                min={1}
                max={120}
              />
            </div>

            {error && <div className="focus-page-error" role="alert">{error}</div>}

            <div className="focus-page-actions">
              <button
                className="focus-confirm-button"
                onClick={handleStart}
                disabled={loading || !selectedPromiseId || loadingPromises}
              >
                {loading ? 'Starting...' : 'Start Focus Session'}
              </button>
              <button
                className="focus-cancel-button"
                onClick={handleCancel}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
