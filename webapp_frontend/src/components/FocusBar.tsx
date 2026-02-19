import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient } from '../api/client';
import type { FocusSession, WeeklyReportData } from '../types';
import './FocusBar.css';

interface FocusBarProps {
  promisesData: WeeklyReportData | null;
  onSessionComplete?: () => void;
}

export function FocusBar({ promisesData, onSessionComplete }: FocusBarProps) {
  const [currentSession, setCurrentSession] = useState<FocusSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [remainingSeconds, setRemainingSeconds] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const getCompletedSessionId = (): string | null => {
    try {
      return sessionStorage.getItem('focus_completed_session_id');
    } catch {
      return null;
    }
  };

  const setCompletedSessionId = (sessionId: string | null) => {
    try {
      if (sessionId) {
        sessionStorage.setItem('focus_completed_session_id', sessionId);
      } else {
        sessionStorage.removeItem('focus_completed_session_id');
      }
    } catch {
      // Ignore storage errors.
    }
  };

  const completedSessionIdRef = useRef<string | null>(getCompletedSessionId());

  const stopTimer = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  };

  const loadCurrentSession = useCallback(async () => {
    try {
      const session = await apiClient.getCurrentFocus();
      if (session) {
        const completedId = getCompletedSessionId();
        if (completedId === session.session_id) {
          setCurrentSession({ ...session, status: 'finished' });
        } else {
          setCurrentSession(session);
        }
      } else {
        setCompletedSessionId(null);
        completedSessionIdRef.current = null;
        setCurrentSession(null);
      }
    } catch (err) {
      console.error('Failed to load current session:', err);
    }
  }, []);

  useEffect(() => {
    loadCurrentSession();
  }, [loadCurrentSession]);

  const handleTimerComplete = useCallback(
    async (sessionId: string) => {
      if (completedSessionIdRef.current === sessionId || getCompletedSessionId() === sessionId) {
        return;
      }

      completedSessionIdRef.current = sessionId;
      setCompletedSessionId(sessionId);
      stopTimer();

      setCurrentSession((prev) => {
        if (prev && prev.session_id === sessionId) {
          return { ...prev, status: 'finished' };
        }
        return prev;
      });

      try {
        if ('Notification' in window) {
          if (Notification.permission === 'granted') {
            new Notification('Focus session complete', {
              body: 'Check Telegram to confirm your session.',
              icon: '/assets/zana_icon.png',
              tag: `focus-complete-${sessionId}`,
            });
          } else if (Notification.permission === 'default') {
            const permission = await Notification.requestPermission();
            if (permission === 'granted') {
              new Notification('Focus session complete', {
                body: 'Check Telegram to confirm your session.',
                icon: '/assets/zana_icon.png',
                tag: `focus-complete-${sessionId}`,
              });
            }
          }
        }
      } catch (err) {
        console.warn('Failed to show browser notification:', err);
      }

      setTimeout(() => {
        if (onSessionComplete) {
          onSessionComplete();
        }
      }, 100);
    },
    [onSessionComplete]
  );

  const updateRemainingTime = useCallback(() => {
    if (!currentSession || !currentSession.expected_end_utc) {
      setRemainingSeconds(0);
      return;
    }

    const now = new Date().getTime();
    const endTime = new Date(currentSession.expected_end_utc).getTime();
    const remaining = Math.max(0, Math.floor((endTime - now) / 1000));
    setRemainingSeconds(remaining);

    if (remaining === 0 && currentSession.status === 'running' && completedSessionIdRef.current !== currentSession.session_id) {
      stopTimer();
      handleTimerComplete(currentSession.session_id);
    }
  }, [currentSession, handleTimerComplete]);

  const startTimer = useCallback(() => {
    stopTimer();
    intervalRef.current = setInterval(updateRemainingTime, 1000);
  }, [updateRemainingTime]);

  useEffect(() => {
    if (currentSession && currentSession.status === 'running') {
      updateRemainingTime();
      startTimer();
    } else if (currentSession && currentSession.status === 'paused') {
      updateRemainingTime();
      stopTimer();
    } else {
      stopTimer();
    }

    return () => {
      stopTimer();
    };
  }, [currentSession?.session_id, currentSession?.status, currentSession?.expected_end_utc, updateRemainingTime, startTimer]);

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const getProgress = (): number => {
    if (!currentSession || !currentSession.planned_duration_minutes) return 0;
    const totalSeconds = currentSession.planned_duration_minutes * 60;
    const elapsed = totalSeconds - remainingSeconds;
    return Math.min(100, Math.max(0, (elapsed / totalSeconds) * 100));
  };

  const handlePause = async () => {
    if (!currentSession) return;
    setLoading(true);
    try {
      const session = await apiClient.pauseFocus(currentSession.session_id);
      setCurrentSession(session);
    } catch (err) {
      console.error('Failed to pause focus:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleResume = async () => {
    if (!currentSession) return;
    setLoading(true);
    try {
      const session = await apiClient.resumeFocus(currentSession.session_id);
      setCurrentSession(session);
    } catch (err) {
      console.error('Failed to resume focus:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    if (!currentSession) return;
    if (!confirm('Stop this focus session? It will not be logged.')) {
      return;
    }

    setLoading(true);
    try {
      await apiClient.stopFocus(currentSession.session_id);
      setCompletedSessionId(null);
      completedSessionIdRef.current = null;
      setCurrentSession(null);
    } catch (err) {
      console.error('Failed to stop focus:', err);
    } finally {
      setLoading(false);
    }
  };

  const getPromiseText = (): string => {
    if (!currentSession || !promisesData) return '';
    const promise = promisesData.promises[currentSession.promise_id];
    return promise?.text || currentSession.promise_text || `Promise #${currentSession.promise_id}`;
  };

  if (!currentSession) {
    return null;
  }

  const progress = getProgress();
  const isRunning = currentSession.status === 'running';
  const isPaused = currentSession.status === 'paused';
  const isFinished = currentSession.status === 'finished';

  return (
    <div className={`focus-bar focus-bar-active ${isRunning ? 'running' : isPaused ? 'paused' : 'finished'}`}>
      <div className="focus-bar-content">
        <div className="focus-session-info">
          <div className="focus-promise-name">{getPromiseText()}</div>
          <div className="focus-timer-display">
            <div className="focus-time">{formatTime(remainingSeconds)}</div>
            <div className="focus-progress-ring">
              <svg viewBox="0 0 100 100" className="focus-progress-svg">
                <circle cx="50" cy="50" r="45" className="focus-progress-bg" />
                <circle
                  cx="50"
                  cy="50"
                  r="45"
                  className="focus-progress-fill"
                  style={{
                    strokeDasharray: `${2 * Math.PI * 45}`,
                    strokeDashoffset: `${2 * Math.PI * 45 * (1 - progress / 100)}`,
                  }}
                />
              </svg>
            </div>
          </div>
        </div>

        <div className="focus-controls">
          {isRunning ? (
            <>
              <button className="focus-control-btn pause" onClick={handlePause} disabled={loading}>
                Pause
              </button>
              <button className="focus-control-btn stop" onClick={handleStop} disabled={loading}>
                Stop
              </button>
            </>
          ) : null}

          {isPaused ? (
            <>
              <button className="focus-control-btn resume" onClick={handleResume} disabled={loading}>
                Resume
              </button>
              <button className="focus-control-btn stop" onClick={handleStop} disabled={loading}>
                Stop
              </button>
            </>
          ) : null}

          {isFinished ? (
            <>
              <div className="focus-complete-message">Session complete. Check Telegram to confirm.</div>
              <button
                className="focus-control-btn dismiss"
                onClick={() => {
                  setCurrentSession(null);
                  setCompletedSessionId(null);
                  completedSessionIdRef.current = null;
                }}
                disabled={loading}
              >
                Dismiss
              </button>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
