import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTelegramWebApp, getDevInitData } from '../hooks/useTelegramWebApp';
import { apiClient, ApiError } from '../api/client';
import type { UserInfo } from '../types';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';

const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'fa', label: 'Persian' },
  { value: 'fr', label: 'French' },
];

export function SettingsPage() {
  const navigate = useNavigate();
  const { initData, isReady, hapticFeedback } = useTelegramWebApp();
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [displayNameDraft, setDisplayNameDraft] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [nameSaving, setNameSaving] = useState(false);
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
        setDisplayNameDraft((info.first_name || '').trim());
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

  const handleDisplayNameSave = async () => {
    if (!userInfo) return;

    const nextName = displayNameDraft.trim();
    const currentName = (userInfo.first_name || '').trim();

    if (nextName === currentName) return;

    setNameSaving(true);
    setError('');
    try {
      const updated = await apiClient.updateUserSettings({
        first_name: nextName || null,
      });
      setUserInfo(updated);
      setDisplayNameDraft((updated.first_name || '').trim());
      showSuccess('Display name updated.');
    } catch (err) {
      console.error('Failed to update display name:', err);
      setError(err instanceof ApiError ? err.message : 'Failed to update display name.');
      hapticFeedback('error');
    } finally {
      setNameSaving(false);
    }
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
  const currentName = (userInfo?.first_name || '').trim();
  const canSaveName = !nameSaving && !!userInfo && displayNameDraft.trim() !== currentName;

  return (
    <div className="page-container">
      <PageHeader title="Settings" showBack />

      <div className="settings-sections">
        {/* Display name */}
        <section className="settings-section">
          <h3>Display name</h3>
          <p className="settings-value">{currentName || 'Not set'}</p>
          <div className="settings-name-row">
            <input
              type="text"
              className="settings-name-input"
              value={displayNameDraft}
              onChange={(e) => setDisplayNameDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleDisplayNameSave();
                }
              }}
              placeholder="Enter your display name"
              maxLength={64}
              disabled={nameSaving}
            />
            <Button
              type="button"
              variant="primary"
              size="md"
              className="settings-name-save"
              onClick={handleDisplayNameSave}
              disabled={!canSaveName}
            >
              {nameSaving ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </section>

        {/* Timezone */}
        <section className="settings-section">
          <h3>Timezone</h3>
          <p className="settings-value">{displayTimezone.replace(/_/g, ' ')}</p>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => navigate('/timezone', { replace: false })}
          >
            Change timezone
          </Button>
        </section>

        {/* Language */}
        <section className="settings-section">
          <h3>Language</h3>
          <div className="settings-language-buttons">
            {LANGUAGES.map(({ value, label }) => (
              <Button
                key={value}
                type="button"
                variant={userInfo?.language === value ? 'primary' : 'secondary'}
                size="sm"
                onClick={() => handleLanguageChange(value)}
                disabled={languageSaving}
              >
                {label}
              </Button>
            ))}
          </div>
        </section>

        {/* Voice mode */}
        <section className="settings-section">
          <h3>Voice mode</h3>
          <p className="settings-hint">
            When enabled, the bot can send voice messages in the chat.
          </p>
          <div className="settings-voice-toggle">
            <Button
              type="button"
              variant={!voiceEnabled ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => handleVoiceModeChange(false)}
              disabled={voiceModeSaving}
            >
              Disabled
            </Button>
            <Button
              type="button"
              variant={voiceEnabled ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => handleVoiceModeChange(true)}
              disabled={voiceModeSaving}
            >
              Enabled
            </Button>
          </div>
        </section>
      </div>

      {error && <div className="error-message">{error}</div>}
      {successMessage && (
        <div className="success-message">{successMessage}</div>
      )}
    </div>
  );
}
