import { useState, useEffect, useRef } from 'react';
import { apiClient, ApiError } from '../../api/client';

export function TestsTab() {
  const [testSuite, setTestSuite] = useState<'pytest' | 'scenarios' | 'both'>('both');
  const [isRunning, setIsRunning] = useState(false);
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [output, setOutput] = useState<string[]>([]);
  const [status, setStatus] = useState<string>('idle');
  const [exitCode, setExitCode] = useState<number | null>(null);
  const [reportContent, setReportContent] = useState<string | null>(null);
  const [error, setError] = useState<string>('');
  const eventSourceRef = useRef<EventSource | null>(null);
  const outputEndRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom when output updates
  useEffect(() => {
    if (outputEndRef.current) {
      outputEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [output]);

  // Cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  const startTestRun = async () => {
    if (isRunning) {
      return;
    }

    setError('');
    setOutput([]);
    setStatus('running');
    setExitCode(null);
    setReportContent(null);
    setIsRunning(true);

    try {
      const response = await apiClient.startTestRun(testSuite);
      setCurrentRunId(response.run_id);
      
      // Start SSE stream (use full API path)
      // Note: EventSource doesn't support custom headers, so we pass auth via query params
      const token = localStorage.getItem('telegram_auth_token');
      const initData = apiClient.initData || '';
      
      // Build URL with auth query params
      const params = new URLSearchParams();
      if (token) {
        params.append('token', token);
      } else if (initData) {
        params.append('init_data', initData);
      }
      
      const streamUrl = `/api/admin/tests/stream/${response.run_id}${params.toString() ? '?' + params.toString() : ''}`;
      const eventSource = new EventSource(streamUrl);
      eventSourceRef.current = eventSource;

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'output') {
            setOutput(prev => [...prev, data.line]);
          } else if (data.type === 'status') {
            setStatus(data.status);
            if (data.exit_code !== undefined) {
              setExitCode(data.exit_code);
            }
          } else if (data.type === 'complete') {
            setStatus(data.status);
            setExitCode(data.exit_code);
            setIsRunning(false);
            eventSource.close();
            eventSourceRef.current = null;
            
            // Fetch report
            if (response.run_id) {
              fetchReport(response.run_id);
            }
          }
        } catch (e) {
          console.error('Error parsing SSE data:', e);
        }
      };

      eventSource.onerror = (err) => {
        console.error('SSE error:', err);
        setError('Connection error while streaming test output');
        setIsRunning(false);
        eventSource.close();
        eventSourceRef.current = null;
      };

    } catch (err) {
      console.error('Failed to start test run:', err);
      if (err instanceof ApiError) {
        setError(err.message || 'Failed to start test run');
      } else {
        setError('Failed to start test run');
      }
      setIsRunning(false);
    }
  };

  const fetchReport = async (runId: string) => {
    try {
      const report = await apiClient.getTestReport(runId);
      if (report.report_content) {
        setReportContent(report.report_content);
      }
    } catch (err) {
      console.error('Failed to fetch report:', err);
    }
  };

  const stopTestRun = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsRunning(false);
    setStatus('stopped');
  };

  const downloadReport = () => {
    if (!reportContent || !currentRunId) {
      return;
    }

    const blob = new Blob([reportContent], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `test_report_${currentRunId}.html`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="admin-panel-tests" style={{ padding: '1.5rem' }}>
      <h2 style={{ marginBottom: '1.5rem', color: '#fff' }}>Test Runner</h2>
      
      <div style={{ marginBottom: '1.5rem' }}>
        <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)' }}>
          Test Suite:
        </label>
        <select
          value={testSuite}
          onChange={(e) => setTestSuite(e.target.value as 'pytest' | 'scenarios' | 'both')}
          disabled={isRunning}
          style={{
            padding: '0.5rem',
            borderRadius: '4px',
            border: '1px solid rgba(232, 238, 252, 0.2)',
            background: 'rgba(15, 23, 48, 0.6)',
            color: '#fff',
            fontSize: '1rem',
            minWidth: '200px'
          }}
        >
          <option value="pytest">Pytest Only</option>
          <option value="scenarios">Scenarios Only</option>
          <option value="both">Both</option>
        </select>
      </div>

      <div style={{ marginBottom: '1.5rem', display: 'flex', gap: '1rem' }}>
        <button
          onClick={startTestRun}
          disabled={isRunning}
          style={{
            padding: '0.75rem 1.5rem',
            borderRadius: '6px',
            border: 'none',
            background: isRunning ? 'rgba(91, 163, 245, 0.5)' : 'rgba(91, 163, 245, 1)',
            color: '#fff',
            fontSize: '1rem',
            fontWeight: '600',
            cursor: isRunning ? 'not-allowed' : 'pointer',
            transition: 'all 0.2s'
          }}
        >
          {isRunning ? 'Running...' : 'Run Tests'}
        </button>
        
        {isRunning && (
          <button
            onClick={stopTestRun}
            style={{
              padding: '0.75rem 1.5rem',
              borderRadius: '6px',
              border: '1px solid rgba(232, 238, 252, 0.3)',
              background: 'rgba(15, 23, 48, 0.6)',
              color: '#fff',
              fontSize: '1rem',
              cursor: 'pointer'
            }}
          >
            Stop
          </button>
        )}

        {reportContent && (
          <button
            onClick={downloadReport}
            style={{
              padding: '0.75rem 1.5rem',
              borderRadius: '6px',
              border: '1px solid rgba(232, 238, 252, 0.3)',
              background: 'rgba(15, 23, 48, 0.6)',
              color: '#fff',
              fontSize: '1rem',
              cursor: 'pointer'
            }}
          >
            Download Report
          </button>
        )}
      </div>

      {error && (
        <div style={{
          padding: '1rem',
          marginBottom: '1rem',
          borderRadius: '6px',
          background: 'rgba(239, 68, 68, 0.2)',
          border: '1px solid rgba(239, 68, 68, 0.5)',
          color: '#fca5a5'
        }}>
          {error}
        </div>
      )}

      {status !== 'idle' && (
        <div style={{ marginBottom: '1rem' }}>
          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
            <span style={{ color: 'rgba(232, 238, 252, 0.8)' }}>Status:</span>
            <span style={{
              color: status === 'completed' ? '#10b981' : status === 'failed' ? '#ef4444' : '#5ba3f5',
              fontWeight: '600'
            }}>
              {status.toUpperCase()}
            </span>
            {exitCode !== null && (
              <span style={{ color: 'rgba(232, 238, 252, 0.6)' }}>
                (Exit Code: {exitCode})
              </span>
            )}
          </div>
        </div>
      )}

      {output.length > 0 && (
        <div style={{
          marginBottom: '1rem',
          padding: '1rem',
          borderRadius: '6px',
          background: 'rgba(15, 23, 48, 0.8)',
          border: '1px solid rgba(232, 238, 252, 0.1)',
          maxHeight: '400px',
          overflowY: 'auto',
          fontFamily: 'monospace',
          fontSize: '0.875rem',
          color: 'rgba(232, 238, 252, 0.9)'
        }}>
          {output.map((line, idx) => (
            <div key={idx} style={{ marginBottom: '0.25rem', whiteSpace: 'pre-wrap' }}>
              {line}
            </div>
          ))}
          <div ref={outputEndRef} />
        </div>
      )}

      {reportContent && (
        <div style={{
          marginTop: '1.5rem',
          padding: '1rem',
          borderRadius: '6px',
          background: 'rgba(15, 23, 48, 0.6)',
          border: '1px solid rgba(232, 238, 252, 0.1)'
        }}>
          <h3 style={{ marginBottom: '1rem', color: '#fff' }}>Test Report</h3>
          <div
            style={{
              maxHeight: '500px',
              overflowY: 'auto',
              padding: '1rem',
              background: 'rgba(0, 0, 0, 0.3)',
              borderRadius: '4px'
            }}
            dangerouslySetInnerHTML={{ __html: reportContent }}
          />
        </div>
      )}
    </div>
  );
}
