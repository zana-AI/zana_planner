from __future__ import annotations

# Legacy file import functionality has been disabled - all data is in SQLite only
# The following imports and functions are kept for reference but are no longer used

# import csv
# import json
# import os
# import uuid
# from datetime import datetime, timezone
# from typing import Any, Dict, Iterable, Optional

# from db.sqlite_db import (
#     date_from_iso,
#     date_to_iso,
#     dt_to_utc_iso,
#     resolve_promise_uuid,
#     utc_now_iso,
# )

# try:
#     import yaml  # type: ignore
#     YAML_AVAILABLE = True
# except Exception:
#     YAML_AVAILABLE = False


# def _file_mtime_utc_iso(path: str) -> Optional[str]:
#     try:
#         st = os.stat(path)
#         dt = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
#         return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
#     except Exception:
#         return None


# def _already_imported(conn, user_id: str, source: str) -> bool:
#     row = conn.execute(
#         "SELECT 1 FROM legacy_imports WHERE user_id = ? AND source = ? LIMIT 1;",
#         (user_id, source),
#     ).fetchone()
#     return bool(row)


# def _mark_imported(conn, user_id: str, source: str, mtime_utc: Optional[str]) -> None:
#     conn.execute(
#         """
#         INSERT OR REPLACE INTO legacy_imports(user_id, source, source_mtime_utc, imported_at_utc)
#         VALUES (?, ?, ?, ?);
#         """,
#         (user_id, source, mtime_utc, utc_now_iso()),
#     )


def ensure_imported(conn, root_dir: str, user_id: str, source: str) -> None:
    """
    Legacy file import disabled. This function is now a no-op.
    
    All data is stored in SQLite only. Legacy CSV/JSON/YAML files are no longer read.
    """
    # Legacy file import has been disabled - all data is in SQLite
    pass


# def _user_dir(root_dir: str, user_id: str) -> str:
#     return os.path.join(root_dir, str(user_id))


# def _import_promises(conn, root_dir: str, user_id: str) -> None:
#     udir = _user_dir(root_dir, user_id)
#     csv_path = os.path.join(udir, "promises.csv")
#     json_path = os.path.join(udir, "promises.json")
#
#     now = utc_now_iso()
#
#     imported_any = False
#     if os.path.exists(csv_path):
#         try:
#             with open(csv_path, "r", newline="", encoding="utf-8") as f:
#                 reader = csv.DictReader(f)
#                 for row in reader:
#                     _upsert_promise_row(conn, user_id, row, now, event_type="import")
#                     imported_any = True
#         except Exception:
#             pass
#         _mark_imported(conn, user_id, "promises", _file_mtime_utc_iso(csv_path))
#         return
#
#     if os.path.exists(json_path):
#         try:
#             with open(json_path, "r", encoding="utf-8") as f:
#                 data = json.load(f) or []
#             for item in data:
#                 if isinstance(item, dict):
#                     _upsert_promise_row(conn, user_id, item, now, event_type="import")
#                     imported_any = True
#         except Exception:
#             pass
#         _mark_imported(conn, user_id, "promises", _file_mtime_utc_iso(json_path))
#         return
#
#     # No legacy file: still mark imported to avoid re-checking every call
#     _mark_imported(conn, user_id, "promises", None)


# def _boolish(v: Any) -> bool:
#     if isinstance(v, bool):
#         return v
#     if isinstance(v, (int, float)):
#         return bool(v)
#     s = str(v or "").strip().lower()
#     return s in ("true", "1", "yes", "y", "on")


# def _to_float(v: Any, default: float = 0.0) -> float:
#     try:
#         return float(v)
#     except Exception:
#         return default


# def _to_int(v: Any, default: int = 0) -> int:
#     try:
#         return int(float(v))
#     except Exception:
#         return default


