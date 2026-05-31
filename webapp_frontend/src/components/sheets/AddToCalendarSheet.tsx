import { Calendar, Download } from 'lucide-react';
import type { PlanSession } from '../../types';
import { BottomSheet } from '../ui/BottomSheet';
import { openGoogleCalendar, downloadIcs } from '../../utils/calendar';

interface AddToCalendarSheetProps {
  open: boolean;
  session: PlanSession | null;
  promiseText: string;
  onClose: () => void;
}

export function AddToCalendarSheet({ open, session, promiseText, onClose }: AddToCalendarSheetProps) {
  const handleGoogle = () => {
    if (session) openGoogleCalendar(session, promiseText);
    onClose();
  };
  const handleIcs = () => {
    if (session) downloadIcs(session, promiseText);
    onClose();
  };

  return (
    <BottomSheet open={open && !!session} onClose={onClose} title="Add to calendar" subtitle="Pick where to save this session">
      <div className="cal-choose-row">
        <button type="button" className="cal-choose-btn" onClick={handleGoogle}>
          <Calendar size={20} aria-hidden />
          <span>
            <span className="cal-choose-title">Google Calendar</span><br />
            <span className="cal-choose-sub">Opens a pre-filled event</span>
          </span>
        </button>
        <button type="button" className="cal-choose-btn" onClick={handleIcs}>
          <Download size={20} aria-hidden />
          <span>
            <span className="cal-choose-title">Apple / other calendar</span><br />
            <span className="cal-choose-sub">Downloads an .ics file</span>
          </span>
        </button>
      </div>
    </BottomSheet>
  );
}
