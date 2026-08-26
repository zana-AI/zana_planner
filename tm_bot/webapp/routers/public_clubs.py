"""
The public club profile — what a stranger sees at xaana.club/<club>.

This is the only router in the app that answers without authentication, and
that is the point: the visitor we are designing for arrives cold from a
creator's Telegram channel and is not logged in. Gating the page behind login
would spend the whole click budget before they see anything, so the page shell
(identity, today's round, the leaderboard) renders anonymously and auth happens
only at the moment they actually play. See docs/CLUBS_MODEL.md §5.

Because the audience is anonymous, every field is filtered here rather than in
the UI:
  * private clubs 404 for non-members (the same as a club that doesn't exist,
    so the endpoint can't be used to probe for club ids),
  * the Telegram *group* invite link is members-only — it's a door, not a
    billboard, unlike the club's outbound channel/website link,
  * members who set their profile private are shown under a stable pseudonym.
"""

from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import FileResponse
from sqlalchemy import text

from ..dependencies import get_current_user_optional
from ..schemas import (
    PublicClubLeaderboardRow,
    PublicClubLink,
    PublicClubProfile,
    PublicClubRound,
    PublicClubViewer,
)
from db.postgres_db import get_db_session
from repositories.challenges_repo import ChallengesRepository
from repositories.clubs_repo import ClubsRepository
from services.club_leaderboard_service import compute_club_leaderboard, resolve_avatar_file
from utils.logger import get_logger
from utils.public_names import initials, public_display_name

router = APIRouter(prefix="/api/public", tags=["public"])
logger = get_logger(__name__)

# How many rows a stranger sees. Short on purpose: the leaderboard is social
# proof here, not a directory, and for a large cohort a long flat ranking is
# demotivating rather than motivating (docs/CLUBS_MODEL.md §6).
_LEADERBOARD_LIMIT = 5


def _iso_date(value: object) -> Optional[str]:
    """compute_club_leaderboard returns `date` objects; the API returns strings."""
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _member_privacy_flags(club_id: str) -> dict:
    """user_id -> {is_private, avatar_public} for this club's active members."""
    with get_db_session() as session:
        rows = session.execute(
            text("""
                SELECT cm.user_id,
                       COALESCE(u.is_private, 0) AS is_private,
                       COALESCE(u.avatar_visibility, 'public') AS avatar_visibility
                FROM club_members cm
                LEFT JOIN users u ON u.user_id = cm.user_id
                WHERE cm.club_id = :club_id AND cm.status = 'active';
            """),
            {"club_id": club_id},
        ).mappings().fetchall()
    return {
        str(row["user_id"]): {
            "is_private": bool(row["is_private"]),
            "avatar_public": str(row["avatar_visibility"]) == "public",
        }
        for row in rows
    }


def _owner_name(owner_user_id: Optional[str]) -> Optional[str]:
    if not owner_user_id:
        return None
    with get_db_session() as session:
        row = session.execute(
            text("""
                SELECT first_name, username, COALESCE(is_private, 0) AS is_private
                FROM users WHERE user_id = :uid LIMIT 1;
            """),
            {"uid": str(owner_user_id)},
        ).mappings().fetchone()
    if not row:
        return None
    return public_display_name(
        str(owner_user_id),
        first_name=row["first_name"],
        username=row["username"],
        is_private=bool(row["is_private"]),
    )


def _link_label(url: str) -> tuple[str, str]:
    """(kind, label) for an outbound URL — a t.me channel keeps its @handle."""
    try:
        parsed = urlparse(url if "//" in url else f"https://{url}")
    except ValueError:
        return "web", url
    host = (parsed.netloc or "").lower().removeprefix("www.")
    handle = parsed.path.strip("/").split("/")[0]
    if host in ("t.me", "telegram.me") and handle:
        # `t.me/+xxxx` and `t.me/joinchat/...` are opaque invite links, not
        # handles — showing them as "@+xxxx" would read as a broken username.
        if handle.startswith("+") or handle == "joinchat":
            return "telegram", "Telegram"
        return "telegram", f"@{handle}"
    return "web", host or url


def _build_links(club: dict, is_member: bool) -> List[PublicClubLink]:
    links: List[PublicClubLink] = []

    external_url = (club.get("external_url") or "").strip()
    if external_url:
        kind, label = _link_label(external_url)
        links.append(PublicClubLink(kind=kind, label=label, url=external_url))

    # The group invite is a private door — only surfaced to people already inside.
    invite = (club.get("telegram_invite_link") or "").strip()
    if invite and is_member and str(club.get("telegram_status")) in ("ready", "connected"):
        links.append(
            PublicClubLink(kind="telegram", label="Group chat", url=invite, members_only=True)
        )

    return links


