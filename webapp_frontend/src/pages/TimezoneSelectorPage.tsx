import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTelegramWebApp, getDevInitData } from '../hooks/useTelegramWebApp';
import { apiClient, ApiError } from '../api/client';

// Common timezones grouped by region
const TIMEZONES = [
  { group: 'Americas', zones: [
    'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
    'America/Toronto', 'America/Mexico_City', 'America/Sao_Paulo', 'America/Buenos_Aires'
  ]},
  { group: 'Europe', zones: [
    'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Rome', 'Europe/Madrid',
    'Europe/Amsterdam', 'Europe/Stockholm', 'Europe/Moscow', 'Europe/Istanbul'
  ]},
  { group: 'Asia', zones: [
    'Asia/Dubai', 'Asia/Karachi', 'Asia/Kolkata', 'Asia/Bangkok', 'Asia/Singapore',
    'Asia/Hong_Kong', 'Asia/Tokyo', 'Asia/Seoul', 'Asia/Shanghai'
  ]},
  { group: 'Pacific', zones: [
    'Australia/Sydney', 'Australia/Melbourne', 'Pacific/Auckland', 'Pacific/Honolulu'
  ]},
  { group: 'Africa', zones: [
    'Africa/Cairo', 'Africa/Johannesburg', 'Africa/Lagos', 'Africa/Nairobi'
  ]}
];

export function TimezoneSelectorPage() {
  const navigate = useNavigate();
  const { user, initData, isReady, hapticFeedback } = useTelegramWebApp();
  const [currentTimezone, setCurrentTimezone] = useState<string>('');
  const [selectedTimezone, setSelectedTimezone] = useState<string>('');
  const [detectedTimezone, setDetectedTimezone] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>('');
  const [success, setSuccess] = useState(false);
  const [customTimezone, setCustomTimezone] = useState<string>('');

  // Detect timezone on mount
  useEffect(() => {
    if (isReady) {
      try {
        const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        setDetectedTimezone(tz);
        setSelectedTimezone(tz);
      } catch (e) {
        console.warn('Failed to detect timezone:', e);
      }
    }
  }, [isReady]);

  // Fetch current timezone
  useEffect(() => {
    const fetchCurrentTimezone = async () => {
      if (!isReady) return;

      try {
        const authData = initData || getDevInitData();
        if (authData) {
          apiClient.setInitData(authData);
        }

        const userInfo = await apiClient.getUserInfo();
        setCurrentTimezone(userInfo.timezone || '');
        if (!selectedTimezone && userInfo.timezone && userInfo.timezone !== 'DEFAULT') {
          setSelectedTimezone(userInfo.timezone);
        }
      } catch (err) {
        console.error('Failed to fetch current timezone:', err);
        if (err instanceof ApiError && err.status === 401) {
          apiClient.clearAuth();
          window.dispatchEvent(new Event('logout'));
          navigate('/', { replace: true });
        }
      } finally {
        setLoading(false);
      }
    };

    fetchCurrentTimezone();
  }, [isReady, initData, navigate, selectedTimezone]);

  const handleSave = async () => {
    const tzToSave = customTimezone.trim() || selectedTimezone;
    
    if (!tzToSave) {
      setError('Please select or enter a timezone');
      return;
    }

    setSaving(true);
    setError('');
    setSuccess(false);

    try {
      const authData = initData || getDevInitData();
      if (authData) {
        apiClient.setInitData(authData);
      }

      // Use force=true to update even if timezone is already set
      await apiClient.updateTimezone(tzToSave, undefined, true);
      
      setSuccess(true);
      hapticFeedback('success');
      
      // Close after a short delay
      setTimeout(() => {
        navigate('/dashboard', { replace: true });
      }, 1500);
    } catch (err) {
      console.error('Failed to update timezone:', err);
      if (err instanceof ApiError) {
        setError(err.message || 'Failed to update timezone');
      } else {
        setError('Failed to update timezone. Please try again.');
      }
      hapticFeedback('error');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="page-container">
        <div className="loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>Select Timezone</h1>
      </div>

      <div className="timezone-selector">
        {currentTimezone && currentTimezone !== 'DEFAULT' && (
          <div className="timezone-info">
            <p>Current timezone: <strong>{currentTimezone}</strong></p>
          </div>
        )}

        {detectedTimezone && (
          <div className="timezone-suggestion">
            <p>Detected timezone: <strong>{detectedTimezone}</strong></p>
            <button
              className="button button-secondary"
              onClick={() => {
                setSelectedTimezone(detectedTimezone);
                setCustomTimezone('');
              }}
              disabled={saving}
            >
              Use Detected
            </button>
          </div>
        )}

        <div className="timezone-groups">
          <h3>Select from common timezones:</h3>
          {TIMEZONES.map(({ group, zones }) => (
            <div key={group} className="timezone-group">
              <h4>{group}</h4>
              <div className="timezone-buttons">
                {zones.map((tz) => (
                  <button
                    key={tz}
                    className={`timezone-button ${selectedTimezone === tz ? 'active' : ''}`}
                    onClick={() => {
                      setSelectedTimezone(tz);
                      setCustomTimezone('');
                    }}
                    disabled={saving}
                  >
                    {tz.replace('_', ' ')}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="timezone-custom">
          <h3>Or enter a custom timezone (IANA format):</h3>
          <input
            type="text"
            className="input"
            placeholder="e.g., America/New_York, Europe/London"
            value={customTimezone}
            onChange={(e) => {
              setCustomTimezone(e.target.value);
              if (e.target.value.trim()) {
                setSelectedTimezone('');
              }
            }}
            disabled={saving}
          />
          <p className="help-text">
            Enter a valid IANA timezone name. Examples: America/New_York, Europe/Paris, Asia/Tokyo
          </p>
        </div>

        {error && (
          <div className="error-message">{error}</div>
        )}

        {success && (
          <div className="success-message">
            ✓ Timezone updated successfully! Redirecting...
          </div>
        )}

        <div className="timezone-actions">
          <button
            className="button button-secondary"
            onClick={() => navigate('/dashboard', { replace: true })}
            disabled={saving}
          >
            Cancel
          </button>
          <button
            className="button button-primary"
            onClick={handleSave}
            disabled={saving || (!selectedTimezone && !customTimezone.trim())}
          >
            {saving ? 'Saving...' : 'Save Timezone'}
          </button>
        </div>
      </div>
    </div>
  );
}
