import { useState } from 'react';
import { apiClient, ApiError } from '../../api/client';

interface PromoteTabProps {
  onError: (error: string) => void;
}

export function PromoteTab({ onError }: PromoteTabProps) {
  const [promoting, setPromoting] = useState(false);

  const handlePromote = async () => {
    if (!confirm('Promote staging to production and overwrite production data?')) {
      return;
    }
    setPromoting(true);
    onError('');
    try {
      await apiClient.promoteStagingToProd();
      alert('Promotion started successfully. The backend is restarting — you will be logged out.');
      apiClient.clearAuth();
      window.dispatchEvent(new Event('logout'));
    } catch (err) {
      console.error('Failed to promote:', err);
      if (err instanceof ApiError) {
        onError(err.message);
      } else {
        onError('Failed to promote staging to production');
      }
    } finally {
      setPromoting(false);
    }
  };

  return (
    <div className="admin-panel-promote">
      <div
        style={{
          background: 'rgba(15, 23, 48, 0.8)',
          border: '1px solid rgba(255, 193, 7, 0.3)',
          borderRadius: '12px',
          padding: '1.5rem',
          marginBottom: '1.5rem',
        }}
      >
        <h2 style={{ marginTop: 0, marginBottom: '1rem', color: '#ffc107' }}>Promote Staging to Production</h2>
        <div style={{ marginBottom: '1rem', color: 'rgba(232, 238, 252, 0.8)' }}>
          <p style={{ marginBottom: '0.5rem' }}>
            <strong>Warning:</strong> This operation copies all staging data to production.
          </p>
          <p style={{ marginBottom: '0.5rem' }}>Production data will be overwritten. This action cannot be undone.</p>
          <ul style={{ marginLeft: '1.5rem', marginTop: '0.5rem' }}>
            <li>All production users, promises, and data will be replaced.</li>
            <li>The operation may take several minutes.</li>
            <li>Production services may experience brief downtime.</li>
          </ul>
        </div>
        <button
          onClick={handlePromote}
          disabled={promoting}
          style={{
            padding: '0.75rem 1.5rem',
            background: promoting ? 'rgba(255, 193, 7, 0.3)' : 'linear-gradient(135deg, #ff6b6b, #ee5a6f)',
            border: 'none',
            borderRadius: '6px',
            color: '#fff',
            cursor: promoting ? 'not-allowed' : 'pointer',
            fontSize: '1rem',
            fontWeight: '600',
            opacity: promoting ? 0.5 : 1,
            width: '100%',
          }}
        >
          {promoting ? 'Promoting...' : 'Promote to Production'}
        </button>
      </div>
    </div>
  );
}
