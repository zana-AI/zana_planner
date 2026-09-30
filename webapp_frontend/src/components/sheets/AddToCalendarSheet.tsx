import { useTranslation } from 'react-i18next';
import { useEffect, useState } from 'react';
import { Calendar, Download } from 'lucide-react';
import type { PlanSession } from '../../types';
import { BottomSheet } from '../ui/BottomSheet';
import { openGoogleCalendar, downloadIcs } from '../../utils/calendar';
import { apiClient } from '../../api/client';

interface AddToCalendarSheetProps {
  open: boolean;
  session: PlanSession | null;
  promiseText: string;
  onClose: () => void;
}

export function AddToCalendarSheet({ open, session, promiseText, onClose }: AddToCalendarSheetProps) {
  const { t } = useTranslation();
  const [addingDirectly, setAddingDirectly] = useState(false);
  const [directError, setDirectError] = useState('');
  const [directAvailable, setDirectAvailable] = useState(false);
  useEffect(() => {
    if (!open) return;
    let active = true;
    apiClient.getGoogleCalendarAvailability()
      .then(({ enabled }) => { if (active) setDirectAvailable(enabled); })
      .catch(() => { if (active) setDirectAvailable(false); });
    return () => { active = false; };
  }, [open]);
  const handleDirectGoogle = async () => {
    if (!session || addingDirectly) return;
    setAddingDirectly(true);
    setDirectError('');
    try {
      const { url } = await apiClient.getGoogleCalendarAuthorizationUrl(session.id);
      if (window.Telegram?.WebApp?.openLink) window.Telegram.WebApp.openLink(url);
      else window.location.assign(url);
      onClose();
    } catch {
      setDirectError(t('calendar.directAddFailed'));
    } finally {
      setAddingDirectly(false);
    }
  };
  const handleGoogle = () => {
    if (session) openGoogleCalendar(session, promiseText);
    onClose();
  };
  const handleIcs = () => {
    if (session) downloadIcs(session, promiseText);
    onClose();
  };

  return (
    <BottomSheet open={open && !!session} onClose={onClose} title={t('calendar.addToCalendar')} subtitle="Pick where to save this session">
      <div className="cal-choose-row">
        {directAvailable && <button type="button" className="cal-choose-btn" onClick={handleDirectGoogle} disabled={addingDirectly}>
          <Calendar size={20} aria-hidden />
          <span>
            <span className="cal-choose-title">{t('calendar.addDirectly')}</span><br />
            <span className="cal-choose-sub">{t('calendar.directAddHint')}</span>
          </span>
        </button>}
        <button type="button" className="cal-choose-btn" onClick={handleGoogle}>
          <Calendar size={20} aria-hidden />
          <span>
            <span className="cal-choose-title">{t('calendar.openGoogleCalendar')}</span><br />
            <span className="cal-choose-sub">{t('calendar.opensAPreFilledEvent')}</span>
          </span>
        </button>
        <button type="button" className="cal-choose-btn" onClick={handleIcs}>
          <Download size={20} aria-hidden />
          <span>
            <span className="cal-choose-title">{t('calendar.appleOtherCalendar')}</span><br />
            <span className="cal-choose-sub">{t('calendar.downloadsAnIcsFile')}</span>
          </span>
        </button>
      </div>
      <p className="cal-choose-sub"><a href="/privacy" target="_blank" rel="noopener noreferrer">{t('calendar.privacyPolicy')}</a></p>
      {directError && <p role="alert" className="error-message">{directError}</p>}
    </BottomSheet>
  );
}
