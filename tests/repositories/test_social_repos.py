import pytest
import uuid

from repositories.follows_repo import FollowsRepository
from repositories.blocks_repo import BlocksRepository
from repositories.mutes_repo import MutesRepository
from repositories.reactions_repo import ReactionsRepository
from repositories.clubs_repo import ClubsRepository
from repositories.feed_repo import FeedRepository


@pytest.mark.repo
def test_follows_repo_basic_operations(tmp_path):
    """Test basic follow/unfollow operations."""
    root = str(tmp_path)
    repo = FollowsRepository(root)
    
    user1 = 100
    user2 = 200
    
    # Follow
    assert repo.follow(user1, user2) is True
    assert repo.is_following(user1, user2) is True
    assert repo.follow(user1, user2) is False  # Already following
    
    # Unfollow
    assert repo.unfollow(user1, user2) is True
    assert repo.is_following(user1, user2) is False
    assert repo.unfollow(user1, user2) is False  # Not following
    
    # Cannot follow self
    with pytest.raises(ValueError, match="Cannot follow yourself"):
        repo.follow(user1, user1)


@pytest.mark.repo
def test_blocks_repo_basic_operations(tmp_path):
    """Test basic block/unblock operations."""
    root = str(tmp_path)
    repo = BlocksRepository(root)
    
    user1 = 100
    user2 = 200
    
    # Block
    assert repo.block(user1, user2) is True
    assert repo.is_blocked(user1, user2) is True
    assert repo.block(user1, user2) is False  # Already blocked
    
    # Unblock
    assert repo.unblock(user1, user2) is True
    assert repo.is_blocked(user1, user2) is False
    assert repo.unblock(user1, user2) is False  # Not blocked
    
    # Bidirectional check
    repo.block(user1, user2)
    assert repo.are_blocked(user1, user2) is True
    
    # Cannot block self
    with pytest.raises(ValueError, match="Cannot block yourself"):
        repo.block(user1, user1)


@pytest.mark.repo
def test_mutes_repo_basic_operations(tmp_path):
    """Test basic mute/unmute operations."""
    root = str(tmp_path)
    repo = MutesRepository(root)
    
    user1 = 100
    user2 = 200
    
    # Mute
    assert repo.mute(user1, user2) is True
    assert repo.is_muted(user1, user2) is True
    assert repo.mute(user1, user2) is False  # Already muted
    
    # Unmute
    assert repo.unmute(user1, user2) is True
    assert repo.is_muted(user1, user2) is False
    assert repo.unmute(user1, user2) is False  # Not muted
    
    # Cannot mute self
    with pytest.raises(ValueError, match="Cannot mute yourself"):
        repo.mute(user1, user1)


@pytest.mark.repo
def test_reactions_repo_basic_operations(tmp_path):
    """Test basic reaction operations."""
    root = str(tmp_path)
    feed_repo = FeedRepository(root)
    reactions_repo = ReactionsRepository(root)
    
    user1 = 100
    feed_item_uuid = feed_repo.create_feed_item(
        actor_user_id=user1,
        visibility="public",
        title="Test feed item",
    )
    
    # Add reaction
    reaction_uuid = reactions_repo.add_reaction(feed_item_uuid, user1, "like")
    assert reaction_uuid is not None
    assert reactions_repo.has_reacted(feed_item_uuid, user1, "like") is True
    
    # Remove reaction
    assert reactions_repo.remove_reaction(feed_item_uuid, user1, "like") is True
    assert reactions_repo.has_reacted(feed_item_uuid, user1, "like") is False
    
    # Add again (should work)
    reactions_repo.add_reaction(feed_item_uuid, user1, "like")
    counts = reactions_repo.get_reaction_counts(feed_item_uuid)
    assert counts.get("like", 0) == 1


@pytest.mark.repo
def test_clubs_repo_basic_operations(tmp_path):
    """Test basic club operations."""
    root = str(tmp_path)
    repo = ClubsRepository(root)
    
    owner = 100
    member = 200
    
    # Create club
    club_id = repo.create_club(owner, "Test Club", "A test club")
    assert club_id is not None
    
    # Get club
    club = repo.get_club(club_id)
    assert club is not None
    assert club["name"] == "Test Club"
    assert club["owner_user_id"] == str(owner)
    
    # Owner should be a member
    assert repo.is_member(club_id, owner) is True
    
    # Add member
    assert repo.add_member(club_id, member) is True
    assert repo.is_member(club_id, member) is True
    assert repo.add_member(club_id, member) is False  # Already a member
    
    # Remove member
    assert repo.remove_member(club_id, member) is True
    assert repo.is_member(club_id, member) is False
    
    # Get members
    members = repo.get_members(club_id)
    assert len(members) == 1  # Only owner
    assert members[0]["user_id"] == str(owner)
    assert members[0]["role"] == "owner"

