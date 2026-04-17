import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shield } from 'lucide-react';
import { apiClient, ApiError } from '../api/client';

export function DevAdminLoginPage() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle');
  const [message, setMessage] = useState('');

  const handleLogin = async () => {
    setStatus('loading');
    setMessage('');

    try {
      const result = await apiClient.devAdminLogin();
      apiClient.setAuthToken(result.session_token);
      window.dispatchEvent(new Event('login'));
      navigate('/admin', { replace: true });
    } catch (error) {
      setStatus('error');
      if (error instanceof ApiError && error.status === 404) {
        setMessage('Dev admin login is disabled. Start the backend with WEBAPP_DEV_AUTH_ENABLED=1.');
      } else {
        setMessage(error instanceof Error ? error.message : 'Dev admin login failed.');
      }
    }
  };

  return (
    <main
      style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        padding: '24px',
        background: '#f5f7fb',
        color: '#111827',
      }}
    >
      <section
        style={{
          width: 'min(440px, 100%)',
          border: '1px solid #d8dee8',
          borderRadius: 8,
          background: '#ffffff',
          padding: 24,
          boxShadow: '0 12px 30px rgba(17, 24, 39, 0.08)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
          <Shield size={28} />
          <h1 style={{ margin: 0, fontSize: 24, lineHeight: 1.2 }}>Dev admin login</h1>
        </div>

        <p style={{ margin: '0 0 20px', color: '#4b5563', lineHeight: 1.5 }}>
          Use a local synthetic admin session to traverse the app while building the frontend.
        </p>

        <button
          type="button"
          onClick={handleLogin}
          disabled={status === 'loading'}
          style={{
            width: '100%',
            border: 0,
            borderRadius: 8,
            padding: '12px 16px',
            background: '#111827',
            color: '#ffffff',
            cursor: status === 'loading' ? 'wait' : 'pointer',
            fontWeight: 700,
          }}
        >
          {status === 'loading' ? 'Creating session...' : 'Enter as dev admin'}
        </button>

        {message && (
          <p style={{ margin: '16px 0 0', color: '#b42318', lineHeight: 1.5 }}>
            {message}
          </p>
        )}
      </section>
    </main>
  );
}
