import { useState, useEffect } from 'react';
import { apiClient, ApiError } from '../api/client';
import { UserCard } from './UserCard';
import type { PublicUser, UserInfo } from '../types';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';

export function UsersPage() {
  const { user, initData } = useTelegramWebApp();
  const [users, setUsers] = useState<PublicUser[]>([]);
  const [followers, setFollowers] = useState<PublicUser[]>([]);
  const [following, setFollowing] = useState<PublicUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [followersLoading, setFollowersLoading] = useState(false);
  const [followingLoading, setFollowingLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  
  // Check authentication - don't render if not authenticated
  const hasToken = !!localStorage.getItem('telegram_auth_token');
  const isAuthenticated = !!initData || hasToken;
  
  if (!isAuthenticated) {
    // This shouldn't happen due to route guard, but handle gracefully
    return null;
  }
  
  // Set initData for API client if available
  useEffect(() => {
    if (initData) {
      apiClient.setInitData(initData);
    }
  }, [initData]);

  // Fetch userInfo for browser login users
  useEffect(() => {
    if (hasToken && !initData) {
      // Browser login - fetch user info to get user_id
      apiClient.getUserInfo()
        .then(setUserInfo)
        .catch(() => {
          console.error('Failed to fetch user info');
        });
    }
  }, [initData, hasToken]);

  // Get current user ID if authenticated
  // Use user?.id for Telegram Mini App, or userInfo?.user_id for browser login
  const currentUserId = user?.id?.toString() || userInfo?.user_id?.toString();

  const fetchSocialData = async () => {
    if (!currentUserId) return;
    
    setFollowersLoading(true);
    setFollowingLoading(true);
    
    try {
      const [followersRes, followingRes] = await Promise.all([
        apiClient.getFollowers(currentUserId).catch(() => ({ users: [], total: 0 })),
        apiClient.getFollowing(currentUserId).catch(() => ({ users: [], total: 0 }))
      ]);
      
      setFollowers(followersRes.users);
      setFollowing(followingRes.users);
    } catch (err) {
      console.error('Failed to fetch social data:', err);
    } finally {
      setFollowersLoading(false);
      setFollowingLoading(false);
    }
  };

  // Fetch followers and following when authenticated
  useEffect(() => {
    fetchSocialData();
  }, [currentUserId]);

  useEffect(() => {
    // Only fetch if authenticated
    if (!isAuthenticated) {
      return;
    }
    
    const fetchUsers = async () => {
      setLoading(true);
      setError('');
      
      try {
        const response = await apiClient.getPublicUsers(20);
        // Filter out current user from the list
        const filteredUsers = response.users.filter(
          u => u.user_id !== currentUserId
        );
        setUsers(filteredUsers);
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
  }, [currentUserId, isAuthenticated]);

  if (loading) {
    return (
      <div className="users-page">
        <div className="users-page-header">
          <h1 className="users-page-title">Xaana Club</h1>
          <p className="users-page-subtitle">Meet active users on Xaana</p>
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
          <h1 className="users-page-title">Xaana Club</h1>
          <p className="users-page-subtitle">Meet active users on Xaana</p>
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
          <h1 className="users-page-title">Xaana Club</h1>
          <p className="users-page-subtitle">Meet active users on Xaana</p>
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
        <h1 className="users-page-title">Xaana Club</h1>
        <p className="users-page-subtitle">Meet active users on Xaana</p>
      </div>
      
      {/* Followers and Following Section - Only show when authenticated */}
      {currentUserId && (
        <div className="users-page-social">
          <div className="social-section">
            <div className="social-header">
              <h3 className="social-title">Followers</h3>
              <span className="social-count">{followers.length}</span>
            </div>
            {followersLoading ? (
              <div className="social-loading">Loading...</div>
            ) : followers.length > 0 ? (
              <div className="social-list">
                {followers.slice(0, 5).map((follower) => (
                  <UserCard 
                    key={follower.user_id} 
                    user={follower} 
                    currentUserId={currentUserId}
                    showFollowButton={false}
                  />
                ))}
                {followers.length > 5 && (
                  <div className="social-more">+{followers.length - 5} more</div>
                )}
              </div>
            ) : (
              <div className="social-empty">No followers yet</div>
            )}
          </div>
          
          <div className="social-section">
            <div className="social-header">
              <h3 className="social-title">Following</h3>
              <span className="social-count">{following.length}</span>
            </div>
            {followingLoading ? (
              <div className="social-loading">Loading...</div>
            ) : following.length > 0 ? (
              <div className="social-list">
                {following.slice(0, 5).map((followed) => (
                  <UserCard 
                    key={followed.user_id} 
                    user={followed} 
                    currentUserId={currentUserId}
                    showFollowButton={false}
                    onFollowChange={fetchSocialData}
                  />
                ))}
                {following.length > 5 && (
                  <div className="social-more">+{following.length - 5} more</div>
                )}
              </div>
            ) : (
              <div className="social-empty">Not following anyone yet</div>
            )}
          </div>
        </div>
      )}
      
      <div className="users-page-grid">
        {users.map((user) => (
          <UserCard 
            key={user.user_id} 
            user={user} 
            currentUserId={currentUserId}
            showFollowButton={!!currentUserId}
            onFollowChange={fetchSocialData}
          />
        ))}
      </div>
    </div>
  );
}

