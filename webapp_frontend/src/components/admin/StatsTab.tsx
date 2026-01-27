import React from 'react';

interface StatsTabProps {
  stats: { total_users: number; active_users: number; total_promises: number } | null;
  loadingStats: boolean;
  statsError: string;
  onRetry: () => void;
}

export function StatsTab({ stats, loadingStats, statsError, onRetry }: StatsTabProps) {
  if (loadingStats) {
    return (
      <div className="admin-panel-stats">
        <div className="admin-loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading statistics...</div>
        </div>
      </div>
    );
  }

  if (statsError) {
    return (
      <div className="admin-panel-stats">
        <div className="admin-no-stats">
          <div className="empty-icon">⚠️</div>
          <p>{statsError}</p>
          <button
            onClick={onRetry}
            style={{
              marginTop: '1rem',
              padding: '0.5rem 1rem',
              background: 'rgba(91, 163, 245, 0.2)',
              border: '1px solid rgba(91, 163, 245, 0.4)',
              borderRadius: '6px',
              color: '#5ba3f5',
              cursor: 'pointer',
              fontSize: '0.9rem'
            }}
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="admin-panel-stats">
        <div className="admin-no-stats">
          <div className="empty-icon">📊</div>
          <p>No statistics available</p>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-panel-stats">
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
        gap: '1.5rem',
        padding: '1.5rem 0'
      }}>
        <div style={{
          background: 'rgba(15, 23, 48, 0.6)',
          border: '1px solid rgba(232, 238, 252, 0.1)',
          borderRadius: '12px',
          padding: '1.5rem',
          textAlign: 'center'
        }}>
          <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>👥</div>
          <div style={{ fontSize: '0.9rem', color: 'rgba(232, 238, 252, 0.6)', marginBottom: '0.5rem' }}>
            Total Users
          </div>
          <div style={{ fontSize: '2rem', fontWeight: '700', color: '#fff' }}>
            {stats.total_users.toLocaleString()}
          </div>
        </div>

        <div style={{
          background: 'rgba(15, 23, 48, 0.6)',
          border: '1px solid rgba(232, 238, 252, 0.1)',
          borderRadius: '12px',
          padding: '1.5rem',
          textAlign: 'center'
        }}>
          <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>🔥</div>
          <div style={{ fontSize: '0.9rem', color: 'rgba(232, 238, 252, 0.6)', marginBottom: '0.5rem' }}>
            Active Users (7d)
          </div>
          <div style={{ fontSize: '2rem', fontWeight: '700', color: '#fff' }}>
            {stats.active_users.toLocaleString()}
          </div>
        </div>

        <div style={{
          background: 'rgba(15, 23, 48, 0.6)',
          border: '1px solid rgba(232, 238, 252, 0.1)',
          borderRadius: '12px',
          padding: '1.5rem',
          textAlign: 'center'
        }}>
          <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>🎯</div>
          <div style={{ fontSize: '0.9rem', color: 'rgba(232, 238, 252, 0.6)', marginBottom: '0.5rem' }}>
            Users with Promises
          </div>
          <div style={{ fontSize: '2rem', fontWeight: '700', color: '#fff' }}>
            {stats.total_promises.toLocaleString()}
          </div>
        </div>
      </div>
    </div>
  );
}
