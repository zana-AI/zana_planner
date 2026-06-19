"""
Challenge endpoints: directory, join, async play loop (deck → complete), leaderboard.

v1 interactive-challenge engine (flashcard + multiple-choice). See docs/CHALLENGES_DESIGN.md.
Admin ingestion endpoints seed content from a host/teacher's vocab lists (no coach UI yet).
"""

from fastapi import APIRouter, HTTPException, Depends

from ..dependencies import get_current_user, get_admin_user
from ..schemas import (
    ChallengeSummary,
    ChallengeJoinRequest,
    ChallengeDeckOut,
    ChallengeCompleteRequest,
    ChallengeCompleteResult,
    ChallengeLeaderboardEntry,
    ChallengeCreateRequest,
    ChallengeDeckIn,
)
from repositories.challenges_repo import ChallengesRepository
from utils.logger import get_logger

router = APIRouter(prefix="/api", tags=["challenges"])
logger = get_logger(__name__)


def _repo() -> ChallengesRepository:
    return ChallengesRepository()


# ---------------------------------------------------------------------------
# Directory / detail
# ---------------------------------------------------------------------------

@router.get("/challenges", response_model=list[ChallengeSummary])
async def list_challenges(user_id: int = Depends(get_current_user)):
    """Public challenge directory."""
    return _repo().list_visible(user_id)


@router.get("/challenges/by-source/{source_key}", response_model=ChallengeSummary)
async def get_challenge_by_source(source_key: str, user_id: int = Depends(get_current_user)):
    """Resolve a startapp deep-link token to its challenge (entry funnel)."""
    repo = _repo()
    challenge_id = repo.get_by_source_key(source_key)
    if not challenge_id:
        raise HTTPException(status_code=404, detail="Challenge not found for that link")
    challenge = repo.get(challenge_id, user_id)
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return challenge


@router.get("/challenges/{challenge_id}", response_model=ChallengeSummary)
async def get_challenge(challenge_id: str, user_id: int = Depends(get_current_user)):
    challenge = _repo().get(challenge_id, user_id)
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return challenge


# ---------------------------------------------------------------------------
# Membership + play loop
# ---------------------------------------------------------------------------

@router.post("/challenges/{challenge_id}/join", response_model=ChallengeSummary)
async def join_challenge(
    challenge_id: str,
    body: ChallengeJoinRequest,
    user_id: int = Depends(get_current_user),
):
    repo = _repo()
    if not repo.join(challenge_id, user_id, source=body.source):
        raise HTTPException(status_code=404, detail="Challenge not found")
    return repo.get(challenge_id, user_id)


@router.get("/challenges/{challenge_id}/deck", response_model=ChallengeDeckOut)
async def get_due_deck(challenge_id: str, user_id: int = Depends(get_current_user)):
    """The next released deck the user hasn't completed. 404 when caught up."""
    deck = _repo().get_due_deck(challenge_id, user_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="No deck due — you're all caught up")
    return deck


@router.post(
    "/challenges/{challenge_id}/decks/{deck_id}/complete",
    response_model=ChallengeCompleteResult,
)
async def complete_deck(
    challenge_id: str,
    deck_id: str,
    body: ChallengeCompleteRequest,
    user_id: int = Depends(get_current_user),
):
    repo = _repo()
    # Auto-join on first play so the participant count + leaderboard include them.
    repo.join(challenge_id, user_id, source="play")
    answers = [a.model_dump() for a in body.answers]
    return repo.complete_deck(challenge_id, deck_id, user_id, answers)


@router.get("/challenges/{challenge_id}/leaderboard", response_model=list[ChallengeLeaderboardEntry])
async def challenge_leaderboard(challenge_id: str, user_id: int = Depends(get_current_user)):
    return _repo().leaderboard(challenge_id)


# ---------------------------------------------------------------------------
# Admin authoring / ingestion (no coach UI in v1)
# ---------------------------------------------------------------------------

@router.post("/admin/challenges", response_model=ChallengeSummary, status_code=201)
async def admin_create_challenge(
    body: ChallengeCreateRequest,
    admin_id: int = Depends(get_admin_user),
):
    host_user_id = body.host_user_id if body.host_user_id is not None else admin_id
    return _repo().create_challenge(host_user_id, body.model_dump(exclude={"host_user_id"}))


@router.post("/admin/challenges/{challenge_id}/decks", status_code=201)
async def admin_add_deck(
    challenge_id: str,
    body: ChallengeDeckIn,
    admin_id: int = Depends(get_admin_user),
):
    if not _repo().get(challenge_id, admin_id):
        raise HTTPException(status_code=404, detail="Challenge not found")
    items = [item.model_dump() for item in body.items]
    return _repo().add_deck(
        challenge_id, body.title, items, position=body.position, release_at=body.release_at
    )
