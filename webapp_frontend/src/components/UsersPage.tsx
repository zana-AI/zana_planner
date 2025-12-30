import { useState, useEffect } from 'react';
import { apiClient, ApiError } from '../api/client';
import { UserCard } from './UserCard';
import type { PublicUser } from '../types';

export function UsersPage() {
  const [users, setUsers] = useState<PublicUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');

  useEffect(() => {
    const fetchUsers = async () => {
      setLoading(true);
      setError('');
      
      try {
        const response = await apiClient.getPublicUsers(20);
        setUsers(response.users);
      } catch (err) {
        console.error('Failed to fetch users:', err);
        
        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError('Failed to load users. Please try again.');
        }
      } finally {
        setLoading(false);
      }
    };

    fetchUsers();
  }, []);

  if (loading) {
    return (
      <div className="users-page">
        <div className="users-page-header">
          <h1 className="users-page-title">Zana Community</h1>
          <p className="users-page-subtitle">Meet active users on Zana</p>
        </div>
        <div className="users-page-loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading users...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="users-page">
        <div className="users-page-header">
          <h1 className="users-page-title">Zana Community</h1>
          <p className="users-page-subtitle">Meet active users on Zana</p>
        </div>
        <div className="users-page-error">
          <div className="error-icon">😕</div>
          <p className="error-message">{error}</p>
          <button 
            className="retry-button" 
            onClick={() => window.location.reload()}
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  if (users.length === 0) {
    return (
      <div className="users-page">
        <div className="users-page-header">
          <h1 className="users-page-title">Zana Community</h1>
          <p className="users-page-subtitle">Meet active users on Zana</p>
        </div>
        <div className="users-page-empty">
          <div className="empty-icon">👥</div>
          <p className="empty-message">No users found yet.</p>
          <p className="empty-hint">Be the first to join!</p>
        </div>
      </div>
    );
  }

  return (
    <div className="users-page">
      <div className="users-page-header">
        <h1 className="users-page-title">Zana Community</h1>
        <p className="users-page-subtitle">Meet active users on Zana</p>
      </div>
      <div className="users-page-grid">
        {users.map((user) => (
          <UserCard key={user.user_id} user={user} />
        ))}
      </div>
    </div>
  );
}

