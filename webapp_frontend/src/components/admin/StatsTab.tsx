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
          <div className="loading-text">Loading metrics...</div>
        </div>
      </div>
    );
  }

  if (statsError) {
    return (
      <div className="admin-panel-stats">
        <div className="admin-no-stats">
          <p>{statsError}</p>
          <button className="admin-select-all-btn" onClick={onRetry}>
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
          <p>No metrics available</p>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-panel-stats">
      <div className="admin-metrics-grid">
        <div className="admin-metric-card">
          <div className="admin-metric-label">Total Users</div>
          <div className="admin-metric-value">{stats.total_users.toLocaleString()}</div>
        </div>
        <div className="admin-metric-card">
          <div className="admin-metric-label">Active Users (7d)</div>
          <div className="admin-metric-value">{stats.active_users.toLocaleString()}</div>
        </div>
        <div className="admin-metric-card">
          <div className="admin-metric-label">Users With Promises</div>
          <div className="admin-metric-value">{stats.total_promises.toLocaleString()}</div>
        </div>
      </div>
    </div>
  );
}
