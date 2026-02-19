import type { Broadcast } from '../../types';
import { apiClient, ApiError } from '../../api/client';

interface ScheduledTabProps {
  broadcasts: Broadcast[];
  loadingBroadcasts: boolean;
  onRefresh: () => void;
}

export function ScheduledTab({ broadcasts, loadingBroadcasts, onRefresh }: ScheduledTabProps) {
  const cancelBroadcast = async (broadcastId: string) => {
    if (!confirm('Are you sure you want to cancel this broadcast?')) {
      return;
    }

    try {
      await apiClient.cancelBroadcast(broadcastId);
      onRefresh();
    } catch (err) {
      console.error('Failed to cancel broadcast:', err);
      if (err instanceof ApiError) {
        alert(err.message);
      } else {
        alert('Failed to cancel broadcast. Please try again.');
      }
    }
  };

  if (loadingBroadcasts) {
    return (
      <div className="admin-panel-scheduled">
        <div className="admin-loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading broadcasts...</div>
        </div>
      </div>
    );
  }

  if (broadcasts.length === 0) {
    return (
      <div className="admin-panel-scheduled">
        <div className="admin-no-broadcasts">
          <p>No queued broadcasts</p>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-panel-scheduled">
      <div className="admin-broadcasts-list">
        {broadcasts.map((broadcast) => (
          <div key={broadcast.broadcast_id} className="admin-broadcast-item">
            <div className="admin-broadcast-header">
              <span className="admin-broadcast-status">{broadcast.status}</span>
              <span className="admin-broadcast-time">{new Date(broadcast.scheduled_time_utc).toLocaleString()}</span>
            </div>
            <div className="admin-broadcast-message">{broadcast.message}</div>
            <div className="admin-broadcast-meta">To {broadcast.target_user_ids.length} user(s)</div>
            {broadcast.status === 'pending' ? (
              <button className="admin-cancel-btn" onClick={() => cancelBroadcast(broadcast.broadcast_id)}>
                Cancel
              </button>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
