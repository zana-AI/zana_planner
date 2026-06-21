"""
Repository for the challenges engine (challenges, decks, items, participants, attempts).

Follows the existing raw-SQL + get_db_session() pattern. v1 is self-contained:
streak and leaderboard are computed directly from challenge_attempts. The nullable
challenges.club_id reserves the Option-A club/promise backing for a later step.
See docs/CHALLENGES_DESIGN.md.
"""
from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso

# A user's friendly name, best-effort, from the users table.
_NAME_EXPR = "COALESCE(u.display_name, u.first_name, u.username, u.user_id)"


def _new_id() -> str:
    return uuid.uuid4().hex


def _now_iso() -> str:
    return utc_now_iso()


def _days_ago_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def _decode_options(raw: Optional[str]) -> Optional[List[str]]:
    if not raw:
        return None
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else None
    except (ValueError, TypeError):
        return None


class ChallengesRepository:
    # ------------------------------------------------------------------
    # Directory / read
    # ------------------------------------------------------------------

    def list_visible(self, user_id: int, include_unlisted: bool = False) -> List[dict]:
        """Public challenge directory, with participant count + whether the user joined."""
        user = str(user_id)
        visibility_filter = "" if include_unlisted else "AND c.visibility = 'public'"
        with get_db_session() as session:
            rows = session.execute(
                text(f"""
                    SELECT c.challenge_id, c.host_user_id, c.title, c.description,
                           c.activity_type, c.cadence, c.visibility, c.status,
                           {_NAME_EXPR} AS host_name,
                           (SELECT COUNT(*) FROM challenge_participants p
                              WHERE p.challenge_id = c.challenge_id) AS participant_count,
                           EXISTS (SELECT 1 FROM challenge_participants p
                              WHERE p.challenge_id = c.challenge_id AND p.user_id = :user_id) AS joined
                    FROM challenges c
                    LEFT JOIN users u ON u.user_id = c.host_user_id
                    WHERE c.status = 'active' {visibility_filter}
                    ORDER BY participant_count DESC, c.created_at_utc DESC
                """),
                {"user_id": user},
            ).mappings().fetchall()
            return [self._challenge_summary(r) for r in rows]

    def get(self, challenge_id: str, user_id: int) -> Optional[dict]:
        user = str(user_id)
        with get_db_session() as session:
            row = session.execute(
                text(f"""
                    SELECT c.challenge_id, c.host_user_id, c.title, c.description,
                           c.activity_type, c.cadence, c.visibility, c.status,
                           {_NAME_EXPR} AS host_name,
                           (SELECT COUNT(*) FROM challenge_participants p
                              WHERE p.challenge_id = c.challenge_id) AS participant_count,
                           EXISTS (SELECT 1 FROM challenge_participants p
                              WHERE p.challenge_id = c.challenge_id AND p.user_id = :user_id) AS joined
                    FROM challenges c
                    LEFT JOIN users u ON u.user_id = c.host_user_id
                    WHERE c.challenge_id = :challenge_id
                """),
                {"challenge_id": challenge_id, "user_id": user},
            ).mappings().fetchone()
            return self._challenge_summary(row) if row else None

    def get_by_source_key(self, source_key: str) -> Optional[str]:
        """Resolve a startapp deep-link token to a challenge_id."""
        if not source_key:
            return None
        with get_db_session() as session:
            row = session.execute(
                text("SELECT challenge_id FROM challenges WHERE source_key = :k LIMIT 1"),
                {"k": source_key},
            ).fetchone()
            return row[0] if row else None

    # ------------------------------------------------------------------
    # Membership
    # ------------------------------------------------------------------

    def join(self, challenge_id: str, user_id: int, source: Optional[str] = None) -> bool:
        """Subscribe the user to the challenge (idempotent). Returns False if challenge missing."""
        return self.ensure_subscription(challenge_id, user_id, source) is not None

    def challenges_with_reminder_at(self, hhmm: str) -> List[dict]:
        """Active challenges whose daily reminder time matches HH:MM (used by the reminder sweeper)."""
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT challenge_id, source_key, title
                    FROM challenges
                    WHERE status = 'active' AND reminder_local_time = :hhmm
                """),
                {"hhmm": hhmm},
            ).mappings().fetchall()
            return [dict(r) for r in rows]

    def list_subscribed_user_ids(self, challenge_id: str) -> List[str]:
        """Active subscribers (participants with a backing promise) of a challenge."""
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT user_id FROM challenge_participants
                    WHERE challenge_id = :cid AND promise_uuid IS NOT NULL
                """),
                {"cid": challenge_id},
            ).fetchall()
            return [str(r[0]) for r in rows]

    def participant_promise_uuid(self, challenge_id: str, user_id: int) -> Optional[str]:
        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT promise_uuid FROM challenge_participants
                    WHERE challenge_id = :cid AND user_id = :uid
                """),
                {"cid": challenge_id, "uid": str(user_id)},
            ).fetchone()
            return row[0] if row and row[0] else None

    def ensure_subscription(self, challenge_id: str, user_id: int, source: Optional[str] = None) -> Optional[str]:
        """Subscribe the user to the challenge and return their backing promise_uuid.

        Idempotent: if already subscribed (participant row has a promise_uuid) it returns it.
        Subscribing reuses the existing template→promise/instance machinery so the challenge
        becomes a real count promise on My Week, plus club membership + promise_club_shares so
        the cohort leaderboard can rank it. Returns None if the challenge is missing.
        """
        from repositories.instances_repo import InstancesRepository
        from repositories.clubs_repo import ClubsRepository

        user = str(user_id)
        with get_db_session() as session:
            row = session.execute(
                text("SELECT template_id, club_id FROM challenges WHERE challenge_id = :cid"),
                {"cid": challenge_id},
            ).fetchone()
            if not row:
                return None
            template_id, club_id = row[0], row[1]
            existing = session.execute(
                text("SELECT promise_uuid FROM challenge_participants WHERE challenge_id = :cid AND user_id = :uid"),
                {"cid": challenge_id, "uid": user},
            ).fetchone()
        if existing and existing[0]:
            return existing[0]

        promise_uuid: Optional[str] = None
        # Older challenges may predate the template/club backing — record a bare participant then.
        if template_id:
            result = InstancesRepository().subscribe_template(user_id, template_id, visibility="public")
            promise_uuid = result.get("promise_uuid")
            if club_id and promise_uuid:
                clubs = ClubsRepository()
                clubs.add_member(club_id, user_id)
                clubs.share_promise_to_club(promise_uuid, club_id)

        with get_db_session() as session:
            session.execute(
                text("""
                    INSERT INTO challenge_participants (challenge_id, user_id, joined_at_utc, source, promise_uuid)
                    VALUES (:cid, :uid, :ts, :src, :puuid)
                    ON CONFLICT (challenge_id, user_id)
                    DO UPDATE SET promise_uuid = COALESCE(challenge_participants.promise_uuid, EXCLUDED.promise_uuid)
                """),
                {"cid": challenge_id, "uid": user, "ts": _now_iso(), "src": source, "puuid": promise_uuid},
            )
        return promise_uuid

    # ------------------------------------------------------------------
    # Play loop
    # ------------------------------------------------------------------

    def get_due_deck(self, challenge_id: str, user_id: int) -> Optional[dict]:
        """The next released deck the user hasn't attempted yet, with its items.

        MCQ answers are NOT revealed (grading is server-side); flashcards include `back`.
        Returns None when the user is caught up.
        """
        user = str(user_id)
        now = _now_iso()
        with get_db_session() as session:
            activity_row = session.execute(
                text("SELECT activity_type FROM challenges WHERE challenge_id = :cid"),
                {"cid": challenge_id},
            ).fetchone()
            if not activity_row:
                return None
            activity_type = activity_row[0]

            deck = session.execute(
                text("""
                    SELECT d.deck_id, d.title, d.position
                    FROM challenge_decks d
                    WHERE d.challenge_id = :cid
                      AND (d.release_at IS NULL OR d.release_at <= :now)
                      AND NOT EXISTS (
                          SELECT 1 FROM challenge_attempts a
                          WHERE a.deck_id = d.deck_id AND a.user_id = :uid
                      )
                    ORDER BY d.position, d.created_at_utc
                    LIMIT 1
                """),
                {"cid": challenge_id, "now": now, "uid": user},
            ).mappings().fetchone()
            if not deck:
                return None

            item_rows = session.execute(
                text("""
                    SELECT item_id, position, front, back, example, options
                    FROM challenge_items
                    WHERE deck_id = :deck_id
                    ORDER BY position, created_at_utc
                """),
                {"deck_id": deck["deck_id"]},
            ).mappings().fetchall()

            items = [self._public_item(r, activity_type) for r in item_rows]
            return {
                "deck_id": deck["deck_id"],
                "title": deck["title"],
                "activity_type": activity_type,
                "items": items,
            }

    def complete_deck(self, challenge_id: str, deck_id: str, user_id: int, answers: List[dict]) -> dict:
        """Record one attempt per answer, grading server-side. Returns score + streak."""
        user = str(user_id)
        ts = _now_iso()
        correct = 0
        with get_db_session() as session:
            # Map item_id -> correct answer for this deck (authoritative grading).
            back_rows = session.execute(
                text("SELECT item_id, back FROM challenge_items WHERE deck_id = :deck_id"),
                {"deck_id": deck_id},
            ).mappings().fetchall()
            back_by_item = {r["item_id"]: (r["back"] or "") for r in back_rows}

            for ans in answers:
                item_id = ans.get("item_id")
                if item_id not in back_by_item:
                    continue
                response = ans.get("response")
                is_correct = self._grade(response, back_by_item[item_id])
                correct += is_correct
                session.execute(
                    text("""
                        INSERT INTO challenge_attempts
                            (attempt_id, challenge_id, deck_id, item_id, user_id,
                             response, is_correct, answered_at_utc, time_ms)
                        VALUES (:aid, :cid, :deck, :item, :uid, :resp, :ok, :ts, :tms)
                    """),
                    {
                        "aid": _new_id(),
                        "cid": challenge_id,
                        "deck": deck_id,
                        "item": item_id,
                        "uid": user,
                        "resp": response,
                        "ok": is_correct,
                        "ts": ts,
                        "tms": ans.get("time_ms"),
                    },
                )

        total = len([a for a in answers if a.get("item_id") in back_by_item])
        score_pct = round(100.0 * correct / total) if total else 0

        # Record one scored check-in for today on the backing promise. This single action
        # drives BOTH the streak (activity) and the club leaderboard (the non-binary score).
        streak = 0
        promise_uuid = self.ensure_subscription(challenge_id, user_id, source="play")
        if promise_uuid:
            from repositories.actions_repo import ActionsRepository
            ActionsRepository().append_scored_checkin(user_id, promise_uuid, float(score_pct))
            streak = ActionsRepository().get_checkin_streak(user_id, promise_uuid)

        return {
            "deck_id": deck_id,
            "total": total,
            "correct": correct,
            "score_pct": score_pct,
            "streak": streak,
        }

    # ------------------------------------------------------------------
    # Streak + leaderboard (self-contained from attempts)
    # ------------------------------------------------------------------

    def get_streak(self, challenge_id: str, user_id: int) -> int:
        """Consecutive days (ending today or yesterday) with at least one attempt."""
        user = str(user_id)
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT DISTINCT substr(answered_at_utc, 1, 10) AS d
                    FROM challenge_attempts
                    WHERE challenge_id = :cid AND user_id = :uid
                    ORDER BY d DESC
                """),
                {"cid": challenge_id, "uid": user},
            ).fetchall()
        days = [r[0] for r in rows if r[0]]
        if not days:
            return 0
        today = datetime.now(timezone.utc).date()
        most_recent = datetime.strptime(days[0], "%Y-%m-%d").date()
        if (today - most_recent).days > 1:
            return 0  # streak already broken
        streak = 0
        cursor = most_recent
        day_set = set(days)
        while cursor.strftime("%Y-%m-%d") in day_set:
            streak += 1
            cursor = cursor - timedelta(days=1)
        return streak

    def leaderboard(self, challenge_id: str, window_days: int = 7, limit: int = 20) -> List[dict]:
        """Cohort leaderboard reusing the club leaderboard model: rank each member by the
        average non-binary daily score of their backing promise over the rolling window
        (missing days count as 0), tie-broken by freeze-streak. Replaces the old
        challenge_attempts counter so there's one score-based leaderboard concept.
        """
        from datetime import datetime, timedelta, timezone
        from repositories.actions_repo import ActionsRepository

        today = datetime.now(timezone.utc).date()
        window_start = (today - timedelta(days=window_days - 1)).isoformat()

        with get_db_session() as session:
            club_row = session.execute(
                text("SELECT club_id FROM challenges WHERE challenge_id = :cid"),
                {"cid": challenge_id},
            ).fetchone()
            if not club_row or not club_row[0]:
                return []
            club_id = club_row[0]

            rows = session.execute(
                text(f"""
                    SELECT cm.user_id AS user_id,
                           {_NAME_EXPR} AS name,
                           p.promise_uuid AS promise_uuid,
                           substr(a.at_utc, 1, 10) AS d,
                           a.score AS score
                    FROM club_members cm
                    JOIN promise_club_shares pcs ON pcs.club_id = cm.club_id
                    JOIN promises p
                      ON p.promise_uuid = pcs.promise_uuid
                     AND p.user_id = cm.user_id
                     AND p.is_deleted = 0
                    LEFT JOIN users u ON u.user_id = cm.user_id
                    LEFT JOIN actions a
                      ON a.user_id = cm.user_id
                     AND a.promise_uuid = p.promise_uuid
                     AND a.action_type = 'club_checkin'
                     AND substr(a.at_utc, 1, 10) >= :ws
                    WHERE cm.club_id = :club AND cm.status = 'active'
                """),
                {"club": club_id, "ws": window_start},
            ).mappings().fetchall()

        members: dict[str, dict] = {}
        for r in rows:
            uid = str(r["user_id"])
            m = members.setdefault(uid, {"name": r["name"] or uid, "promise_uuid": r["promise_uuid"], "days": {}})
            if r["d"] and r["score"] is not None:
                m["days"][r["d"]] = float(r["score"])

        arepo = ActionsRepository()
        entries = []
        for uid, m in members.items():
            score_percent = round(sum(m["days"].values()) / window_days, 1) if m["days"] else 0.0
            streak = arepo.get_checkin_streak(uid, m["promise_uuid"]) if m["promise_uuid"] else 0
            entries.append({
                "user_id": uid,
                "name": m["name"],
                "score_percent": score_percent,
                "streak": streak,
                "active_days": len(m["days"]),
            })
        entries.sort(key=lambda e: (-e["score_percent"], -e["streak"], str(e["name"]).lower()))
        return [{"rank": i + 1, **e} for i, e in enumerate(entries[:limit])]

    def daily_activity_for_promises(self, user_id: int, promise_uuids: List[str]) -> dict:
        """For challenge-backed promises, return {promise_uuid: daily_activity} for the My Week badge.

        daily_activity = { type:'quiz', challenge_id, deck_id|None, status:'due'|'done', score|None }.
        'due' means there's an un-played released deck today; 'done' carries today's score.
        """
        if not promise_uuids:
            return {}
        user = str(user_id)
        uuids = list(promise_uuids)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT cp.promise_uuid, cp.challenge_id
                    FROM challenge_participants cp
                    WHERE cp.user_id = :uid AND cp.promise_uuid = ANY(:uuids)
                """),
                {"uid": user, "uuids": uuids},
            ).mappings().fetchall()
            score_rows = session.execute(
                text("""
                    SELECT promise_uuid, score FROM actions
                    WHERE user_id = :uid AND action_type = 'club_checkin'
                      AND substr(at_utc, 1, 10) = :today AND promise_uuid = ANY(:uuids)
                """),
                {"uid": user, "today": today, "uuids": uuids},
            ).mappings().fetchall()
        today_score = {r["promise_uuid"]: r["score"] for r in score_rows}

        out: dict = {}
        for r in rows:
            puuid, cid = r["promise_uuid"], r["challenge_id"]
            deck = self.get_due_deck(cid, user_id)
            if deck:
                out[puuid] = {"type": "quiz", "challenge_id": cid, "deck_id": deck["deck_id"], "status": "due", "score": None}
            else:
                s = today_score.get(puuid)
                out[puuid] = {"type": "quiz", "challenge_id": cid, "deck_id": None, "status": "done",
                              "score": float(s) if s is not None else None}
        return out

    # ------------------------------------------------------------------
    # Admin authoring (no coach UI in v1 — used by admin ingestion)
    # ------------------------------------------------------------------

    def create_challenge(self, host_user_id: int, data: dict) -> dict:
        from repositories.templates_repo import TemplatesRepository
        from repositories.clubs_repo import ClubsRepository

        cid = _new_id()
        ts = _now_iso()
        title = data["title"]

        # Backing count promise_template — subscribers subscribe to this so the challenge
        # becomes a real count promise on My Week. Hidden from the Explore list (is_active=0).
        template_id = TemplatesRepository().create_template({
            "title": title,
            "description": data.get("description") or "",
            "category": "challenge",
            "metric_type": "count",
            "target_value": 7,
            "is_active": False,
            "created_by_user_id": str(host_user_id),
        })

        # Cohort club (no Telegram group — challenges don't need one).
        club_id = ClubsRepository().create_club(owner_user_id=host_user_id, name=title, visibility="public")

        with get_db_session() as session:
            session.execute(
                text("""
                    INSERT INTO challenges
                        (challenge_id, host_user_id, club_id, template_id, title, description, activity_type,
                         cadence, visibility, source_key, reminder_local_time, created_at_utc, updated_at_utc)
                    VALUES (:cid, :host, :club, :template, :title, :desc, :activity,
                            :cadence, :vis, :src, :reminder, :ts, :ts)
                """),
                {
                    "cid": cid,
                    "host": str(host_user_id),
                    "club": club_id,
                    "template": template_id,
                    "title": title,
                    "desc": data.get("description"),
                    "activity": data.get("activity_type", "flashcard"),
                    "cadence": data.get("cadence", "daily"),
                    "vis": data.get("visibility", "public"),
                    "src": data.get("source_key"),
                    "reminder": data.get("reminder_local_time"),
                    "ts": ts,
                },
            )
            # Challenge cohorts have no Telegram group; clear the default 'pending_admin_setup'.
            session.execute(
                text("UPDATE clubs SET telegram_status = 'not_connected' WHERE club_id = :club"),
                {"club": club_id},
            )
        return self.get(cid, host_user_id)

    def add_deck(self, challenge_id: str, title: str, items: List[dict], position: int = 0,
                 release_at: Optional[str] = None) -> dict:
        """Create a deck plus its items in one shot (admin ingestion path)."""
        deck_id = _new_id()
        ts = _now_iso()
        with get_db_session() as session:
            session.execute(
                text("""
                    INSERT INTO challenge_decks (deck_id, challenge_id, title, position, release_at, created_at_utc)
                    VALUES (:deck, :cid, :title, :pos, :rel, :ts)
                """),
                {"deck": deck_id, "cid": challenge_id, "title": title,
                 "pos": position, "rel": release_at, "ts": ts},
            )
            for i, item in enumerate(items):
                options = item.get("options")
                session.execute(
                    text("""
                        INSERT INTO challenge_items
                            (item_id, deck_id, position, front, back, example, media_url, options, created_at_utc)
                        VALUES (:iid, :deck, :pos, :front, :back, :example, :media, :options, :ts)
                    """),
                    {
                        "iid": _new_id(),
                        "deck": deck_id,
                        "pos": i,
                        "front": item["front"],
                        "back": item["back"],
                        "example": item.get("example"),
                        "media": item.get("media_url"),
                        "options": json.dumps(options) if options else None,
                        "ts": ts,
                    },
                )
        return {"deck_id": deck_id, "item_count": len(items)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _grade(response, correct_answer: str) -> int:
        """1 if correct. MCQ: response equals the correct answer. Flashcard: self-graded 'knew'."""
        if response is None:
            return 0
        resp = str(response).strip()
        if resp.lower() in ("knew", "known", "1", "true", "yes"):
            return 1
        return 1 if resp == (correct_answer or "").strip() else 0

    @staticmethod
    def _public_item(row, activity_type: str) -> dict:
        """Shape an item for play, hiding the answer for MCQ."""
        item = {
            "item_id": row["item_id"],
            "position": row["position"],
            "front": row["front"],
            "example": row["example"],
        }
        if activity_type == "multiple_choice":
            options = _decode_options(row["options"]) or []
            # Shuffle per request so the correct answer's position never leaks,
            # regardless of how options were stored (grading is by text, not index).
            options = list(options)
            random.shuffle(options)
            item["options"] = options  # includes the correct answer; client must not know which
        else:
            item["back"] = row["back"]  # flashcards reveal the answer client-side
        return item

    @staticmethod
    def _challenge_summary(row) -> dict:
        return {
            "challenge_id": row["challenge_id"],
            "host_user_id": row["host_user_id"],
            "host_name": row["host_name"] or row["host_user_id"],
            "title": row["title"],
            "description": row["description"],
            "activity_type": row["activity_type"],
            "cadence": row["cadence"],
            "visibility": row["visibility"],
            "status": row["status"],
            "participant_count": int(row["participant_count"] or 0),
            "joined": bool(row["joined"]),
        }
