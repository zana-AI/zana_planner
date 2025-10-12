import os
import csv
from typing import List, Optional
from datetime import datetime
import pandas as pd

from models.models import Action


class ActionsRepository:
    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def _get_file_path(self, user_id: int) -> str:
        return os.path.join(self.root_dir, str(user_id), "actions.csv")

    def _ensure_user_dir(self, user_id: int) -> None:
        os.makedirs(os.path.join(self.root_dir, str(user_id)), exist_ok=True)

    def _ensure_file_exists(self, user_id: int) -> None:
        """Ensure actions.csv exists. In the legacy format we DO NOT write a header."""
        file_path = self._get_file_path(user_id)
        if not os.path.exists(file_path):
            self._ensure_user_dir(user_id)
            # just create the empty file, no header
            open(file_path, "a").close()

    # ---- WRITE (legacy 4-column format) ----
    def append_action(self, action: Action) -> None:
        """
        Append in legacy format: date, time, promise_id, time_spent
        Example: 2025-01-19,21:33,P06,0.36
        """
        self._ensure_file_exists(action.user_id)
        file_path = self._get_file_path(action.user_id)

        at = action.at or datetime.now()
        # NOTE: we keep whatever tz `at` has; format is just date + HH:MM
        date_str = at.strftime("%Y-%m-%d")
        time_str = at.strftime("%H:%M")

        with open(file_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([date_str, time_str, action.promise_id, action.time_spent])

    # ---- READ (map legacy rows -> Action objects) ----
    def list_actions(self, user_id: int, since: Optional[datetime] = None) -> List[Action]:
        """
        Read legacy CSV (no header) and return Action objects.
        """
        file_path = self._get_file_path(user_id)
        if not os.path.exists(file_path):
            return []

        try:
            # Legacy: 4 columns, no header
            df = pd.read_csv(
                file_path,
                header=None,
                names=["date", "time", "promise_id", "time_spent"],
                dtype={"date": str, "time": str, "promise_id": str, "time_spent": float},
            )
            if df.empty:
                return []
            df = df.dropna(how="any")  # drop malformed lines silently

            # Combine date + time to a timestamp (naive)
            dt = pd.to_datetime(df["date"] + " " + df["time"], errors="coerce")
            actions: List[Action] = []
            for i, row in df.iterrows():
                at = dt.iloc[i]
                if pd.isna(at):
                    continue  # skip malformed lines silently

                if since and at.to_pydatetime() < since:
                    continue

                actions.append(
                    Action(
                        user_id=user_id,
                        promise_id=str(row["promise_id"]),
                        action="log_time",                     # legacy files don’t store action type
                        time_spent=float(row["time_spent"]),
                        at=at.to_pydatetime(),
                    )
                )
            return actions
        except Exception:
            return []

    def last_action_for_promise(self, user_id: int, promise_id: str) -> Optional[Action]:
        actions = self.list_actions(user_id)
        ps = [a for a in actions if a.promise_id == promise_id]
        return max(ps, key=lambda a: a.at) if ps else None

    # ---- DataFrame view in legacy shape ----
    def get_actions_df(self, user_id: int) -> pd.DataFrame:
        """
        Return DataFrame with legacy columns: ['date','time','promise_id','time_spent'].
        """
        file_path = self._get_file_path(user_id)
        if not os.path.exists(file_path):
            return pd.DataFrame(columns=["date", "time", "promise_id", "time_spent"])

        try:
            df = pd.read_csv(
                file_path,
                header=None,
                names=["date", "time", "promise_id", "time_spent"],
                dtype={"date": str, "time": str, "promise_id": str, "time_spent": float},
            )
            return df if not df.empty else pd.DataFrame(columns=["date", "time", "promise_id", "time_spent"])
        except Exception:
            return pd.DataFrame(columns=["date", "time", "promise_id", "time_spent"])
