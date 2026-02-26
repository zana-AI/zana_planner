import { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { useModalBodyLock } from '../hooks/useModalBodyLock';

interface PromiseLogsModalProps {
  promiseId: string;
  promiseText: string;
  isOpen: boolean;
  onClose: () => void;
}

interface LogEntry {
  datetime: string;
  date: string;
  time_spent: number;
  time_str: string;
  notes: string | null;
}

export function PromiseLogsModal({ promiseId, promiseText, isOpen, onClose }: PromiseLogsModalProps) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  useModalBodyLock(isOpen);

  useEffect(() => {
    if (isOpen && promiseId) {
      fetchLogs();
    }
  }, [isOpen, promiseId]);

  const fetchLogs = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await apiClient.getPromiseLogs(promiseId, 20);
      setLogs(response.logs);
    } catch (err) {
      console.error('Failed to fetch logs:', err);
      setError(err instanceof Error ? err.message : 'Failed to load logs');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content promise-logs-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">Recent Logs</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        
        <div className="modal-body">
          <div className="promise-logs-promise-name">{promiseText.replace(/_/g, ' ')}</div>
          
          {loading ? (
            <div className="promise-logs-loading">Loading logs...</div>
          ) : error ? (
            <div className="promise-logs-error">{error}</div>
          ) : logs.length === 0 ? (
            <div className="promise-logs-empty">No logs yet for this promise.</div>
          ) : (
            <div className="promise-logs-list">
              {logs.map((log, index) => (
                <div key={index} className="promise-logs-entry">
                  <div className="promise-logs-entry-main">
                    {log.time_spent > 0 ? (
                      <span className="promise-logs-log-text">
                        &gt; {log.time_str} logged on {log.date}
                      </span>
                    ) : (
                      <span className="promise-logs-log-text">
                        &gt; previous action logged on {log.date}
                      </span>
                    )}
                  </div>
                  {log.notes && (
                    <div className="promise-logs-notes">{log.notes}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
