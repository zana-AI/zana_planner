import React, { useState } from 'react';
import { apiClient, ApiError } from '../../api/client';

interface PromoteTabProps {
  onError: (error: string) => void;
}

export function PromoteTab({ onError }: PromoteTabProps) {
  const [promoting, setPromoting] = useState(false);
  const [promoteConfirmText, setPromoteConfirmText] = useState('');

  const handlePromote = async () => {
    if (promoteConfirmText !== 'PROMOTE TO PROD') {
      onError('Please type "PROMOTE TO PROD" to confirm');
      return;
    }
    if (!confirm('Are you absolutely sure you want to promote staging to production? This will overwrite all production data!')) {
      return;
    }
    setPromoting(true);
    onError('');
    try {
      await apiClient.promoteStagingToProd();
      alert('Promotion started successfully! This may take several minutes.');
      setPromoteConfirmText('');
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
      <div style={{
        background: 'rgba(15, 23, 48, 0.8)',
        border: '1px solid rgba(255, 193, 7, 0.3)',
        borderRadius: '12px',
        padding: '1.5rem',
        marginBottom: '1.5rem'
      }}>
        <h2 style={{ marginTop: 0, marginBottom: '1rem', color: '#ffc107' }}>
          ⚠️ Promote Staging to Production
        </h2>
        <div style={{ marginBottom: '1rem', color: 'rgba(232, 238, 252, 0.8)' }}>
          <p style={{ marginBottom: '0.5rem' }}>
            <strong>Warning:</strong> This operation will copy all data from the staging database to the production database.
          </p>
          <p style={{ marginBottom: '0.5rem' }}>
            This will <strong>overwrite</strong> all production data with staging data. This action cannot be undone.
          </p>
          <ul style={{ marginLeft: '1.5rem', marginTop: '0.5rem' }}>
            <li>All production users, promises, and data will be replaced</li>
            <li>This operation may take several minutes</li>
            <li>Production services may experience brief downtime</li>
          </ul>
        </div>
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem' }}>
            Type <strong>PROMOTE TO PROD</strong> to confirm:
          </label>
          <input
            type="text"
            value={promoteConfirmText}
            onChange={(e) => setPromoteConfirmText(e.target.value)}
            placeholder="PROMOTE TO PROD"
            style={{
              width: '100%',
              padding: '0.5rem',
              borderRadius: '6px',
              border: '1px solid rgba(232, 238, 252, 0.2)',
              background: 'rgba(11, 16, 32, 0.6)',
              color: '#fff',
              fontSize: '1rem'
            }}
          />
        </div>
        <button
          onClick={handlePromote}
          disabled={promoting || promoteConfirmText !== 'PROMOTE TO PROD'}
          style={{
            padding: '0.75rem 1.5rem',
            background: promoting ? 'rgba(255, 193, 7, 0.3)' : 'linear-gradient(135deg, #ff6b6b, #ee5a6f)',
            border: 'none',
            borderRadius: '6px',
            color: '#fff',
            cursor: (promoting || promoteConfirmText !== 'PROMOTE TO PROD') ? 'not-allowed' : 'pointer',
            fontSize: '1rem',
            fontWeight: '600',
            opacity: (promoting || promoteConfirmText !== 'PROMOTE TO PROD') ? 0.5 : 1,
            width: '100%'
          }}
        >
          {promoting ? 'Promoting...' : '🚀 Promote Staging to Production'}
        </button>
      </div>
    </div>
  );
}
