import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient, ApiError } from '../api/client';
import type { FocusSession, WeeklyReportData } from '../types';
import './FocusBar.css';

// Mobile breakpoint constant - matches CSS media query
const MOBILE_BREAKPOINT = 768;

interface FocusBarProps {
  promisesData: WeeklyReportData | null;
  onSessionComplete?: () => void;
}

export function FocusBar({ promisesData, onSessionComplete }: FocusBarProps) {
  const navigate = useNavigate();
  const [currentSession, setCurrentSession] = useState<FocusSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [selectedPromiseId, setSelectedPromiseId] = useState<string>('');
  const [selectedDuration, setSelectedDuration] = useState<number>(25);
  const [showPromisePicker, setShowPromisePicker] = useState(false);
  const [remainingSeconds, setRemainingSeconds] = useState<number>(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [isMobile, setIsMobile] = useState(false);
  const completionHandledRef = useRef<boolean>(false);

  // Detect mobile viewport
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth <= MOBILE_BREAKPOINT);
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    
    return () => {
      window.removeEventListener('resize', checkMobile);
    };
  }, []);

  // Close modal when switching from desktop to mobile
  useEffect(() => {
    if (isMobile && showPromisePicker) {
      setShowPromisePicker(false);
    }
  }, [isMobile, showPromisePicker]);

  // Load current session on mount
  useEffect(() => {
    loadCurrentSession();
  }, []);

  // Reset completion flag when session changes
  useEffect(() => {
    completionHandledRef.current = false;
  }, [currentSession?.session_id]);

  const loadCurrentSession = async () => {
    try {
      const session = await apiClient.getCurrentFocus();
      if (session) {
        setCurrentSession(session);
        if (session.promise_id && !selectedPromiseId) {
          setSelectedPromiseId(session.promise_id);
        }
      }
    } catch (err) {
      console.error('Failed to load current session:', err);
    }
  };

  const stopTimer = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  };

  const handleTimerComplete = useCallback(async (sessionId: string) => {
    // Prevent multiple calls
    if (completionHandledRef.current) {
      return;
    }
    completionHandledRef.current = true;
    
    stopTimer();
    
    // Show completion state - backend will send Telegram notification
    setCurrentSession((prev) => {
      if (prev && prev.session_id === sessionId) {
        return { ...prev, status: 'finished' };
      }
      return prev;
    });
    
    // Request browser notification if available (do this first, before any refresh)
    try {
      if ('Notification' in window) {
        if (Notification.permission === 'granted') {
          new Notification('🎉 Focus session complete!', {
            body: 'Check Telegram for confirmation options.',
            icon: '/assets/zana_icon.png',
            tag: `focus-complete-${sessionId}`, // Prevent duplicate notifications
          });
        } else if (Notification.permission === 'default') {
          // Request permission if not yet asked
          const permission = await Notification.requestPermission();
          if (permission === 'granted') {
            new Notification('🎉 Focus session complete!', {
              body: 'Check Telegram for confirmation options.',
              icon: '/assets/zana_icon.png',
              tag: `focus-complete-${sessionId}`,
            });
          }
        }
      }
    } catch (err) {
      console.warn('Failed to show browser notification:', err);
      // Don't fail the completion flow if notification fails
    }
    
    // Call onSessionComplete callback (which may trigger refresh) after notification
    // Use setTimeout to ensure notification is shown before any potential page refresh
    setTimeout(() => {
      if (onSessionComplete) {
        onSessionComplete();
      }
    }, 100);
  }, [onSessionComplete]);

  const updateRemainingTime = useCallback(() => {
    if (!currentSession || !currentSession.expected_end_utc) {
      setRemainingSeconds(0);
      return;
    }

    const now = new Date().getTime();
    const endTime = new Date(currentSession.expected_end_utc).getTime();
    const remaining = Math.max(0, Math.floor((endTime - now) / 1000));

    setRemainingSeconds(remaining);

    // If timer completed, handle it (only once)
    if (remaining === 0 && currentSession.status === 'running' && !completionHandledRef.current) {
      handleTimerComplete(currentSession.session_id);
    }
  }, [currentSession, handleTimerComplete]);

  const startTimer = useCallback(() => {
    stopTimer();
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
    }
    intervalRef.current = setInterval(() => {
      updateRemainingTime();
    }, 1000);
  }, [updateRemainingTime]);

  // Update remaining time when session changes
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

  const handleStart = async () => {
    if (!selectedPromiseId) {
      setError('Please select a promise');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const session = await apiClient.startFocus(selectedPromiseId, selectedDuration);
      setCurrentSession(session);
      setShowPromisePicker(false);
      
      // Request notification permission
      if ('Notification' in window && Notification.permission === 'default') {
        await Notification.requestPermission();
      }
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

  const handlePause = async () => {
    if (!currentSession) return;

    setLoading(true);
    try {
      const session = await apiClient.pauseFocus(currentSession.session_id);
      setCurrentSession(session);
    } catch (err) {
      console.error('Failed to pause focus:', err);
      setError('Failed to pause session');
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
      setError('Failed to resume session');
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
      setCurrentSession(null);
      setSelectedPromiseId('');
    } catch (err) {
      console.error('Failed to stop focus:', err);
      setError('Failed to stop session');
    } finally {
      setLoading(false);
    }
  };

  // Get promise text for display
  const getPromiseText = (): string => {
    if (!currentSession || !promisesData) return '';
    const promise = promisesData.promises[currentSession.promise_id];
    return promise?.text || currentSession.promise_text || `Promise #${currentSession.promise_id}`;
  };

  // Get available promises for picker
  const getAvailablePromises = (): Array<{ id: string; text: string }> => {
    if (!promisesData) return [];
    return Object.entries(promisesData.promises)
      .filter(([_, data]) => data.hours_promised > 0) // Only time-based promises
      .map(([id, data]) => ({ id, text: data.text }));
  };

  // Render idle state (no active session)
  if (!currentSession) {
    const handleStartClick = () => {
      if (isMobile) {
        // On mobile, navigate to dedicated focus page
        navigate('/focus');
      } else {
        // On desktop, show modal
        setShowPromisePicker(true);
      }
    };

    return (
      <div className="focus-bar focus-bar-idle">
        <div className="focus-bar-content">
          <button
            className="focus-start-button"
            onClick={handleStartClick}
            disabled={loading}
          >
            🎯 Start Focus
          </button>
          
          {showPromisePicker && !isMobile && (
            <div 
              className="focus-picker-modal"
              onClick={(e) => {
                // Close modal when clicking backdrop
                if (e.target === e.currentTarget) {
                  setShowPromisePicker(false);
                  setError('');
                }
              }}
            >
              <div 
                className="focus-picker-content"
                onClick={(e) => e.stopPropagation()}
              >
                <h3>Start Focus Session</h3>
                
                <div className="focus-picker-section">
                  <label>Select Promise:</label>
                  <select
                    value={selectedPromiseId}
                    onChange={(e) => setSelectedPromiseId(e.target.value)}
                    className="focus-picker-select"
                  >
                    <option value="">-- Choose a promise --</option>
                    {getAvailablePromises().map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.text}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="focus-picker-section">
                  <label>Duration:</label>
                  <div className="focus-duration-presets">
                    {[25, 45, 60].map((mins) => (
                      <button
                        key={mins}
                        className={`focus-duration-btn ${selectedDuration === mins ? 'active' : ''}`}
                        onClick={() => setSelectedDuration(mins)}
                      >
                        {mins}m
                      </button>
                    ))}
                  </div>
                </div>

                {error && <div className="focus-error">{error}</div>}

                <div className="focus-picker-actions">
                  <button
                    className="focus-confirm-button"
                    onClick={handleStart}
                    disabled={loading || !selectedPromiseId}
                  >
                    {loading ? 'Starting...' : 'Start'}
                  </button>
                  <button
                    className="focus-cancel-button"
                    onClick={() => {
                      setShowPromisePicker(false);
                      setError('');
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Render active session state
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
                <circle
                  cx="50"
                  cy="50"
                  r="45"
                  className="focus-progress-bg"
                />
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
          {isRunning && (
            <>
              <button
                className="focus-control-btn pause"
                onClick={handlePause}
                disabled={loading}
              >
                ⏸️ Pause
              </button>
              <button
                className="focus-control-btn stop"
                onClick={handleStop}
                disabled={loading}
              >
                ⏹️ Stop
              </button>
            </>
          )}
          {isPaused && (
            <>
              <button
                className="focus-control-btn resume"
                onClick={handleResume}
                disabled={loading}
              >
                ▶️ Resume
              </button>
              <button
                className="focus-control-btn stop"
                onClick={handleStop}
                disabled={loading}
              >
                ⏹️ Stop
              </button>
            </>
          )}
          {isFinished && (
            <div className="focus-complete-message">
              🎉 Session complete! Check Telegram to confirm.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
