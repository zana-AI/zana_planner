import { useCallback, useEffect, useMemo, useState, type FormEvent, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient, ApiError } from '../api/client';
import { ActivityItem } from './community/ActivityItem';
import { CompactUserChip } from './community/CompactUserChip';
import { AvatarStack } from './ui/AvatarStack';
import type { ClubSummary, PublicActivityItem, PublicUser, UserInfo } from '../types';
import { getDevInitData, useTelegramWebApp } from '../hooks/useTelegramWebApp';

const PREVIEW_COUNT = 8;
const ACTIVITY_FETCH_COUNT = 60;
const ACTIVITY_PAGE_SIZE = 10;

type CommunityFeedItem = {
  item: PublicActivityItem;
  mergedCount: number;
};

function mergeSimilarActivity(items: PublicActivityItem[]): CommunityFeedItem[] {
  const grouped = new Map<string, CommunityFeedItem>();
  const orderedGroups: CommunityFeedItem[] = [];

  for (const item of items) {
    const key = [
      item.actor.user_id,
      item.action_type || item.action_label,
      item.promise_id || item.promise_text || 'general',
    ].join('|');
    const existing = grouped.get(key);

    if (existing) {
      existing.mergedCount += 1;
      existing.item.duration_minutes =
        (existing.item.duration_minutes || 0) + (item.duration_minutes || 0) || undefined;
      continue;
    }

    const groupItem = { item: { ...item }, mergedCount: 1 };
    grouped.set(key, groupItem);
    orderedGroups.push(groupItem);
  }

  return orderedGroups.map((group) => {
    if (group.mergedCount === 1) {
      return group;
    }

    return {
      ...group,
      item: {
        ...group.item,
        activity_id: `${group.item.activity_id}-merged-${group.mergedCount}`,
        action_label: `${group.item.action_label || 'updated progress'} ${group.mergedCount} times`,
      },
    };
  });
}

function buildMomentumActivity(users: PublicUser[]): CommunityFeedItem[] {
  return users
    .filter((person) => (person.weekly_activity_count ?? 0) >= 3 && person.last_activity_at_utc)
    .slice(0, 3)
    .map((person) => ({
      mergedCount: 1,
      item: {
        activity_id: `momentum-${person.user_id}-${person.last_activity_at_utc}`,
        action_type: 'momentum',
        action_label: `kept momentum with ${person.weekly_activity_count} public updates this week`,
        timestamp_utc: person.last_activity_at_utc || new Date().toISOString(),
        actor: {
          user_id: person.user_id,
          first_name: person.first_name,
          last_name: person.last_name,
          display_name: person.display_name,
          username: person.username,
          avatar_path: person.avatar_path,
          avatar_file_unique_id: person.avatar_file_unique_id,
          weekly_activity_count: person.weekly_activity_count,
          last_activity_at_utc: person.last_activity_at_utc,
        },
      },
    }));
}

