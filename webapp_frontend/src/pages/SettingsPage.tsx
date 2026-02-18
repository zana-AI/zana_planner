import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTelegramWebApp, getDevInitData } from '../hooks/useTelegramWebApp';
import { apiClient, ApiError } from '../api/client';
import type { UserInfo } from '../types';

const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'fa', label: 'Persian' },
  { value: 'fr', label: 'French' },
];

export function SettingsPage() {
  const navigate = useNavigate();
  const { initData, isReady, hapticFeedback } = useTelegramWebApp();
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [languageSaving, setLanguageSaving] = useState(false);
  const [voiceModeSaving, setVoiceModeSaving] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string>('');

  useEffect(() => {
    const fetchUserInfo = async () => {
      if (!isReady) return;
      try {
        const authData = initData || getDevInitData();
        if (authData) {
          apiClient.setInitData(authData);
        }
        const info = await apiClient.getUserInfo();
        setUserInfo(info);
      } catch (err) {
        console.error('Failed to fetch user info:', err);
        if (err instanceof ApiError && err.status === 401) {
          apiClient.clearAuth();
          window.dispatchEvent(new Event('logout'));
          navigate('/', { replace: true });
        } else {
          setError('Failed to load settings.');
        }
      } finally {
        setLoading(false);
      }
    };
    fetchUserInfo();
  }, [isReady, initData, navigate]);

  const showSuccess = (message: string) => {
    setSuccessMessage(message);
    hapticFeedback('success');
    setTimeout(() => setSuccessMessage(''), 2500);
  };

  const handleLanguageChange = async (language: string) => {
    if (!userInfo || language === userInfo.language) return;
    setLanguageSaving(true);
    setError('');
    try {
      await apiClient.updateUserSettings({ language });
      setUserInfo((prev) => (prev ? { ...prev, language } : null));
      showSuccess('Language updated.');
    } catch (err) {
      console.error('Failed to update language:', err);
      setError(err instanceof ApiError ? err.message : 'Failed to update language.');
      hapticFeedback('error');
    } finally {
      setLanguageSaving(false);
    }
  };

  const handleVoiceModeChange = async (enabled: boolean) => {
    const value = enabled ? 'enabled' : 'disabled';
    setVoiceModeSaving(true);
    setError('');
    try {
      await apiClient.updateUserSettings({ voice_mode: value });
      setUserInfo((prev) => (prev ? { ...prev, voice_mode: value } : null));
      showSuccess(enabled ? 'Voice mode enabled.' : 'Voice mode disabled.');
    } catch (err) {
      console.error('Failed to update voice mode:', err);
      setError(err instanceof ApiError ? err.message : 'Failed to update voice mode.');
      hapticFeedback('error');
    } finally {
      setVoiceModeSaving(false);
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

  const displayTimezone =
    userInfo?.timezone && userInfo.timezone !== 'DEFAULT'
      ? userInfo.timezone
      : 'Not set';
  const voiceEnabled = userInfo?.voice_mode === 'enabled';

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>Settings</h1>
      </div>

      <div className="settings-sections">
        {/* Timezone */}
        <section className="settings-section">
          <h3>Timezone</h3>
          <p className="settings-value">{displayTimezone.replace(/_/g, ' ')}</p>
          <button
            type="button"
            className="button button-secondary"
            onClick={() => navigate('/timezone', { replace: false })}
          >
            Change timezone
          </button>
        </section>

        {/* Language */}
        <section className="settings-section">
          <h3>Language</h3>
          <div className="settings-language-buttons">
            {LANGUAGES.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                className={`button ${userInfo?.language === value ? 'button-primary' : 'button-secondary'}`}
                onClick={() => handleLanguageChange(value)}
                disabled={languageSaving}
              >
                {label}
              </button>
            ))}
          </div>
        </section>

        {/* Voice mode (Xaana) */}
        <section className="settings-section">
          <h3>Voice mode (Xaana)</h3>
          <p className="settings-hint">
            When enabled, the bot can send voice messages in the chat.
          </p>
          <div className="settings-voice-toggle">
            <button
              type="button"
              className={`button ${!voiceEnabled ? 'button-primary' : 'button-secondary'}`}
              onClick={() => handleVoiceModeChange(false)}
              disabled={voiceModeSaving}
            >
              Disabled
            </button>
            <button
              type="button"
              className={`button ${voiceEnabled ? 'button-primary' : 'button-secondary'}`}
              onClick={() => handleVoiceModeChange(true)}
              disabled={voiceModeSaving}
            >
              Enabled
            </button>
          </div>
        </section>
      </div>

      {error && <div className="error-message">{error}</div>}
      {successMessage && (
        <div className="success-message">{successMessage}</div>
      )}

      <div className="settings-actions">
        <button
          type="button"
          className="button button-secondary"
          onClick={() => navigate('/dashboard', { replace: true })}
        >
          Back to Dashboard
        </button>
      </div>
    </div>
  );
}