def _build_round(club_id: str, leaderboard: dict) -> Optional[PublicClubRound]:
    """Today's round: a content deck if the club has one, else its check-in."""
    challenges = ChallengesRepository()
    challenge = challenges.get_active_by_club(club_id)

    if challenge:
        deck = challenges.current_deck_preview(challenge["challenge_id"])
        if deck:
            return PublicClubRound(
                kind="quiz",
                title=str(deck["title"]),
                subtitle=str(challenge.get("title") or ""),
                item_count=int(deck.get("item_count") or 0),
                challenge_id=str(challenge["challenge_id"]),
                activity_type=str(challenge.get("activity_type") or ""),
                cadence=str(challenge.get("cadence") or ""),
            )

    # No content layer — a shared-ledger club (gym pair, Cheenva). The round is
    # the check-in itself, named after whatever the club actually promised.
    promises = leaderboard.get("promises") or []
    if promises:
        return PublicClubRound(
            kind="checkin",
            title=str(promises[0].get("promise_text") or "Today's check-in"),
            subtitle="Check in for today",
            item_count=len(promises),
        )
    return None


def _public_rows(leaderboard: dict, club_id: str) -> List[PublicClubLeaderboardRow]:
    flags = _member_privacy_flags(club_id)
    rows: List[PublicClubLeaderboardRow] = []
    for member in leaderboard.get("members", [])[:_LEADERBOARD_LIMIT]:
        user_id = str(member.get("user_id"))
        member_flags = flags.get(user_id, {"is_private": False, "avatar_public": True})
        name = public_display_name(
            user_id,
            first_name=member.get("first_name"),
            username=member.get("username"),
            is_private=member_flags["is_private"],
        )
        rows.append(
            PublicClubLeaderboardRow(
                rank=int(member.get("rank") or 0),
                name=name,
                initials=initials(name),
                # Only pass an id the avatar endpoint would actually serve, so the
                # page never renders a broken image for a private profile.
                user_id=user_id if member_flags["avatar_public"] and not member_flags["is_private"] else None,
                score_percent=float(member.get("score_percent") or 0.0),
                streak=int(member.get("freeze_streak") or 0),
                daily_activity=[
                    float(day.get("score_percent") or 0.0)
                    for day in member.get("daily_activity", [])
                ],
            )
        )
    return rows


@router.get("/clubs/{club_ref}", response_model=PublicClubProfile)
async def get_public_club(
    club_ref: str,
    viewer_id: Optional[int] = Depends(get_current_user_optional),
):
    """The public landing page payload for one club.

    `club_ref` is a club_id today. Handle resolution (xaana.club/<handle>) lands
    in a follow-up and will resolve to the same club_id before this point.
    """
    clubs_repo = ClubsRepository()
    club = clubs_repo.get_club(club_ref)
    if not club or str(club.get("status") or "active") != "active":
        raise HTTPException(status_code=404, detail="Club not found")

    is_member = bool(viewer_id) and clubs_repo.is_member(club["club_id"], viewer_id)
    if str(club.get("visibility")) != "public" and not is_member:
        # Same response as a missing club, so this can't enumerate private clubs.
        raise HTTPException(status_code=404, detail="Club not found")

    club_id = str(club["club_id"])
    today = datetime.utcnow().date()
    try:
        leaderboard = compute_club_leaderboard(club_id, today=today, limit=_LEADERBOARD_LIMIT)
    except Exception:
        # A failed leaderboard must not take the landing page (and its CTA) down.
        logger.exception("Public club page: leaderboard failed for club %s", club_id)
        leaderboard = {}

    challenge = ChallengesRepository().get_active_by_club(club_id)

    return PublicClubProfile(
        club_id=club_id,
        name=str(club.get("name") or "Club"),
        tagline=str(club.get("club_goal") or "") or None,
        description=str(club.get("description") or "") or None,
        host_name=_owner_name(club.get("owner_user_id")),
        member_count=int(leaderboard.get("member_count") or len(clubs_repo.get_members(club_id))),
        participant_count=int(challenge["participant_count"]) if challenge else None,
        visibility=str(club.get("visibility") or "public"),
        links=_build_links(club, is_member),
        today=_build_round(club_id, leaderboard),
        leaderboard=_public_rows(leaderboard, club_id),
        window_start=_iso_date(leaderboard.get("window_start")),
        window_end=_iso_date(leaderboard.get("window_end")),
        viewer=PublicClubViewer(authenticated=bool(viewer_id), is_member=is_member),
    )


@router.get("/avatars/{user_id}")
async def get_public_avatar(request: Request, user_id: str):
    """Avatar for the public club page — no auth, public-visibility avatars only.

    Separate from `/api/media/avatars/{user_id}`, which keeps its auth
    requirement. Only ids the profile endpoint already chose to expose land
    here, and the visibility check is repeated rather than trusted.
    """
    full_path = resolve_avatar_file(user_id, root_dir=request.app.state.root_dir)
    if not full_path:
        raise HTTPException(status_code=404, detail="Avatar not found")

    media_type = "image/jpeg"
    lowered = full_path.lower()
    if lowered.endswith(".png"):
        media_type = "image/png"
    elif lowered.endswith(".gif"):
        media_type = "image/gif"

    return FileResponse(
        full_path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
