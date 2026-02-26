import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient, ApiError } from '../api/client';
import { ActivityItem } from './community/ActivityItem';
import { CompactUserChip } from './community/CompactUserChip';
import type { PublicActivityItem, PublicUser, UserInfo } from '../types';
import { getDevInitData, useTelegramWebApp } from '../hooks/useTelegramWebApp';
import { PageHeader } from './ui/PageHeader';

const PREVIEW_COUNT = 8;

export function UsersPage() {
  const navigate = useNavigate();
  const { user, initData, isReady } = useTelegramWebApp();
  const [discoverUsers, setDiscoverUsers] = useState<PublicUser[]>([]);
  const [activityItems, setActivityItems] = useState<PublicActivityItem[]>([]);
  const [followers, setFollowers] = useState<PublicUser[]>([]);
  const [following, setFollowing] = useState<PublicUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [activityLoading, setActivityLoading] = useState(false);
  const [followersLoading, setFollowersLoading] = useState(false);
  const [followingLoading, setFollowingLoading] = useState(false);
  const [error, setError] = useState('');
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [followBusyByUser, setFollowBusyByUser] = useState<Record<string, boolean>>({});
  const [followingExpanded, setFollowingExpanded] = useState(false);
  const [followersExpanded, setFollowersExpanded] = useState(false);
  const [discoverExpanded, setDiscoverExpanded] = useState(false);

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
  const followingIds = useMemo(() => new Set(following.map((person) => person.user_id)), [following]);

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

  const fetchCommunityData = useCallback(async () => {
    if (!isReady || !isAuthenticated) return;

    setLoading(true);
    setActivityLoading(true);
    setError('');
    try {
      if (authData) {
        apiClient.setInitData(authData);
      }

      const [activityRes, usersRes] = await Promise.all([
        apiClient.getPublicActivity(25),
        apiClient.getPublicUsers(24),
      ]);

      setActivityItems(activityRes.items);
      setDiscoverUsers(usersRes.users.filter((publicUser) => publicUser.user_id !== currentUserId));
    } catch (err) {
      console.error('Failed to fetch community data:', err);
      if (err instanceof ApiError) {
        if (err.status === 401) {
          apiClient.clearAuth();
          window.dispatchEvent(new Event('logout'));
          navigate('/', { replace: true });
          return;
        }
        setError(err.message);
      } else {
        setError('Failed to load community. Please try again.');
      }
    } finally {
      setLoading(false);
      setActivityLoading(false);
    }
  }, [isReady, isAuthenticated, authData, currentUserId, navigate]);

  useEffect(() => {
    fetchCommunityData();
  }, [fetchCommunityData]);

  const toggleFollow = useCallback(async (targetUserId: string) => {
    if (!currentUserId || targetUserId === currentUserId) return;

    setFollowBusyByUser((prev) => ({ ...prev, [targetUserId]: true }));
    try {
      if (followingIds.has(targetUserId)) {
        await apiClient.unfollowUser(targetUserId);
      } else {
        await apiClient.followUser(targetUserId);
      }
      await fetchSocialData();
    } catch (err) {
      console.error(`Failed to toggle follow for ${targetUserId}:`, err);
    } finally {
      setFollowBusyByUser((prev) => ({ ...prev, [targetUserId]: false }));
    }
  }, [currentUserId, followingIds, fetchSocialData]);

  const discoverCandidates = useMemo(
    () => discoverUsers.filter((person) => !followingIds.has(person.user_id)),
    [discoverUsers, followingIds]
  );

  const visibleFollowing = followingExpanded ? following : following.slice(0, PREVIEW_COUNT);
  const visibleFollowers = followersExpanded ? followers : followers.slice(0, PREVIEW_COUNT);
  const visibleDiscover = discoverExpanded ? discoverCandidates : discoverCandidates.slice(0, PREVIEW_COUNT);

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
    <div className="users-page users-page-community">
      <PageHeader title="Community" subtitle="Recent public activity and people you follow" />

      {loading && activityItems.length === 0 ? (
        <div className="users-page-loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading community...</div>
        </div>
      ) : null}

      {!loading && error ? (
        <div className="users-page-error">
          <div className="error-icon">!</div>
          <p className="error-message">{error}</p>
          <button type="button" className="retry-button" onClick={fetchCommunityData}>
            Try Again
          </button>
        </div>
      ) : null}

      {!error ? (
        <div className="community-v2-layout">
          <section className="community-v2-section community-v2-activity">
            <div className="community-v2-section-header">
              <h3 className="community-v2-title">Recent Activity</h3>
              <span className="community-v2-count">{activityItems.length}</span>
            </div>

            {activityLoading && activityItems.length === 0 ? (
              <div className="community-v2-empty-note">Loading recent activity...</div>
            ) : activityItems.length > 0 ? (
              <div className="community-v2-activity-list">
                {activityItems.map((item, index) => (
                  <ActivityItem
                    key={`${item.activity_id}-${index}`}
                    item={item}
                    currentUserId={currentUserId}
                    isFollowing={followingIds.has(item.actor.user_id)}
                    followPending={!!followBusyByUser[item.actor.user_id]}
                    onToggleFollow={toggleFollow}
                  />
                ))}
              </div>
            ) : (
              <div className="community-v2-activity-empty">
                <p className="community-v2-empty-title">No recent public activity yet</p>
                <p className="community-v2-empty-note">Follow active users to personalize this stream.</p>
                <div className="community-v2-placeholder-list">
                  <div className="community-v2-placeholder-row" />
                  <div className="community-v2-placeholder-row" />
                  <div className="community-v2-placeholder-row" />
                </div>
              </div>
            )}
          </section>

          {currentUserId ? (
            <section className="community-v2-section">
              <div className="community-v2-section-header">
                <h3 className="community-v2-title">Following</h3>
                <span className="community-v2-count">{following.length}</span>
              </div>
              {followingLoading ? (
                <div className="community-v2-empty-note">Loading following...</div>
              ) : following.length > 0 ? (
                <>
                  <div className="community-v2-people-row">
                    {visibleFollowing.map((person) => (
                      <CompactUserChip
                        key={person.user_id}
                        user={person}
                        currentUserId={currentUserId}
                        isFollowing
                      />
                    ))}
                  </div>
                  {following.length > PREVIEW_COUNT ? (
                    <button
                      type="button"
                      className="community-v2-row-toggle"
                      onClick={() => setFollowingExpanded((prev) => !prev)}
                    >
                      {followingExpanded ? 'Collapse' : `See more (${following.length - PREVIEW_COUNT})`}
                    </button>
                  ) : null}
                </>
              ) : (
                <div className="community-v2-empty-note">Not following anyone yet.</div>
              )}
            </section>
          ) : null}

          {currentUserId ? (
            <section className="community-v2-section">
              <div className="community-v2-section-header">
                <h3 className="community-v2-title">Followers</h3>
                <span className="community-v2-count">{followers.length}</span>
              </div>
              {followersLoading ? (
                <div className="community-v2-empty-note">Loading followers...</div>
              ) : followers.length > 0 ? (
                <>
                  <div className="community-v2-people-row">
                    {visibleFollowers.map((person) => (
                      <CompactUserChip
                        key={person.user_id}
                        user={person}
                        currentUserId={currentUserId}
                        isFollowing={followingIds.has(person.user_id)}
                      />
                    ))}
                  </div>
                  {followers.length > PREVIEW_COUNT ? (
                    <button
                      type="button"
                      className="community-v2-row-toggle"
                      onClick={() => setFollowersExpanded((prev) => !prev)}
                    >
                      {followersExpanded ? 'Collapse' : `See more (${followers.length - PREVIEW_COUNT})`}
                    </button>
                  ) : null}
                </>
              ) : (
                <div className="community-v2-empty-note">No followers yet.</div>
              )}
            </section>
          ) : null}

          <section className="community-v2-section">
            <div className="community-v2-section-header">
              <h3 className="community-v2-title">Discover Active Users</h3>
              <span className="community-v2-count">{discoverCandidates.length}</span>
            </div>
            {visibleDiscover.length > 0 ? (
              <>
                <div className="community-v2-people-row">
                  {visibleDiscover.map((person) => (
                    <CompactUserChip
                      key={person.user_id}
                      user={person}
                      currentUserId={currentUserId}
                      showFollowButton={!!currentUserId}
                      isFollowing={followingIds.has(person.user_id)}
                      followPending={!!followBusyByUser[person.user_id]}
                      onFollowToggle={toggleFollow}
                    />
                  ))}
                </div>
                {discoverCandidates.length > PREVIEW_COUNT ? (
                  <button
                    type="button"
                    className="community-v2-row-toggle"
                    onClick={() => setDiscoverExpanded((prev) => !prev)}
                  >
                    {discoverExpanded ? 'Collapse' : `See more (${discoverCandidates.length - PREVIEW_COUNT})`}
                  </button>
                ) : null}
              </>
            ) : (
              <div className="community-v2-empty-note">
                You are already connected with most active users.
              </div>
            )}
          </section>
        </div>
      ) : null}
    </div>
  );
}
