import { useEffect, useState } from 'react';
import { Check, Pause, Play } from 'lucide-react';
import { apiClient } from '../../api/client';
import { BottomSheet } from '../ui/BottomSheet';
import { Button } from '../ui/Button';

interface FocusSheetProps {
  open: boolean;
  promiseId: string;
  promiseText: string;
  onClose: () => void;
  onComplete: (message: string) => void;
  durationMinutes?: number;
}

export function FocusSheet({
  open,
  promiseId,
  promiseText,
  onClose,
  onComplete,
  durationMinutes = 25,
}: FocusSheetProps) {
  const totalSeconds = durationMinutes * 60;
  const [remaining, setRemaining] = useState(totalSeconds);
  const [running, setRunning] = useState(true);

  useEffect(() => {
    if (!open) return;
    setRemaining(totalSeconds);
    setRunning(true);
  }, [open, totalSeconds]);

  useEffect(() => {
    if (!open || !running || remaining <= 0) return;
    const timer = window.setInterval(() => {
      setRemaining((value) => Math.max(0, value - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [open, running, remaining]);

  const mm = String(Math.floor(remaining / 60)).padStart(2, '0');
  const ss = String(remaining % 60).padStart(2, '0');
  const pct = 1 - remaining / totalSeconds;
  const radius = 92;
  const circumference = 2 * Math.PI * radius;

  const handleComplete = async () => {
    try {
      await apiClient.startFocus(promiseId, durationMinutes);
      onComplete('Focus session logged');
      onClose();
    } catch {
      onComplete('Focus session finished');
      onClose();
    }
  };

  return (
    <BottomSheet open={open} onClose={onClose} title="Focus" subtitle={promiseText}>
      <section className="focus-ring">
        <svg width="220" height="220" aria-hidden="true">
          <defs>
            <linearGradient id="focus-ring-gradient" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#67E8F9" />
              <stop offset="1" stopColor="#A78BFA" />
            </linearGradient>
          </defs>
          <circle cx="110" cy="110" r={radius} fill="none" stroke="rgba(230,234,245,0.07)" strokeWidth="6" />
          <circle
            cx="110"
            cy="110"
            r={radius}
            fill="none"
            stroke="url(#focus-ring-gradient)"
            strokeWidth="6"
            strokeDasharray={circumference}
            strokeDashoffset={circumference * (1 - pct)}
            strokeLinecap="round"
          />
        </svg>
        <div className="center">
          <div>
            <div className="time">{mm}:{ss}</div>
            <div className="label">{running ? 'Focusing' : remaining === 0 ? 'Complete' : 'Paused'}</div>
          </div>
        </div>
      </section>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <Button variant="secondary" onClick={() => setRunning((value) => !value)}>
          {running ? <Pause size={14} /> : <Play size={14} />}
          {running ? 'Pause' : 'Resume'}
        </Button>
        <Button variant="primary" onClick={handleComplete}>
          <Check size={14} />
          Finish
        </Button>
      </div>
    </BottomSheet>
  );
}
