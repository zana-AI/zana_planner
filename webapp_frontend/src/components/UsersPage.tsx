import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient, ApiError } from '../api/client';
import { UserCard } from './UserCard';
import type { PublicUser, UserInfo } from '../types';
import { getDevInitData, useTelegramWebApp } from '../hooks/useTelegramWebApp';
import { PageHeader } from './ui/PageHeader';

export function UsersPage() {
  const navigate = useNavigate();
  const { user, initData, isReady } = useTelegramWebApp();
  const [users, setUsers] = useState<PublicUser[]>([]);
  const [followers, setFollowers] = useState<PublicUser[]>([]);
  const [following, setFollowing] = useState<PublicUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [followersLoading, setFollowersLoading] = useState(false);
  const [followingLoading, setFollowingLoading] = useState(false);
  const [error, setError] = useState('');
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);

  const authData = initData || getDevInitData();
  const hasToken = !!localStorage.getItem('telegram_auth_token');
  const isAuthenticated = !!authData || hasToken;

  useEffect(() => {
    if (authData) {
      apiClient.setInitData(authData);
    }
  }, [authData]);

  useEffect(() => {
    if (!isReady || !isAuthenticated) return;
    // Always fetch user info when Telegram user id is not available.
    if (user?.id) return;

    if (authData) {
      apiClient.setInitData(authData);
    }

    apiClient
      .getUserInfo()
      .then(setUserInfo)
      .catch((err) => {
        console.error('Failed to fetch user info', err);
      });
  }, [isReady, isAuthenticated, user?.id, authData]);

  const currentUserId = user?.id?.toString() || userInfo?.user_id?.toString();

  const fetchSocialData = useCallback(async () => {
    if (!currentUserId) return;
    setFollowersLoading(true);
    setFollowingLoading(true);
    try {
      if (authData) {
        apiClient.setInitData(authData);
      }
      const [followersRes, followingRes] = await Promise.all([
        apiClient.getFollowers(currentUserId).catch(() => ({ users: [], total: 0 })),
        apiClient.getFollowing(currentUserId).catch(() => ({ users: [], total: 0 })),
      ]);
      setFollowers(followersRes.users);
      setFollowing(followingRes.users);
    } catch (err) {
      console.error('Failed to fetch social data:', err);
    } finally {
      setFollowersLoading(false);
      setFollowingLoading(false);
    }
  }, [currentUserId, authData]);

  useEffect(() => {
    fetchSocialData();
  }, [fetchSocialData]);

  useEffect(() => {
    if (!isReady || !isAuthenticated) return;

    const fetchUsers = async () => {
      setLoading(true);
      setError('');
      try {
        if (authData) {
          apiClient.setInitData(authData);
        }
        const response = await apiClient.getPublicUsers(20);
        const filteredUsers = response.users.filter((publicUser) => publicUser.user_id !== currentUserId);
        setUsers(filteredUsers);
      } catch (err) {
        console.error('Failed to fetch users:', err);
        if (err instanceof ApiError) {
          if (err.status === 401) {
            apiClient.clearAuth();
            window.dispatchEvent(new Event('logout'));
            navigate('/', { replace: true });
            return;
          }
          setError(err.message);
        } else {
          setError('Failed to load users. Please try again.');
        }
      } finally {
        setLoading(false);
      }
    };
    fetchUsers();
  }, [currentUserId, isAuthenticated, isReady, authData, navigate]);

  if (!isReady) {
    return (
      <div className="users-page">
        <div className="users-page-loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading community...</div>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="users-page">
        <div className="users-page-error">
          <div className="error-icon">!</div>
          <p className="error-message">Authentication required.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="users-page">
      <PageHeader title="Community" subtitle="Meet active users on Xaana" />

      {loading ? (
        <div className="users-page-loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading users...</div>
        </div>
      ) : null}

      {!loading && error ? (
        <div className="users-page-error">
          <div className="error-icon">!</div>
          <p className="error-message">{error}</p>
          <button className="retry-button" onClick={() => window.location.reload()}>
            Try Again
          </button>
        </div>
      ) : null}

      {!loading && !error && users.length === 0 ? (
        <div className="users-page-empty">
          <p className="empty-message">No users found yet.</p>
          <p className="empty-hint">Be the first to join.</p>
        </div>
      ) : null}

      {!loading && !error && currentUserId ? (
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
                  <UserCard key={follower.user_id} user={follower} currentUserId={currentUserId} showFollowButton={false} />
                ))}
                {followers.length > 5 ? <div className="social-more">+{followers.length - 5} more</div> : null}
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
                {following.slice(0, 5).map((followedUser) => (
                  <UserCard
                    key={followedUser.user_id}
                    user={followedUser}
                    currentUserId={currentUserId}
                    showFollowButton={false}
                    onFollowChange={fetchSocialData}
                  />
                ))}
                {following.length > 5 ? <div className="social-more">+{following.length - 5} more</div> : null}
              </div>
            ) : (
              <div className="social-empty">Not following anyone yet</div>
            )}
          </div>
        </div>
      ) : null}

      {!loading && !error ? (
        <div className="users-page-grid">
          {users.map((publicUser) => (
            <UserCard
              key={publicUser.user_id}
              user={publicUser}
              currentUserId={currentUserId}
              showFollowButton={!!currentUserId}
              onFollowChange={fetchSocialData}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
