import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { apiClient, ApiError } from '../api/client';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import type { PublicUser, UserInfo } from '../types';
import { PromiseBadge } from '../components/PromiseBadge';
import { SuggestPromiseModal } from '../components/SuggestPromiseModal';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';

export function UserDetailPage() {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const { user, initData, hapticFeedback } = useTelegramWebApp();
  const [userData, setUserData] = useState<PublicUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showSuggestModal, setShowSuggestModal] = useState(false);
  const [isFollowing, setIsFollowing] = useState(false);
  const [isLoadingFollow, setIsLoadingFollow] = useState(false);
  const [followStatusChecked, setFollowStatusChecked] = useState(false);
  const [avatarError, setAvatarError] = useState(false);
  const [dicebearError, setDicebearError] = useState(false);
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);

  const hasToken = !!localStorage.getItem('telegram_auth_token');

  useEffect(() => {
    if (initData) {
      apiClient.setInitData(initData);
    }
  }, [initData]);

  useEffect(() => {
    if (hasToken && !initData) {
      apiClient.getUserInfo().then(setUserInfo).catch(() => console.error('Failed to fetch user info'));
    }
  }, [hasToken, initData]);

  const currentUserId = user?.id?.toString() || userInfo?.user_id?.toString();

  useEffect(() => {
    if (!userId) {
      setError('User ID is required');
      setLoading(false);
      return;
    }

    const fetchUser = async () => {
      setLoading(true);
      setError('');
      try {
        const data = await apiClient.getUser(userId);
        setUserData(data);
      } catch (err) {
        console.error('Failed to fetch user:', err);
        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError('Failed to load user');
        }
      } finally {
        setLoading(false);
      }
    };
    fetchUser();
  }, [userId]);

  useEffect(() => {
    setFollowStatusChecked(false);
    setIsFollowing(false);
  }, [userId]);

  useEffect(() => {
    if (!currentUserId || !userId || currentUserId === userId || followStatusChecked) return;

    const checkFollowStatus = async () => {
      try {
        const status = await apiClient.getFollowStatus(userId);
        setIsFollowing(status.is_following);
        setFollowStatusChecked(true);
      } catch (err) {
        console.error('Failed to check follow status:', err);
      }
    };
    checkFollowStatus();
  }, [currentUserId, userId, followStatusChecked]);

  const handleFollowToggle = async () => {
    if (!currentUserId || !userId || currentUserId === userId || isLoadingFollow) return;

    setIsLoadingFollow(true);
    try {
      if (isFollowing) {
        await apiClient.unfollowUser(userId);
        setIsFollowing(false);
      } else {
        await apiClient.followUser(userId);
        setIsFollowing(true);
      }
      hapticFeedback('success');
    } catch (err) {
      console.error('Failed to toggle follow:', err);
      hapticFeedback('error');
    } finally {
      setIsLoadingFollow(false);
    }
  };

  const getDisplayName = (publicUser: PublicUser): string => {
    if (publicUser.display_name) return publicUser.display_name;
    if (publicUser.first_name && publicUser.last_name) return `${publicUser.first_name} ${publicUser.last_name}`;
    if (publicUser.first_name) return publicUser.first_name;
    if (publicUser.username) return `@${publicUser.username}`;
    return `User ${publicUser.user_id}`;
  };

  if (loading) {
    return (
      <div className="app">
        <div className="loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading user profile...</div>
        </div>
      </div>
    );
  }

  if (error || !userData) {
    return (
      <div className="app">
        <div className="error">
          <div className="error-icon">!</div>
          <h1 className="error-title">User not found</h1>
          <p className="error-message">{error || 'The user you are looking for does not exist.'}</p>
          <Button variant="secondary" onClick={() => navigate('/community')}>
            Back to Community
          </Button>
        </div>
      </div>
    );
  }

  const isOwnProfile = currentUserId === userId;
  const displayName = getDisplayName(userData);

  const dicebearUrl = `https://api.dicebear.com/7.x/avataaars/svg?seed=${encodeURIComponent(userData.user_id)}`;
  const avatarUrl =
    !avatarError && userData.avatar_path
      ? userData.avatar_path.startsWith('http')
        ? userData.avatar_path
        : `/api/media/avatars/${userData.user_id}`
      : null;

  return (
    <div className="app">
      <PageHeader title={displayName} showBack fallbackRoute="/community" />

      <div className="user-detail-container">
        <div className="user-detail-card">
          <div className="user-detail-head">
            {avatarUrl ? (
              <img src={avatarUrl} alt={displayName} onError={() => setAvatarError(true)} className="user-detail-avatar" />
            ) : !dicebearError ? (
              <img src={dicebearUrl} alt={displayName} onError={() => setDicebearError(true)} className="user-detail-avatar" />
            ) : (
              <div className="user-detail-avatar user-detail-avatar-fallback">{displayName.charAt(0).toUpperCase()}</div>
            )}

            <div className="user-detail-main">
              <h2>{displayName}</h2>
              {userData.username ? <div className="user-detail-username">@{userData.username}</div> : null}
            </div>

            {!isOwnProfile && currentUserId ? (
              <div className="user-detail-actions">
                <Button
                  variant={isFollowing ? 'secondary' : 'primary'}
                  size="sm"
                  onClick={handleFollowToggle}
                  disabled={isLoadingFollow || !followStatusChecked}
                >
                  {isLoadingFollow ? '...' : isFollowing ? 'Unfollow' : 'Follow'}
                </Button>
                <Button size="sm" onClick={() => setShowSuggestModal(true)}>
                  Suggest Promise
                </Button>
              </div>
            ) : null}
          </div>

          <div className="user-detail-metrics">
            {userData.activity_count > 0 ? (
              <div>
                <strong>{userData.activity_count}</strong> {userData.activity_count === 1 ? 'activity' : 'activities'}
              </div>
            ) : null}
            {userData.promise_count > 0 ? (
              <div>
                <strong>{userData.promise_count}</strong> {userData.promise_count === 1 ? 'promise' : 'promises'}
              </div>
            ) : null}
          </div>
        </div>

        {userData.public_promises && userData.public_promises.length > 0 ? (
          <div>
            <h3 className="user-detail-section-title">Public Promises</h3>
            <div className="user-detail-promises">
              {userData.public_promises.map((badge) => (
                <PromiseBadge key={badge.promise_id} badge={badge} compact={false} />
              ))}
            </div>
          </div>
        ) : (
          <div className="user-detail-empty">No public promises yet</div>
        )}
      </div>

      {showSuggestModal ? (
        <SuggestPromiseModal
          toUserId={userData.user_id}
          toUserName={displayName}
          onClose={() => setShowSuggestModal(false)}
          onSuccess={() => {
            hapticFeedback('success');
            setShowSuggestModal(false);
          }}
        />
      ) : null}
    </div>
  );
}
