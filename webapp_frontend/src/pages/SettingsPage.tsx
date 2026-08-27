import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useTelegramWebApp, getDevInitData } from '../hooks/useTelegramWebApp';
import { apiClient, ApiError } from '../api/client';
import type { UserInfo } from '../types';
import { Button } from '../components/ui/Button';
import { applyServerLanguage, isReleased } from '../i18n';

// The account language always drives the Telegram bot, where all three already
// work. `isReleased()` decides whether it also switches this app's UI — see
// RELEASED_UI_LANGUAGES in src/i18n. Labels are endonyms on purpose: a language
// is listed in its own language, so it stays findable when the UI is unreadable.
const LANGUAGES = ['en', 'fa', 'fr'] as const;

export function SettingsPage() {
  const { t } = useTranslation();
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
        applyServerLanguage(info.language);
      } catch (err) {
        console.error('Failed to fetch user info:', err);
        if (err instanceof ApiError && err.status === 401) {
          apiClient.clearAuth();
          window.dispatchEvent(new Event('logout'));
          navigate('/', { replace: true });
        } else {
          setError(t('settings.loadFailed'));
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
      showSuccess(t('settings.displayNameUpdated'));
    } catch (err) {
      console.error('Failed to update display name:', err);
      setError(err instanceof ApiError ? err.message : t('settings.displayNameFailed'));
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
      // Switches the app UI too, for languages whose catalogs have shipped.
      applyServerLanguage(language);
      showSuccess(t('settings.languageUpdated'));
    } catch (err) {
      console.error('Failed to update language:', err);
      setError(err instanceof ApiError ? err.message : t('settings.languageFailed'));
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
      showSuccess(enabled ? t('settings.voiceModeEnabled') : t('settings.voiceModeDisabled'));
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
          <div className="loading-text">{t('common.loading')}</div>
        </div>
      </div>
    );
  }

  const displayTimezone =
    userInfo?.timezone && userInfo.timezone !== 'DEFAULT'
      ? userInfo.timezone
      : t('settings.timezoneNotSet');
  const voiceEnabled = userInfo?.voice_mode === 'enabled';
  const currentName = (userInfo?.first_name || '').trim();
  const canSaveName = !nameSaving && !!userInfo && displayNameDraft.trim() !== currentName;

  return (
    <div className="page-container">
      <div className="settings-sections">
        {/* Display name */}
        <section className="settings-section">
          <h3>{t('settings.displayName')}</h3>
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
              placeholder={t('settings.enterYourDisplayName')}
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
              {nameSaving ? t('common.saving') : t('common.save')}
            </Button>
          </div>
        </section>

        {/* Timezone */}
        <section className="settings-section">
          <h3>{t('settings.timezone')}</h3>
          <p className="settings-value">{displayTimezone.replace(/_/g, ' ')}</p>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => navigate('/timezone', { replace: false })}
          >
            {t('settings.changeTimezone')}
          </Button>
        </section>

        {/* Language */}
        <section className="settings-section">
          <h3>{t('settings.language')}</h3>
          <div className="settings-language-buttons">
            {LANGUAGES.map((value) => (
              <Button
                key={value}
                type="button"
                variant={userInfo?.language === value ? 'primary' : 'secondary'}
                size="sm"
                onClick={() => handleLanguageChange(value)}
                disabled={languageSaving}
              >
                {t(`language.${value}`)}
              </Button>
            ))}
          </div>
          <p className="settings-hint">
            {isReleased(userInfo?.language)
              ? t('settings.languageAppHint')
              : t('settings.languageBotHint')}
          </p>
        </section>

        {/* Voice mode */}
        <section className="settings-section">
          <h3>{t('settings.voiceMode')}</h3>
          <p className="settings-hint">
            {t('settings.voiceModeHint')}
          </p>
          <div className="settings-voice-toggle">
            <Button
              type="button"
              variant={!voiceEnabled ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => handleVoiceModeChange(false)}
              disabled={voiceModeSaving}
            >
              {t('settings.disabled')}
            </Button>
            <Button
              type="button"
              variant={voiceEnabled ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => handleVoiceModeChange(true)}
              disabled={voiceModeSaving}
            >
              {t('settings.enabled')}
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