export function UsersPage() {
  const navigate = useNavigate();
  const { user, initData, isReady } = useTelegramWebApp();
  const [discoverUsers, setDiscoverUsers] = useState<PublicUser[]>([]);
  const [activityItems, setActivityItems] = useState<PublicActivityItem[]>([]);
  const [clubs, setClubs] = useState<ClubSummary[]>([]);
  const [followers, setFollowers] = useState<PublicUser[]>([]);
  const [following, setFollowing] = useState<PublicUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [activityLoading, setActivityLoading] = useState(false);
  const [clubsLoading, setClubsLoading] = useState(false);
  const [creatingClub, setCreatingClub] = useState(false);
  const [followersLoading, setFollowersLoading] = useState(false);
  const [followingLoading, setFollowingLoading] = useState(false);
  const [error, setError] = useState('');
  const [clubError, setClubError] = useState('');
  const [showCreateClubDialog, setShowCreateClubDialog] = useState(false);
  const [clubBusyById, setClubBusyById] = useState<Record<string, boolean>>({});
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [followBusyByUser, setFollowBusyByUser] = useState<Record<string, boolean>>({});
  const [followingExpanded, setFollowingExpanded] = useState(false);
  const [followersExpanded, setFollowersExpanded] = useState(false);
  const [discoverExpanded, setDiscoverExpanded] = useState(false);
  const [activityExpanded, setActivityExpanded] = useState(false);
  const [clubForm, setClubForm] = useState({
    name: '',
    visibility: 'private' as 'private' | 'public',
    promise_text: '',
    target_count_per_week: 2,
  });

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
    setClubsLoading(true);
    setError('');
    try {
      if (authData) {
        apiClient.setInitData(authData);
      }

      const [activityRes, usersRes, clubsRes] = await Promise.all([
        apiClient.getPublicActivity(ACTIVITY_FETCH_COUNT),
        apiClient.getPublicUsers(24),
        apiClient.getMyClubs().catch(() => ({ clubs: [], total: 0 })),
      ]);

      setActivityItems(activityRes.items);
      setDiscoverUsers(usersRes.users.filter((publicUser) => publicUser.user_id !== currentUserId));
      setClubs(clubsRes.clubs);
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
      setClubsLoading(false);
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
  const activityFeed = useMemo(() => {
    const mergedActivity = mergeSimilarActivity(activityItems);
    const momentumActivity = buildMomentumActivity(discoverUsers);

    return [...momentumActivity, ...mergedActivity].sort(
      (left, right) => new Date(right.item.timestamp_utc).getTime() - new Date(left.item.timestamp_utc).getTime()
    );
  }, [activityItems, discoverUsers]);

  const visibleFollowing = followingExpanded ? following : following.slice(0, PREVIEW_COUNT);
  const visibleFollowers = followersExpanded ? followers : followers.slice(0, PREVIEW_COUNT);
  const visibleDiscover = discoverExpanded ? discoverCandidates : discoverCandidates.slice(0, PREVIEW_COUNT);
  const visibleActivity = activityExpanded ? activityFeed : activityFeed.slice(0, ACTIVITY_PAGE_SIZE);

  const handleCreateClub = useCallback(async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setClubError('');

    const name = clubForm.name.trim();
    const promiseText = clubForm.promise_text.trim();
    if (!name || !promiseText) {
      setClubError('Add a club name and one shared promise.');
      return;
    }

    setCreatingClub(true);
    try {
      const created = await apiClient.createClub({
        name,
        visibility: clubForm.visibility,
        promise_text: promiseText,
        target_count_per_week: clubForm.target_count_per_week,
      });
      setClubs((prev) => [created, ...prev.filter((club) => club.club_id !== created.club_id)]);
      setClubForm({
        name: '',
        visibility: 'private',
        promise_text: '',
        target_count_per_week: 2,
      });
      setShowCreateClubDialog(false);
    } catch (err) {
      console.error('Failed to create club:', err);
      setClubError(err instanceof ApiError ? err.message : 'Failed to create club.');
    } finally {
      setCreatingClub(false);
    }
  }, [clubForm]);

  const handleRemoveClub = useCallback(async (club: ClubSummary) => {
    const isOwner = club.role === 'owner';
    const actionLabel = isOwner ? 'cancel this club' : 'leave this club';
    if (!window.confirm(`Are you sure you want to ${actionLabel}?`)) {
      return;
    }

    setClubError('');
    setClubBusyById((prev) => ({ ...prev, [club.club_id]: true }));
    try {
      await apiClient.removeMyClub(club.club_id);
      setClubs((prev) => prev.filter((item) => item.club_id !== club.club_id));
    } catch (err) {
      console.error('Failed to remove club:', err);
      setClubError(err instanceof ApiError ? err.message : 'Failed to update club.');
    } finally {
      setClubBusyById((prev) => ({ ...prev, [club.club_id]: false }));
    }
  }, []);

  const handleClubCardKeyDown = useCallback((event: KeyboardEvent<HTMLElement>, club: ClubSummary) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    navigate(`/clubs/${club.club_id}`);
  }, [navigate]);

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
          <section className="community-v2-section community-v2-clubs-section">
            <div className="community-v2-section-header">
              <div>
                <h3 className="community-v2-title">Clubs</h3>
                <p className="community-v2-section-subtitle">Small circles for shared promises.</p>
              </div>
              <div className="community-club-header-actions">
                <span className="community-v2-count">{clubs.length}</span>
                <button
                  type="button"
                  className="community-club-create-trigger"
                  onClick={() => {
                    setClubError('');
                    setShowCreateClubDialog(true);
                  }}
                >
                  Create club
                </button>
              </div>
            </div>

            {clubsLoading && clubs.length === 0 ? (
              <div className="community-v2-empty-note">Loading clubs...</div>
            ) : clubs.length > 0 ? (
              <div className="community-club-grid">
                {clubs.map((club) => (
                  <article
                    className="community-club-card community-club-card-clickable"
                    key={club.club_id}
                    role="button"
                    tabIndex={0}
                    aria-label={`Open ${club.name} club details`}
                    onClick={() => navigate(`/clubs/${club.club_id}`)}
                    onKeyDown={(event) => handleClubCardKeyDown(event, club)}
                  >
                    <div className="community-club-card-header">
                      <h4>{club.name}</h4>
                      <span>{club.visibility}</span>
                    </div>
                    <p>{club.promise_text || 'No shared promise yet'}</p>
                    <div className="community-club-meta">
                      <span className="community-club-members">
                        <AvatarStack users={club.members} size={24} max={4} />
                        {club.member_count} {club.member_count === 1 ? 'member' : 'members'}
                      </span>
                      {club.target_count_per_week ? <span>{club.target_count_per_week}x/week</span> : null}
                      {club.telegram_invite_link && ['ready', 'connected'].includes(club.telegram_status) ? (
                        <a
                          className="community-club-telegram-link"
                          href={club.telegram_invite_link}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(event) => event.stopPropagation()}
                        >
                          Join Telegram
                        </a>
                      ) : (
                        <span>Telegram pending</span>
                      )}
                    </div>
                    {club.role === 'owner' && club.telegram_status !== 'pending_admin_setup' ? null : (
                      <button
                        type="button"
                        className="community-club-remove"
                        disabled={!!clubBusyById[club.club_id]}
                        onClick={(event) => {
                          event.stopPropagation();
                          handleRemoveClub(club);
                        }}
                      >
                        {clubBusyById[club.club_id]
                          ? 'Updating...'
                          : club.role === 'owner'
                            ? 'Cancel club'
                            : 'Leave club'}
                      </button>
                    )}
                  </article>
                ))}
              </div>
            ) : (
              <div className="community-v2-empty-note">No clubs yet.</div>
            )}
          </section>

          {showCreateClubDialog ? (
            <div
              className="modal-overlay"
              role="dialog"
              aria-modal="true"
              aria-labelledby="create-club-title"
              onClick={() => setShowCreateClubDialog(false)}
            >
              <section className="modal-content community-club-dialog" onClick={(event) => event.stopPropagation()}>
                <div className="modal-header">
                  <h3 id="create-club-title" className="modal-title">Create club</h3>
                  <button
                    type="button"
                    className="modal-close"
                    aria-label="Close"
                    disabled={creatingClub}
                    onClick={() => setShowCreateClubDialog(false)}
                  >
                    x
                  </button>
                </div>

                <form className="modal-form community-club-dialog-form" onSubmit={handleCreateClub}>
                  <label className="modal-form-group">
                    <span className="modal-label">Club name</span>
                    <input
                      className="modal-input"
                      value={clubForm.name}
                      onChange={(event) => setClubForm((prev) => ({ ...prev, name: event.target.value }))}
                      placeholder="Tennis friends"
                      maxLength={80}
                      autoFocus
                    />
                  </label>

                  <label className="modal-form-group">
                    <span className="modal-label">Shared promise</span>
                    <input
                      className="modal-input"
                      value={clubForm.promise_text}
                      onChange={(event) => setClubForm((prev) => ({ ...prev, promise_text: event.target.value }))}
                      placeholder="Play tennis"
                      maxLength={160}
                    />
                  </label>

                  <div className="community-club-dialog-row">
                    <label className="modal-form-group">
                      <span className="modal-label">Visibility</span>
                      <select
                        className="modal-input"
                        value={clubForm.visibility}
                        onChange={(event) => setClubForm((prev) => ({
                          ...prev,
                          visibility: event.target.value as 'private' | 'public',
                        }))}
                      >
                        <option value="private">Private</option>
                        <option value="public">Public</option>
                      </select>
                    </label>

                    <label className="modal-form-group">
                      <span className="modal-label">Per week</span>
                      <input
                        className="modal-input"
                        type="number"
                        min={1}
                        max={21}
                        step={1}
                        value={clubForm.target_count_per_week}
                        onChange={(event) => setClubForm((prev) => ({
                          ...prev,
                          target_count_per_week: Number(event.target.value) || 1,
                        }))}
                      />
                    </label>
                  </div>

                  {clubError ? <div className="modal-error">{clubError}</div> : null}

                  <div className="modal-actions">
                    <button
                      type="button"
                      className="modal-button modal-button-secondary"
                      disabled={creatingClub}
                      onClick={() => setShowCreateClubDialog(false)}
                    >
                      Cancel
                    </button>
                    <button type="submit" className="modal-button modal-button-primary" disabled={creatingClub}>
                      {creatingClub ? 'Creating...' : 'Create club'}
                    </button>
                  </div>
                </form>
              </section>
            </div>
          ) : null}

          <section className="community-v2-section community-v2-people-section">
            <div className="community-v2-section-header">
              <h3 className="community-v2-title">Discover Active Users</h3>
              <span className="community-v2-count">{discoverCandidates.length}</span>
            </div>
            {visibleDiscover.length > 0 ? (
              <>
                <div className="community-v2-people-grid">
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

          {currentUserId ? (
            <section className="community-v2-section community-v2-people-section">
              <div className="community-v2-section-header">
                <h3 className="community-v2-title">Following</h3>
                <span className="community-v2-count">{following.length}</span>
              </div>
              {followingLoading ? (
                <div className="community-v2-empty-note">Loading following...</div>
              ) : following.length > 0 ? (
                <>
                  <div className="community-v2-people-grid">
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
            <section className="community-v2-section community-v2-people-section">
              <div className="community-v2-section-header">
                <h3 className="community-v2-title">Followers</h3>
                <span className="community-v2-count">{followers.length}</span>
              </div>
              {followersLoading ? (
                <div className="community-v2-empty-note">Loading followers...</div>
              ) : followers.length > 0 ? (
                <>
                  <div className="community-v2-people-grid">
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

          <section className="community-v2-section community-v2-activity">
            <div className="community-v2-section-header">
              <h3 className="community-v2-title">Recent Activity</h3>
              <span className="community-v2-count">{activityFeed.length}</span>
            </div>

            {activityLoading && activityItems.length === 0 ? (
              <div className="community-v2-empty-note">Loading recent activity...</div>
            ) : activityFeed.length > 0 ? (
              <>
                <div className="community-v2-activity-list">
                  {visibleActivity.map(({ item }, index) => (
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
                {activityFeed.length > ACTIVITY_PAGE_SIZE ? (
                  <button
                    type="button"
                    className="community-v2-row-toggle"
                    onClick={() => setActivityExpanded((prev) => !prev)}
                  >
                    {activityExpanded ? 'Show fewer' : `Show earlier activity (${activityFeed.length - ACTIVITY_PAGE_SIZE})`}
                  </button>
                ) : null}
              </>
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
        </div>
      ) : null}
    </div>
  );
}