# def _upsert_promise_row(conn, user_id: str, row: Dict[str, Any], now: str, event_type: str) -> None:
#     pid = str(row.get("id", "") or "").strip().upper()
#     if not pid:
#         return
#
#     # Find existing by current id
#     existing = conn.execute(
#         "SELECT promise_uuid FROM promises WHERE user_id = ? AND current_id = ? LIMIT 1;",
#         (user_id, pid),
#     ).fetchone()
#     promise_uuid = str(existing["promise_uuid"]) if existing else str(uuid.uuid4())
#
#     text = str(row.get("text", "") or row.get("content", "") or "")
#     hours = _to_float(row.get("hours_per_week", 0.0))
#     recurring = 1 if _boolish(row.get("recurring", False)) else 0
#
#     start_date = str(row.get("start_date", "") or "").strip() or None
#     end_date = str(row.get("end_date", "") or "").strip() or None
#     # Validate dates (optional)
#     start_date_iso = date_to_iso(date_from_iso(start_date)) if start_date else None
#     end_date_iso = date_to_iso(date_from_iso(end_date)) if end_date else None
#
#     angle = _to_int(row.get("angle_deg", 0), 0)
#     radius = _to_int(row.get("radius", 0), 0)
#
#     conn.execute(
#         """
#         INSERT OR REPLACE INTO promises(
#             promise_uuid, user_id, current_id, text, hours_per_week, recurring,
#             start_date, end_date, angle_deg, radius, is_deleted,
#             created_at_utc, updated_at_utc
#         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
#         """,
#         (
#             promise_uuid,
#             user_id,
#             pid,
#             text,
#             hours,
#             recurring,
#             start_date_iso,
#             end_date_iso,
#             angle,
#             radius,
#             0,
#             now,
#             now,
#         ),
#     )
#
#     # Ensure current id is an alias, too
#     conn.execute(
#         """
#         INSERT OR IGNORE INTO promise_aliases(user_id, alias_id, promise_uuid, created_at_utc)
#         VALUES (?, ?, ?, ?);
#         """,
#         (user_id, pid, promise_uuid, now),
#     )
#
#     snapshot = json.dumps(
#         {
#             "id": pid,
#             "text": text,
#             "hours_per_week": hours,
#             "recurring": bool(recurring),
#             "start_date": start_date_iso or "",
#             "end_date": end_date_iso or "",
#             "angle_deg": angle,
#             "radius": radius,
#             "is_deleted": False,
#         },
#         ensure_ascii=False,
#     )
#     conn.execute(
#         """
#         INSERT INTO promise_events(event_uuid, promise_uuid, user_id, event_type, at_utc, snapshot_json)
#         VALUES (?, ?, ?, ?, ?, ?);
#         """,
#         (str(uuid.uuid4()), promise_uuid, user_id, event_type, now, snapshot),
#     )


# def _import_actions(conn, root_dir: str, user_id: str) -> None:
#     udir = _user_dir(root_dir, user_id)
#     path = os.path.join(udir, "actions.csv")
#     if not os.path.exists(path):
#         _mark_imported(conn, user_id, "actions", None)
#         return
#
#     now = utc_now_iso()
#     try:
#         with open(path, "r", newline="", encoding="utf-8") as f:
#             reader = csv.reader(f)
#             for row in reader:
#                 if not row or len(row) < 4:
#                     continue
#                 date_str, time_str, promise_id, time_spent = row[0], row[1], row[2], row[3]
#                 pid = (promise_id or "").strip().upper()
#                 if not pid:
#                     continue
#                 try:
#                     naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
#                 except Exception:
#                     continue
#
#                 at_utc = dt_to_utc_iso(naive, assume_local_tz=True)
#                 if not at_utc:
#                     continue
#
#                 p_uuid = resolve_promise_uuid(conn, user_id, pid)
#
#                 conn.execute(
#                     """
#                     INSERT INTO actions(
#                         action_uuid, user_id, promise_uuid, promise_id_text,
#                         action_type, time_spent_hours, at_utc
#                     ) VALUES (?, ?, ?, ?, ?, ?, ?);
#                     """,
#                     (
#                         str(uuid.uuid4()),
#                         user_id,
#                         p_uuid,
#                         pid,
#                         "log_time",
#                         _to_float(time_spent, 0.0),
#                         at_utc,
#                     ),
#                 )
#     except Exception:
#         pass
#
#     _mark_imported(conn, user_id, "actions", _file_mtime_utc_iso(path))


