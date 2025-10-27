# python
"""
Unified MongoDB persistence for tm_bot using Motor (async MongoDB driver).

- Connects to MongoDB using env var `MONGO_URI` or `MONGODB_URI` (fallback: mongodb://localhost:27017).
- Database: `zana_planner`
- Collections: promises, actions, sessions, settings
- Adds `created_at` and `updated_at` on writes, indexes `user_id` and timestamps.
- Async CRUD for Promise, Action, Session, UserSettings dataclasses.
- Auto serialization/deserialization for dataclasses, enums, date/datetime.
- Placeholders for Argon2 hashing (PII) and Fernet encryption (env `DATA_ENC_KEY`).
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Type, TypeVar
from pymongo import IndexModel, ASCENDING
from pymongo.errors import OperationFailure

from dataclasses import is_dataclass, fields as dc_fields

try:
    # Load .env from current or parent dirs
    from dotenv import load_dotenv, find_dotenv  # type: ignore
    load_dotenv(find_dotenv())
except Exception:  # pragma: no cover
    pass

from motor.motor_asyncio import AsyncIOMotorClient  # Motor async driver

# Optional crypto dependencies
try:
    from cryptography.fernet import Fernet  # type: ignore
except Exception:  # pragma: no cover
    Fernet = None  # type: ignore

try:
    from argon2 import PasswordHasher  # type: ignore
except Exception:  # pragma: no cover
    PasswordHasher = None  # type: ignore

# Domain models
from models.models import Promise, Action, Session, UserSettings
from models.enums import ActionType, SessionStatus


T = TypeVar("T")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class DataManager:
    """
    Async MongoDB data manager using Motor.
    Encapsulates all persistence for Promise, Action, Session, UserSettings.

    Usage:
        dm = DataManager()
        await dm.save_promise(p)
        promises = await dm.list_promises(user_id)
        await dm.save_action(a)
        sessions = await dm.get_active_sessions(user_id)
    """

    def __init__(self, mongo_uri: Optional[str] = None, db_name: str = "zana_planner") -> None:
        # Connection
        env_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
        self._mongo_uri = mongo_uri or env_uri or "mongodb://localhost:27017"
        # Tighter timeouts for faster feedback during dev
        self._client = AsyncIOMotorClient(
            self._mongo_uri,
            serverSelectionTimeoutMS=7000,
            connectTimeoutMS=7000,
            socketTimeoutMS=7000,
        )
        self._db = self._client[db_name]

        # Collections
        self._collections: Dict[str, Any] = {
            "promises": self._db["promises"],
            "actions": self._db["actions"],
            "sessions": self._db["sessions"],
            "settings": self._db["settings"],
        }

        # Model -> collection name
        self._model_to_collection: Dict[Type[Any], str] = {
            Promise: "promises",
            Action: "actions",
            Session: "sessions",
            UserSettings: "settings",
        }

        # One-time index setup
        self._initialized: bool = False

        # Security helpers (placeholders)
        self._fernet = self._init_fernet()
        self._hasher = PasswordHasher() if PasswordHasher else None

        logger.info("DataManager initialized for MongoDB at %s, DB=%s", self._mongo_uri, db_name)

    async def ping(self) -> bool:
        """Check connectivity to MongoDB."""
        try:
            await self._db.command({"ping": 1})
            return True
        except Exception as exc:
            logger.error("MongoDB ping failed: %s", exc)
            return False

    # ---------- Public API ----------

    async def save_promise(self, p: Promise) -> None:
        """Insert or update a Promise by (user_id, id)."""
        await self._ensure_indexes()
        doc = self._serialize_dataclass(p)
        now = self._now_utc()

        filt = {"user_id": doc.get("user_id"), "id": doc.get("id")}
        if filt["user_id"] is None or filt["id"] is None:
            raise ValueError("Promise must include 'user_id' and 'id'")

        update = {"$set": {**doc, "updated_at": now}, "$setOnInsert": {"created_at": now}}
        await self._collections["promises"].update_one(filt, update, upsert=True)

    async def list_promises(self, user_id: str) -> List[Promise]:
        """List all promises for a user."""
        await self._ensure_indexes()
        cursor = self._collections["promises"].find({"user_id": user_id})
        docs = await cursor.to_list(length=None)
        return [self._deserialize_dataclass(d, Promise) for d in docs]

    async def save_action(self, a: Action) -> None:
        """Append an Action document."""
        await self._ensure_indexes()
        doc = self._serialize_dataclass(a)
        now = self._now_utc()
        doc["created_at"] = now
        doc["updated_at"] = now
        await self._collections["actions"].insert_one(doc)

    async def list_actions(self, user_id: str, since: Optional[datetime] = None) -> List[Action]:
        """List actions for a user, optionally since a datetime."""
        await self._ensure_indexes()
        filt: Dict[str, Any] = {"user_id": user_id}
        if since:
            filt["at"] = {"$gte": since}
        cursor = self._collections["actions"].find(filt).sort("at", 1)
        docs = await cursor.to_list(length=None)
        return [self._deserialize_dataclass(d, Action) for d in docs]

    async def save_session(self, s: Session) -> None:
        """Insert or update a Session by (user_id, id|session_id)."""
        await self._ensure_indexes()
        doc = self._serialize_dataclass(s)
        now = self._now_utc()

        session_id = doc.get("id") or doc.get("session_id")
        if doc.get("user_id") is None or session_id is None:
            raise ValueError("Session must include 'user_id' and 'id' (or 'session_id')")

        filt = {"user_id": doc.get("user_id"), "id": session_id}
        doc["id"] = session_id  # normalize to 'id' in storage
        update = {"$set": {**doc, "updated_at": now}, "$setOnInsert": {"created_at": now}}
        await self._collections["sessions"].update_one(filt, update, upsert=True)

    async def get_active_sessions(self, user_id: str) -> List[Session]:
        """Return sessions with status in [running, paused] for a user."""
        await self._ensure_indexes()
        active_values = {
            SessionStatus.RUNNING.value if hasattr(SessionStatus.RUNNING, "value") else SessionStatus.RUNNING,
            SessionStatus.PAUSED.value if hasattr(SessionStatus.PAUSED, "value") else SessionStatus.PAUSED,
        }
        filt = {"user_id": user_id, "status": {"$in": list(active_values)}}
        cursor = self._collections["sessions"].find(filt)
        docs = await cursor.to_list(length=None)
        return [self._deserialize_dataclass(d, Session) for d in docs]

    async def save_settings(self, st: UserSettings) -> None:
        """Upsert settings by user_id."""
        await self._ensure_indexes()
        doc = self._serialize_dataclass(st)
        now = self._now_utc()
        user_id = doc.get("user_id")
        if user_id is None:
            raise ValueError("UserSettings must include 'user_id'")

        update = {"$set": {**doc, "updated_at": now}, "$setOnInsert": {"created_at": now}}
        await self._collections["settings"].update_one({"user_id": user_id}, update, upsert=True)

    async def get_settings(self, user_id: str) -> Optional[UserSettings]:
        """Get settings for a user or None if not found."""
        await self._ensure_indexes()
        doc = await self._collections["settings"].find_one({"user_id": user_id})
        if not doc:
            return None
        return self._deserialize_dataclass(doc, UserSettings)

    # ---------- Optional bonus ----------

    async def export_user_data(self, user_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """Export all user-related documents for backup."""
        await self._ensure_indexes()
        result: Dict[str, List[Dict[str, Any]]] = {}
        for name, coll in self._collections.items():
            cursor = coll.find({"user_id": user_id})
            docs = await cursor.to_list(length=None)
            result[name] = [{k: v for k, v in d.items() if k != "_id"} for d in docs]
        return result

    async def purge_user(self, user_id: str) -> None:
        """Delete all data for a user. Irreversible."""
        await self._ensure_indexes()
        for coll in self._collections.values():
            await coll.delete_many({"user_id": user_id})

    async def _ensure_indexes(self) -> None:
        if self._initialized:
            return
        defs = {
            "promises": [
                IndexModel([("user_id", ASCENDING)], name="ix_promises_user"),
                IndexModel([("user_id", ASCENDING), ("id", ASCENDING)], name="ux_promises_user_id", unique=True),
            ],
            "actions": [
                IndexModel([("user_id", ASCENDING)], name="ix_actions_user"),
                IndexModel([("user_id", ASCENDING), ("at", ASCENDING)], name="ix_actions_user_at"),
                IndexModel([("user_id", ASCENDING), ("promise_id", ASCENDING)], name="ix_actions_user_promise"),
            ],
            "sessions": [
                IndexModel([("user_id", ASCENDING)], name="ix_sessions_user"),
                IndexModel([("user_id", ASCENDING), ("id", ASCENDING)], name="ux_sessions_user_id"),
            ],
            "settings": [
                IndexModel([("user_id", ASCENDING)], name="ux_settings_user", unique=True),
            ],
        }
        for coll_name, models in defs.items():
            coll = self._collections[coll_name]
            existing = await coll.list_indexes().to_list(length=None)

            def eq(existing_ix, m: IndexModel):
                # compare keys and uniqueness only
                ex_keys = list(existing_ix["key"].items())  # [('user_id', 1), ...]
                m_keys = list(m.document["key"].items())
                ex_unique = existing_ix.get("unique", False)
                m_unique = m.document.get("unique", False)
                return ex_keys == m_keys and ex_unique == m_unique

            for m in models:
                # skip if an equivalent index already exists (regardless of name)
                if any(eq(ix, m) for ix in existing):
                    continue
                await coll.create_indexes([m])

        self._initialized = True
        logger.info("MongoDB indexes ensured (quiet).")

    def _now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    # ----- Serialization helpers -----

    def _serialize_dataclass(self, obj: Any) -> Dict[str, Any]:
        """Dataclass -> Mongo-friendly dict with enum/date handling."""
        if not is_dataclass(obj):
            raise TypeError("Expected a dataclass instance")

        result: Dict[str, Any] = {}
        for f in dc_fields(obj):
            key = f.name
            val = getattr(obj, key)
            result[key] = self._to_bson(val)

        # Placeholder: hashing/encryption for sensitive PII
        # if "email" in result and result["email"] is not None:
        #     result["email_hash"] = self._argon2_hash(str(result["email"]))
        # if "telegram_id" in result and result["telegram_id"] is not None:
        #     result["telegram_id_enc"] = self._encrypt_str(str(result["telegram_id"]))

        return result

    def _deserialize_dataclass(self, data: Dict[str, Any], model: Type[T]) -> T:
        """Mongo dict -> dataclass instance with enum/date parsing."""
        clean = {k: v for k, v in data.items() if k != "_id"}

        def to_py(key: str, v: Any) -> Any:
            if key in {"start_date", "end_date"} and isinstance(v, str):
                try:
                    return date.fromisoformat(v)
                except Exception:
                    return v
            if key in {"at", "created_at", "updated_at", "start_time", "end_time", "completed_at", "last_activity_at"}:
                if isinstance(v, str):
                    try:
                        return datetime.fromisoformat(v)
                    except Exception:
                        return v
                return v
            if key == "action" and v is not None:
                try:
                    return v if isinstance(v, ActionType) else ActionType(v)
                except Exception:
                    return v
            if key == "status" and v is not None:
                try:
                    return v if isinstance(v, SessionStatus) else SessionStatus(v)
                except Exception:
                    return v
            return v

        parsed = {k: to_py(k, v) for k, v in clean.items()}
        try:
            return model(**parsed)  # type: ignore[arg-type]
        except TypeError:
            names = {f.name for f in dc_fields(model)}
            filtered = {k: v for k, v in parsed.items() if k in names}
            return model(**filtered)  # type: ignore[arg-type]

    def _to_bson(self, v: Any) -> Any:
        """Convert Python value to something MongoDB can store."""
        if hasattr(v, "value") and type(getattr(v, "value", None)) in (str, int):
            return v.value  # Enum
        if isinstance(v, datetime):
            return v  # native datetime in BSON
        if isinstance(v, date):
            return v.isoformat()  # store date as ISO string
        if is_dataclass(v):
            return self._serialize_dataclass(v)
        if isinstance(v, (list, tuple)):
            return [self._to_bson(i) for i in v]
        if isinstance(v, dict):
            return {k: self._to_bson(val) for k, val in v.items()}
        return v

    # ----- Security helpers (placeholders) -----

    def _init_fernet(self):
        key = os.getenv("DATA_ENC_KEY")
        if Fernet and key:
            try:
                return Fernet(key.encode("utf-8"))
            except Exception as exc:
                logger.warning("Invalid DATA_ENC_KEY; encryption disabled: %s", exc)
        else:
            if not key:
                logger.debug("DATA_ENC_KEY not set; encryption disabled.")
        return None

    def _encrypt_str(self, s: str) -> Optional[str]:
        """Encrypt a string using Fernet if configured."""
        if not self._fernet:
            return None
        try:
            token = self._fernet.encrypt(s.encode("utf-8"))
            return token.decode("utf-8")
        except Exception as exc:
            logger.error("Encryption failed: %s", exc)
            return None

    def _decrypt_str(self, token: str) -> Optional[str]:
        """Decrypt a string using Fernet if configured."""
        if not self._fernet:
            return None
        try:
            data = self._fernet.decrypt(token.encode("utf-8"))
            return data.decode("utf-8")
        except Exception as exc:
            logger.error("Decryption failed: %s", exc)
            return None

    def _argon2_hash(self, s: str) -> Optional[str]:
        """Hash a string using Argon2 (not reversible, for PII)."""
        if not self._hasher:
            return None
        try:
            return self._hasher.hash(s)
        except Exception as exc:
            logger.error("Argon2 hashing failed: %s", exc)
            return None


# Example usage
if __name__ == "__main__":
    async def _demo() -> None:
        dm = DataManager()

        # Fail fast if MongoDB is not reachable
        if not await dm.ping():
            print("MongoDB is not reachable. Check `MONGO_URI`/`MONGODB_URI` and that the server is running.")
            return

        # Replace with real dataclass instances as needed.
        p = Promise(user_id=1, id="P01", text="Deep_Work", hours_per_week=5.0, recurring=True,
                    start_date=date.today(), end_date=date(2099, 12, 31), angle_deg=0, radius=0)
        await dm.save_promise(p)
        print(await dm.list_promises(1))

        a = Action(user_id=1, promise_id="P01", action=ActionType.LOG_TIME, time_spent=1.5, at=datetime.now(timezone.utc))
        await dm.save_action(a)
        print(await dm.list_actions(1))

        s = Session(user_id=1, id=1, promise_id="S01", status=SessionStatus.RUNNING, started_at=datetime.now(timezone.utc))
        await dm.save_session(s)
        print(await dm.get_active_sessions(1))

        st = UserSettings(user_id=1, timezone="UTC", nightly_hh=23, nightly_mm=30)
        await dm.save_settings(st)
        print(await dm.get_settings(1))

    asyncio.run(_demo())
