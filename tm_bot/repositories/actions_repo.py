import uuid
from datetime import datetime
from typing import List, Optional

import pandas as pd

from db.legacy_importer import ensure_imported
from db.sqlite_db import (
    connection_for_root,
    dt_to_utc_iso,
    dt_utc_iso_to_local_naive,
    resolve_promise_uuid,
)
from models.models import Action


class ActionsRepository:
    """
    SQLite-backed actions repository.

    Stores timestamps as UTC ISO strings, but returns naive local datetimes for
    backward compatibility with existing code comparisons.
    """

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def append_action(self, action: Action) -> None:
        user = str(action.user_id)
        pid = (action.promise_id or "").strip().upper()
        at_utc = dt_to_utc_iso(action.at, assume_local_tz=True) or dt_to_utc_iso(datetime.now(), assume_local_tz=True)
        if not at_utc:
            return

        with connection_for_root(self.root_dir) as conn:
            # Import promises once so we can link promise_uuid even for old IDs
            ensure_imported(conn, self.root_dir, user, "promises")
            p_uuid = resolve_promise_uuid(conn, user, pid) if pid else None

            conn.execute(
                """
                INSERT INTO actions(
                    action_uuid, user_id, promise_uuid, promise_id_text,
                    action_type, time_spent_hours, at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    str(uuid.uuid4()),
                    user,
                    p_uuid,
                    pid or "",
                    str(action.action or "log_time"),
                    float(action.time_spent or 0.0),
                    at_utc,
                ),
            )

    def list_actions(self, user_id: int, since: Optional[datetime] = None) -> List[Action]:
        user = str(user_id)
        since_utc = dt_to_utc_iso(since, assume_local_tz=True) if since else None

        with connection_for_root(self.root_dir) as conn:
            ensure_imported(conn, self.root_dir, user, "actions")
            if since_utc:
                rows = conn.execute(
                    """
                    SELECT
                        a.action_type, a.time_spent_hours, a.at_utc,
                        COALESCE(p.current_id, a.promise_id_text) AS canonical_promise_id
                    FROM actions a
                    LEFT JOIN promises p ON p.promise_uuid = a.promise_uuid AND p.user_id = a.user_id
                    WHERE a.user_id = ? AND a.at_utc >= ?
                    ORDER BY a.at_utc ASC;
                    """,
                    (user, since_utc),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT
                        a.action_type, a.time_spent_hours, a.at_utc,
                        COALESCE(p.current_id, a.promise_id_text) AS canonical_promise_id
                    FROM actions a
                    LEFT JOIN promises p ON p.promise_uuid = a.promise_uuid AND p.user_id = a.user_id
                    WHERE a.user_id = ?
                    ORDER BY a.at_utc ASC;
                    """,
                    (user,),
                ).fetchall()

        actions: List[Action] = []
        for r in rows:
            at = dt_utc_iso_to_local_naive(r["at_utc"])
            if not at:
                continue
            actions.append(
                Action(
                    user_id=user,
                    promise_id=str(r["canonical_promise_id"] or ""),
                    action=str(r["action_type"] or "log_time"),
                    time_spent=float(r["time_spent_hours"] or 0.0),
                    at=at,
                )
            )
        return actions

    def last_action_for_promise(self, user_id: int, promise_id: str) -> Optional[Action]:
        pid = (promise_id or "").strip().upper()
        if not pid:
            return None
        actions = self.list_actions(user_id)
        ps = [a for a in actions if (a.promise_id or "").strip().upper() == pid]
        return max(ps, key=lambda a: a.at) if ps else None

    def get_actions_df(self, user_id: int) -> pd.DataFrame:
        """
        Return DataFrame with legacy columns: ['date','time','promise_id','time_spent'].
        If pandas is unavailable, returns a list-of-dicts compatible with .to_dict().
        """
        actions = self.list_actions(user_id)
        rows = [
            {
                "date": a.at.strftime("%Y-%m-%d"),
                "time": a.at.strftime("%H:%M"),
                "promise_id": a.promise_id,
                "time_spent": float(a.time_spent or 0.0),
            }
            for a in actions
        ]

        return pd.DataFrame(rows, columns=["date", "time", "promise_id", "time_spent"])