# def _import_sessions(conn, root_dir: str, user_id: str) -> None:
#     udir = _user_dir(root_dir, user_id)
#     path = os.path.join(udir, "sessions.csv")
#     if not os.path.exists(path):
#         _mark_imported(conn, user_id, "sessions", None)
#         return
#
#     try:
#         with open(path, "r", newline="", encoding="utf-8") as f:
#             reader = csv.DictReader(f)
#             for row in reader:
#                 sid = str(row.get("session_id", "") or "").strip()
#                 pid = str(row.get("promise_id", "") or "").strip().upper()
#                 if not sid or not pid:
#                     continue
#
#                 p_uuid = resolve_promise_uuid(conn, user_id, pid)
#                 if not p_uuid:
#                     # Skip sessions we cannot associate (should be rare)
#                     continue
#
#                 started_at_utc = dt_to_utc_iso(_safe_fromiso(row.get("started_at")), assume_local_tz=True) or utc_now_iso()
#                 ended_at_utc = dt_to_utc_iso(_safe_fromiso(row.get("ended_at")), assume_local_tz=True)
#                 last_change_utc = dt_to_utc_iso(_safe_fromiso(row.get("last_state_change_at")), assume_local_tz=True)
#
#                 conn.execute(
#                     """
#                     INSERT OR REPLACE INTO sessions(
#                         session_id, user_id, promise_uuid, status,
#                         started_at_utc, ended_at_utc, paused_seconds_total,
#                         last_state_change_at_utc, message_id, chat_id
#                     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
#                     """,
#                     (
#                         sid,
#                         user_id,
#                         p_uuid,
#                         str(row.get("status", "") or "").strip() or "finished",
#                         started_at_utc,
#                         ended_at_utc,
#                         _to_int(row.get("paused_seconds_total", 0), 0),
#                         last_change_utc,
#                         _to_int(row.get("message_id", "") or 0, 0) or None,
#                         _to_int(row.get("chat_id", "") or 0, 0) or None,
#                     ),
#                 )
#     except Exception:
#         pass
#
#     _mark_imported(conn, user_id, "sessions", _file_mtime_utc_iso(path))


# def _safe_fromiso(s: Any) -> Optional[datetime]:
#     t = str(s or "").strip()
#     if not t:
#         return None
#     try:
#         return datetime.fromisoformat(t)
#     except Exception:
#         return None


# def _import_settings(conn, root_dir: str, user_id: str) -> None:
#     udir = _user_dir(root_dir, user_id)
#     path = os.path.join(udir, "settings.yaml")
#     if not os.path.exists(path):
#         _mark_imported(conn, user_id, "settings", None)
#         return
#
#     data: Dict[str, Any] = {}
#     try:
#         with open(path, "r", encoding="utf-8") as f:
#             if YAML_AVAILABLE:
#                 data = yaml.safe_load(f) or {}
#             else:
#                 data = json.load(f) or {}
#     except Exception:
#         data = {}
#
#     now = utc_now_iso()
#     timezone_name = str(data.get("timezone", "Europe/Paris") or "Europe/Paris")
#     nightly_hh = _to_int(data.get("nightly_hh", 22), 22)
#     nightly_mm = _to_int(data.get("nightly_mm", 0), 0)
#     language = str(data.get("language", "en") or "en")
#     voice_mode = data.get("voice_mode", None)
#     voice_mode = None if voice_mode in (None, "", "none", "null") else str(voice_mode)
#
#     conn.execute(
#         """
#         INSERT OR REPLACE INTO user_settings(
#             user_id, timezone, nightly_hh, nightly_mm, language, voice_mode,
#             created_at_utc, updated_at_utc
#         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
#         """,
#         (user_id, timezone_name, nightly_hh, nightly_mm, language, voice_mode, now, now),
#     )
#
#     _mark_imported(conn, user_id, "settings", _file_mtime_utc_iso(path))

