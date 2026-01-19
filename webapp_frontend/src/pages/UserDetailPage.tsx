import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiClient, ApiError } from '../api/client';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import type { PublicUser, UserInfo } from '../types';
import { PromiseBadge } from '../components/PromiseBadge';
import { SuggestPromiseModal } from '../components/SuggestPromiseModal';

export function UserDetailPage() {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const { user, initData, hapticFeedback } = useTelegramWebApp();
  const [userData, setUserData] = useState<PublicUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [showSuggestModal, setShowSuggestModal] = useState(false);
  const [isFollowing, setIsFollowing] = useState(false);
  const [isLoadingFollow, setIsLoadingFollow] = useState(false);
  const [followStatusChecked, setFollowStatusChecked] = useState(false);
  const [avatarError, setAvatarError] = useState(false);
  const [dicebearError, setDicebearError] = useState(false);
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);

  // Support both Telegram Mini App (initData + initDataUnsafe.user) and browser login token.
  const hasToken = !!localStorage.getItem('telegram_auth_token');

  // Set initData for API client if available (Telegram Mini App)
  useEffect(() => {
    if (initData) {
      apiClient.setInitData(initData);
    }
  }, [initData]);

  // Fetch userInfo for browser login users (to get user_id)
  useEffect(() => {
    if (hasToken && !initData) {
      apiClient.getUserInfo()
        .then(setUserInfo)
        .catch(() => {
          console.error('Failed to fetch user info');
        });
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

  // Reset follow status when navigating between profiles
  useEffect(() => {
    setFollowStatusChecked(false);
    setIsFollowing(false);
  }, [userId]);

  // Check follow status if authenticated and not own profile
  useEffect(() => {
    if (currentUserId && userId && currentUserId !== userId && !followStatusChecked) {
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
    }
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

  const getDisplayName = (user: PublicUser): string => {
    if (user.display_name) return user.display_name;
    if (user.first_name && user.last_name) return `${user.first_name} ${user.last_name}`;
    if (user.first_name) return user.first_name;
    if (user.username) return `@${user.username}`;
    return `User ${user.user_id}`;
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
          <div className="error-icon">😕</div>
          <h1 className="error-title">User not found</h1>
          <p className="error-message">{error || 'The user you are looking for does not exist.'}</p>
          <button className="retry-button" onClick={() => navigate('/community')}>
            Back to Community
          </button>
        </div>
      </div>
    );
  }

  const isOwnProfile = currentUserId === userId;
  const displayName = getDisplayName(userData);

  const dicebearUrl = `https://api.dicebear.com/7.x/avataaars/svg?seed=${encodeURIComponent(userData.user_id)}`;
  const avatarUrl = !avatarError && userData.avatar_path
    ? (userData.avatar_path.startsWith('http') ? userData.avatar_path : `/api/media/avatars/${userData.user_id}`)
    : null;

  return (
    <div className="app">
      <header className="page-header">
        <button
          onClick={() => navigate(-1)}
          style={{
            position: 'absolute',
            left: '1rem',
            top: '50%',
            transform: 'translateY(-50%)',
            background: 'rgba(232, 238, 252, 0.1)',
            border: '1px solid rgba(232, 238, 252, 0.2)',
            borderRadius: '8px',
            padding: '0.5rem 1rem',
            color: '#fff',
            cursor: 'pointer',
            fontSize: '0.9rem'
          }}
        >
          ← Back
        </button>
        <h1 className="page-title">{getDisplayName(userData)}</h1>
      </header>

      <div style={{ padding: '1rem', maxWidth: '800px', margin: '0 auto' }}>
        {/* User Info Card */}
        <div
          style={{
            border: '1px solid rgba(232, 238, 252, 0.15)',
            borderRadius: '12px',
            padding: '1.5rem',
            background: 'linear-gradient(180deg, rgba(15,26,56,0.98), rgba(15,23,48,0.98))',
            marginBottom: '1.5rem'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
            {avatarUrl ? (
              <img
                src={avatarUrl}
                alt={displayName}
                onError={() => setAvatarError(true)}
                style={{
                  width: '64px',
                  height: '64px',
                  borderRadius: '50%',
                  objectFit: 'cover'
                }}
              />
            ) : !dicebearError ? (
              <img
                src={dicebearUrl}
                alt={displayName}
                onError={() => setDicebearError(true)}
                style={{
                  width: '64px',
                  height: '64px',
                  borderRadius: '50%',
                  objectFit: 'cover'
                }}
              />
            ) : (
              <div
                style={{
                  width: '64px',
                  height: '64px',
                  borderRadius: '50%',
                  background: 'rgba(232, 238, 252, 0.1)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '24px',
                  color: '#fff',
                  fontWeight: '600'
                }}
              >
                {displayName.charAt(0).toUpperCase()}
              </div>
            )}
            <div style={{ flex: 1 }}>
              <h2 style={{ color: '#fff', margin: 0, marginBottom: '0.25rem' }}>
                {displayName}
              </h2>
              {userData.username && (
                <div style={{ color: 'rgba(232, 238, 252, 0.6)', fontSize: '0.9rem' }}>
                  @{userData.username}
                </div>
              )}
            </div>
            {!isOwnProfile && currentUserId && (
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  className={`user-card-follow-btn ${isFollowing ? 'following' : ''}`}
                  onClick={handleFollowToggle}
                  disabled={isLoadingFollow || !followStatusChecked}
                  title={isFollowing ? 'Click to unfollow' : 'Click to follow'}
                >
                  {isLoadingFollow ? '...' : isFollowing ? 'Unfollow' : 'Follow'}
                </button>
                <button
                  className="button-primary"
                  onClick={() => setShowSuggestModal(true)}
                  style={{ fontSize: '0.9rem', padding: '0.5rem 1rem' }}
                >
                  Suggest Promise
                </button>
              </div>
            )}
          </div>

          <div style={{ display: 'flex', gap: '2rem', color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem' }}>
            {userData.activity_count > 0 && (
              <div>
                <strong>{userData.activity_count}</strong> {userData.activity_count === 1 ? 'activity' : 'activities'}
              </div>
            )}
            {userData.promise_count > 0 && (
              <div>
                <strong>{userData.promise_count}</strong> {userData.promise_count === 1 ? 'promise' : 'promises'}
              </div>
            )}
          </div>
        </div>

        {/* Public Promises */}
        {userData.public_promises && userData.public_promises.length > 0 ? (
          <div>
            <h2 style={{ color: '#fff', marginBottom: '1rem', fontSize: '1.2rem' }}>Public Promises</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {userData.public_promises.map((badge) => (
                <PromiseBadge key={badge.promise_id} badge={badge} compact={false} />
              ))}
            </div>
          </div>
        ) : (
          <div
            style={{
              border: '1px solid rgba(232, 238, 252, 0.15)',
              borderRadius: '12px',
              padding: '2rem',
              textAlign: 'center',
              color: 'rgba(232, 238, 252, 0.6)'
            }}
          >
            No public promises yet
          </div>
        )}
      </div>

      {showSuggestModal && userData && (
        <SuggestPromiseModal
          toUserId={userData.user_id}
          toUserName={getDisplayName(userData)}
          onClose={() => setShowSuggestModal(false)}
          onSuccess={() => {
            hapticFeedback('success');
            setShowSuggestModal(false);
          }}
        />
      )}
    </div>
  );
}
