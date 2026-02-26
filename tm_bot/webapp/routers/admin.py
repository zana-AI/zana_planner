"""
Admin-related endpoints.
"""

import os
import json
import subprocess
import re
import uuid
import tempfile
import threading
import asyncio
import html
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Literal
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import StreamingResponse, Response
from ..dependencies import get_current_user, get_admin_user
from ..schemas import (
    AdminUsersResponse, CreateBroadcastRequest, UpdateBroadcastRequest,
    BroadcastResponse, BotTokenResponse, ConversationResponse, ConversationMessage,
    GenerateTemplateRequest, CreatePromiseForUserRequest, DayReminder,
    RunTestsRequest, TestRunResponse, TestReportResponse
)
from repositories.templates_repo import TemplatesRepository
from repositories.promises_repo import PromisesRepository
from repositories.settings_repo import SettingsRepository
from repositories.broadcasts_repo import BroadcastsRepository
from repositories.bot_tokens_repo import BotTokensRepository
from repositories.reminders_repo import RemindersRepository
from services.reminder_dispatch import ReminderDispatchService
from db.postgres_db import get_db_session, dt_to_utc_iso, utc_now_iso, resolve_promise_uuid
from sqlalchemy import text
from utils.admin_utils import is_admin
from utils.logger import get_logger
from llms.llm_env_utils import load_llm_env
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = get_logger(__name__)

# Admin stats cache (module-level)
_admin_stats_cache: Optional[Dict[str, Any]] = None
_admin_stats_cache_timestamp: Optional[datetime] = None
ADMIN_STATS_CACHE_TTL = timedelta(minutes=5)

# Test run storage (in-memory, cleared on restart)
_test_runs: Dict[str, Dict[str, Any]] = {}
_test_run_lock = threading.Lock()
_test_run_active = False  # Guard to prevent concurrent runs


_ALLOWED_EXPORT_HTML_TAGS = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "code", "pre", "blockquote", "a", "br"
}
_VOID_EXPORT_HTML_TAGS = {"br"}
_ALLOWED_EXPORT_HTML_ATTRS = {
    "a": {"href"},
    "blockquote": {"expandable"},
}
_SAFE_EXPORT_LINK_RE = re.compile(r"^(https?://|mailto:|tg://|tg:)", re.IGNORECASE)
_UNSAFE_EXPORT_TAG_RE = re.compile(r"<\s*/?\s*(script|style)[^>]*>", re.IGNORECASE)
_UNSAFE_EXPORT_HANDLER_RE = re.compile(r"\son[a-z]+\s*=\s*(['\"]).*?\1", re.IGNORECASE | re.DOTALL)
_UNSAFE_EXPORT_JS_URL_RE = re.compile(r"javascript\s*:", re.IGNORECASE)


class _ConversationExportSanitizer:
    """Conservative sanitizer for bot HTML content in conversation exports."""

    @staticmethod
    def _sanitize_attr_value(attr_name: str, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = str(value).strip()
        if not value:
            return None
        if attr_name == "href":
            if not _SAFE_EXPORT_LINK_RE.match(value):
                return None
            if _UNSAFE_EXPORT_JS_URL_RE.search(value):
                return None
        return value

    @classmethod
    def sanitize(cls, raw_html: str) -> str:
        source = "" if raw_html is None else str(raw_html)
        source = _UNSAFE_EXPORT_TAG_RE.sub("", source)
        source = _UNSAFE_EXPORT_HANDLER_RE.sub("", source)

        parts: List[str] = []
        tag_stack: List[str] = []
        token_re = re.compile(r"(<[^>]+>)")
        for token in token_re.split(source):
            if not token:
                continue
            if not token.startswith("<"):
                parts.append(html.escape(html.unescape(token)))
                continue

            is_end_tag = token.startswith("</")
            tag_match = re.match(r"<\s*/?\s*([a-zA-Z0-9]+)", token)
            if not tag_match:
                continue
            tag = tag_match.group(1).lower()
            if tag not in _ALLOWED_EXPORT_HTML_TAGS:
                continue

            if is_end_tag:
                if tag in _VOID_EXPORT_HTML_TAGS:
                    continue
                if tag in tag_stack:
                    while tag_stack:
                        open_tag = tag_stack.pop()
                        parts.append(f"</{open_tag}>")
                        if open_tag == tag:
                            break
                continue

            attrs = ""
            allowed_attrs = _ALLOWED_EXPORT_HTML_ATTRS.get(tag, set())
            for attr_name, attr_value in re.findall(
                r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(".*?"|\'.*?\'|[^\s>]+)',
                token
            ):
                attr_name = attr_name.lower()
                if attr_name not in allowed_attrs:
                    continue
                raw_value = attr_value.strip().strip('"').strip("'")
                safe_value = cls._sanitize_attr_value(attr_name, raw_value)
                if safe_value is None:
                    continue
                attrs += f' {attr_name}="{html.escape(safe_value, quote=True)}"'

            if tag == "a":
                attrs += ' rel="noopener noreferrer" target="_blank"'

            if tag in _VOID_EXPORT_HTML_TAGS:
                parts.append(f"<{tag}{attrs}>")
            else:
                parts.append(f"<{tag}{attrs}>")
                tag_stack.append(tag)

        while tag_stack:
            parts.append(f"</{tag_stack.pop()}>")
        return "".join(parts)


def _build_conversation_export_html(
    user_id: int,
    messages: List[Dict[str, Any]],
    generated_at_utc: str,
) -> str:
    rows: List[str] = []
    for msg in messages:
        is_user = msg.get("message_type") == "user"
        message_type = "User" if is_user else "Bot"
        created_at = html.escape(str(msg.get("created_at_utc") or ""))
        if is_user:
            plain_text = html.escape(html.unescape(str(msg.get("content") or "")))
            body = f"<div class=\"message-text plain\">{plain_text}</div>"
        else:
            body = (
                "<div class=\"message-text rich\">"
                f"{_ConversationExportSanitizer.sanitize(str(msg.get('content') or ''))}"
                "</div>"
            )
        bubble_class = "message-user" if is_user else "message-bot"
        rows.append(
            "<article class=\"message-row\">"
            f"<header class=\"message-meta\">{message_type} | {created_at}</header>"
            f"<section class=\"message-bubble {bubble_class}\">{body}</section>"
            "</article>"
        )

    rendered_rows = "\n".join(rows) if rows else "<p class=\"empty\">No messages found.</p>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Conversation Export - User {user_id}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0b1020;
      --panel: rgba(15, 23, 48, 0.65);
      --text: #e8eefc;
      --muted: rgba(232, 238, 252, 0.6);
      --border: rgba(232, 238, 252, 0.15);
      --user-bg: rgba(91, 163, 245, 0.2);
      --bot-bg: rgba(232, 238, 252, 0.1);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      background: radial-gradient(circle at 20% 10%, #17264f, var(--bg));
      color: var(--text);
      padding: 24px;
      line-height: 1.5;
    }}
    .container {{ max-width: 920px; margin: 0 auto; }}
    .title {{ margin: 0 0 6px; font-size: 1.4rem; }}
    .subtitle {{ margin: 0 0 20px; color: var(--muted); font-size: 0.95rem; }}
    .message-row {{ margin-bottom: 14px; }}
    .message-meta {{ font-size: 0.78rem; color: var(--muted); margin-bottom: 6px; }}
    .message-bubble {{
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px 14px;
      background: var(--panel);
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .message-user {{ background: var(--user-bg); }}
    .message-bot {{ background: var(--bot-bg); }}
    .message-text blockquote {{
      border-left: 3px solid rgba(91, 163, 245, 0.7);
      margin: 10px 0 0;
      padding: 8px 12px;
      background: rgba(91, 163, 245, 0.12);
      border-radius: 6px;
    }}
    .message-text pre {{
      background: rgba(11, 16, 32, 0.8);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px;
      overflow-x: auto;
    }}
    .message-text a {{ color: #7dc6ff; }}
    .empty {{ color: var(--muted); }}
  </style>
</head>
<body>
  <main class="container">
    <h1 class="title">Conversation Export</h1>
    <p class="subtitle">User ID: {user_id} | Generated at UTC: {html.escape(generated_at_utc)}</p>
    {rendered_rows}
  </main>
</body>
</html>
"""


def _normalize_export_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for msg in messages:
        normalized.append(
            {
                "id": msg.get("id"),
                "user_id": msg.get("user_id"),
                "chat_id": msg.get("chat_id"),
                "message_id": msg.get("message_id"),
                "message_type": msg.get("message_type"),
                "content": msg.get("content") or "",
                "created_at_utc": msg.get("created_at_utc"),
                "conversation_session_id": msg.get("conversation_session_id"),
                "conversation_session_time_tag_utc": msg.get("conversation_session_time_tag_utc"),
            }
        )
    return normalized


@router.get("/check")
async def check_admin_status(
    request: Request,
    user_id: int = Depends(get_current_user)
):
    """Check if the current user is an admin."""
    return {"is_admin": is_admin(user_id)}


@router.get("/stats")
async def get_admin_stats(
    request: Request,
    admin_id: int = Depends(get_admin_user)
):
    """
    Get app statistics (admin only).
    Returns cached results for 5 minutes to reduce database load.
    """
    global _admin_stats_cache, _admin_stats_cache_timestamp
    
    now = datetime.now()
    
    # Return cached stats if still valid
    if _admin_stats_cache and _admin_stats_cache_timestamp and (now - _admin_stats_cache_timestamp) < ADMIN_STATS_CACHE_TTL:
        logger.debug("Returning cached admin stats")
        return _admin_stats_cache
    
    try:
        # Compute stats directly from PostgreSQL
        with get_db_session() as session:
            # Total users (distinct user_ids from any table)
            total_users = session.execute(
                text("""
                    SELECT COUNT(DISTINCT user_id) 
                    FROM (
                        SELECT user_id FROM users
                        UNION
                        SELECT user_id FROM promises
                        UNION
                        SELECT user_id FROM actions
                    ) AS all_users;
                """)
            ).scalar() or 0
            
            # Active users in last 7 days (users with actions in last 7 days)
            seven_days_ago_dt = datetime.now(timezone.utc) - timedelta(days=7)
            seven_days_ago = dt_to_utc_iso(seven_days_ago_dt) or utc_now_iso()
            active_users = session.execute(
                text("""
                    SELECT COUNT(DISTINCT user_id)
                    FROM actions
                    WHERE at_utc >= :seven_days_ago;
                """),
                {"seven_days_ago": seven_days_ago}
            ).scalar() or 0
            
            # Users with promises (non-deleted)
            users_with_promises = session.execute(
                text("""
                    SELECT COUNT(DISTINCT user_id)
                    FROM promises
                    WHERE is_deleted = 0;
                """)
            ).scalar() or 0
        
        # Return simplified stats for admin panel
        result = {
            "total_users": int(total_users),
            "active_users": int(active_users),
            "total_promises": int(users_with_promises),  # Users with promises, not total promise count
        }
        
        # Cache the result
        _admin_stats_cache = result
        _admin_stats_cache_timestamp = now
        
        logger.info(f"Admin stats computed: {result}")
        return result
        
    except Exception as e:
        logger.exception(f"Error computing admin stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to compute stats: {str(e)}")


@router.get("/users", response_model=AdminUsersResponse)
async def get_admin_users(
    request: Request,
    limit: int = Query(default=1000, ge=1, le=10000),
    admin_id: int = Depends(get_admin_user)
):
    """
    Get all users (admin only).
    
    Args:
        limit: Maximum number of users to return
        admin_id: Admin user ID (from dependency)
    
    Returns:
        List of all users
    """
    try:
        # Calculate 30 days ago for activity count
        since_utc = (
            datetime.now(timezone.utc) - timedelta(days=30)
        ).isoformat().replace("+00:00", "Z")

        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT 
                        u.user_id,
                        u.first_name,
                        u.last_name,
                        u.username,
                        u.last_seen_utc,
                        u.timezone,
                        u.language,
                        COALESCE(promise_counts.promise_count, 0) as promise_count,
                        COALESCE(activity.activity_count, 0) as activity_count
                    FROM users u
                    LEFT JOIN (
                        SELECT user_id, COUNT(*) as promise_count
                        FROM promises
                        WHERE is_deleted = 0
                        GROUP BY user_id
                    ) promise_counts ON u.user_id = promise_counts.user_id
                    LEFT JOIN (
                        SELECT user_id, COUNT(*) as activity_count
                        FROM actions 
                        WHERE at_utc >= :since_utc
                        GROUP BY user_id
                    ) activity ON u.user_id = activity.user_id
                    ORDER BY u.last_seen_utc DESC NULLS LAST
                    LIMIT :limit;
                """),
                {"since_utc": since_utc, "limit": int(limit)},
            ).mappings().fetchall()

        from ..schemas import AdminUser
        users = []
        for row in rows:
            users.append(
                AdminUser(
                    user_id=str(row.get("user_id")),
                    first_name=row.get("first_name"),
                    last_name=row.get("last_name"),
                    username=row.get("username"),
                    last_seen_utc=row.get("last_seen_utc"),
                    timezone=row.get("timezone"),
                    language=row.get("language"),
                    promise_count=row.get("promise_count"),
                    activity_count=row.get("activity_count"),
                )
            )

        return AdminUsersResponse(users=users, total=len(users))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting admin users: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch users: {str(e)}")


@router.get("/bot-tokens", response_model=List[BotTokenResponse])
async def get_bot_tokens(
    request: Request,
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    admin_id: int = Depends(get_admin_user)
):
    """
    List available bot tokens (admin only).
    
    Args:
        is_active: Filter by active status (optional)
        admin_id: Admin user ID (from dependency)
    
    Returns:
        List of bot tokens
    """
    try:
        bot_tokens_repo = BotTokensRepository()
        tokens = bot_tokens_repo.list_bot_tokens(is_active=is_active)
        
        return [
            BotTokenResponse(
                bot_token_id=token["bot_token_id"],
                bot_username=token["bot_username"],
                is_active=token["is_active"],
                description=token["description"],
                created_at_utc=token["created_at_utc"],
                updated_at_utc=token["updated_at_utc"],
            )
            for token in tokens
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error listing bot tokens: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list bot tokens: {str(e)}")


@router.get("/users/{user_id}/conversations", response_model=ConversationResponse)
async def get_user_conversations(
    request: Request,
    user_id: int,
    limit: int = Query(default=100, ge=1, le=1000),
    message_type: Optional[str] = Query(None, description="Filter by 'user' or 'bot'"),
    admin_id: int = Depends(get_admin_user)
):
    """
    Get conversation history for a user (admin only).
    
    Args:
        user_id: Target user ID
        limit: Maximum number of messages to return
        message_type: Filter by message type ('user' or 'bot'), or None for all
        admin_id: Admin user ID (from dependency)
    
    Returns:
        List of conversation messages
    """
    try:
        from repositories.conversation_repo import ConversationRepository
        
        # Validate message_type if provided
        if message_type and message_type not in ['user', 'bot']:
            raise HTTPException(status_code=400, detail="message_type must be 'user' or 'bot'")
        
        conversation_repo = ConversationRepository()
        messages = conversation_repo.get_recent_history(
            user_id=user_id,
            limit=limit,
            message_type=message_type
        )
        
        # Convert to response models
        conversation_messages = [
            ConversationMessage(
                id=msg["id"],
                user_id=msg["user_id"],
                chat_id=msg.get("chat_id"),
                message_id=msg.get("message_id"),
                message_type=msg["message_type"],
                content=msg["content"],
                created_at_utc=msg["created_at_utc"],
                conversation_session_id=msg.get("conversation_session_id"),
                conversation_session_time_tag_utc=msg.get("conversation_session_time_tag_utc"),
            )
            for msg in messages
        ]
        
        return ConversationResponse(messages=conversation_messages)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting conversations for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch conversations: {str(e)}")


@router.get("/users/{user_id}/conversations/export")
async def export_user_conversations(
    request: Request,
    user_id: int,
    limit: int = Query(default=1000, ge=1, le=10000),
    message_type: Optional[str] = Query(None, description="Filter by 'user' or 'bot'"),
    export_format: Literal["html", "json"] = Query(default="html", alias="format"),
    admin_id: int = Depends(get_admin_user),
):
    """
    Export conversation history for a user (admin only).

    Supports HTML (human-readable rich document) and JSON (raw data for analysis).
    """
    try:
        from repositories.conversation_repo import ConversationRepository

        if message_type and message_type not in ["user", "bot"]:
            raise HTTPException(status_code=400, detail="message_type must be 'user' or 'bot'")

        conversation_repo = ConversationRepository()
        messages_desc = conversation_repo.get_recent_history(
            user_id=user_id,
            limit=limit,
            message_type=message_type,
        )
        messages = list(reversed(messages_desc))
        normalized_messages = _normalize_export_messages(messages)

        generated_at_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"conversation_user_{user_id}_{timestamp}.{export_format}"

        if export_format == "json":
            payload = {
                "generated_at_utc": generated_at_utc,
                "user_id": str(user_id),
                "limit": limit,
                "message_type_filter": message_type,
                "messages": normalized_messages,
            }
            content = json.dumps(payload, ensure_ascii=False, indent=2)
            return Response(
                content=content.encode("utf-8"),
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        html_content = _build_conversation_export_html(
            user_id=user_id,
            messages=normalized_messages,
            generated_at_utc=generated_at_utc,
        )
        return Response(
            content=html_content.encode("utf-8"),
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error exporting conversations for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export conversations: {str(e)}")


@router.post("/broadcast", response_model=BroadcastResponse)
async def create_broadcast(
    request: Request,
    broadcast_request: CreateBroadcastRequest,
    admin_id: int = Depends(get_admin_user)
):
    """
    Create or schedule a broadcast (admin only).
    
    Args:
        broadcast_request: Broadcast creation request
        admin_id: Admin user ID (from dependency)
    
    Returns:
        Created broadcast
    """
    try:
        from zoneinfo import ZoneInfo
        from services.broadcast_service import get_all_users_from_db, execute_broadcast_from_db

        # Validate message
        if not broadcast_request.message or not broadcast_request.message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        # Validate target users
        if not broadcast_request.target_user_ids:
            raise HTTPException(status_code=400, detail="At least one target user must be selected")

        # Get all valid users
        all_users = get_all_users_from_db()
        valid_user_ids = [uid for uid in broadcast_request.target_user_ids if uid in all_users]
        
        if not valid_user_ids:
            raise HTTPException(status_code=400, detail="No valid target users found")
        
        # Determine scheduled time
        is_immediate = not bool(broadcast_request.scheduled_time_utc)
        if broadcast_request.scheduled_time_utc:
            # Parse scheduled time
            try:
                scheduled_dt = datetime.fromisoformat(broadcast_request.scheduled_time_utc.replace('Z', '+00:00'))
                if scheduled_dt.tzinfo is None:
                    scheduled_dt = scheduled_dt.replace(tzinfo=ZoneInfo("UTC"))
                scheduled_dt = scheduled_dt.astimezone(ZoneInfo("UTC"))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid scheduled_time_utc format: {e}")
            
            # Check if time is in the past
            now_utc = datetime.now(ZoneInfo("UTC"))
            if scheduled_dt < now_utc:
                raise HTTPException(status_code=400, detail="Scheduled time cannot be in the past")
        else:
            # Immediate broadcast - schedule for now
            scheduled_dt = datetime.now(ZoneInfo("UTC"))
        
        # Create broadcast in database
        broadcasts_repo = BroadcastsRepository()
        broadcast_id = broadcasts_repo.create_broadcast(
            admin_id=admin_id,
            message=broadcast_request.message,
            target_user_ids=valid_user_ids,
            scheduled_time_utc=scheduled_dt,
            bot_token_id=broadcast_request.bot_token_id,
        )

        # Fire-and-forget immediate dispatch.
        # Scheduled broadcasts are handled by the background dispatcher.
        if is_immediate:
            default_bot_token = getattr(request.app.state, "bot_token", None)

            async def _dispatch_immediate() -> None:
                try:
                    await execute_broadcast_from_db(
                        response_service=None,
                        broadcast_id=broadcast_id,
                        default_bot_token=default_bot_token,
                    )
                except Exception as e:
                    logger.error(
                        "Immediate dispatch failed for broadcast %s: %s",
                        broadcast_id,
                        e,
                        exc_info=True,
                    )

            asyncio.create_task(_dispatch_immediate())
        
        # Get created broadcast
        broadcast = broadcasts_repo.get_broadcast(broadcast_id)
        if not broadcast:
            raise HTTPException(status_code=500, detail="Failed to retrieve created broadcast")
        
        return BroadcastResponse(
            broadcast_id=broadcast.broadcast_id,
            admin_id=broadcast.admin_id,
            message=broadcast.message,
            target_user_ids=broadcast.target_user_ids,
            scheduled_time_utc=broadcast.scheduled_time_utc.isoformat(),
            status=broadcast.status,
            bot_token_id=broadcast.bot_token_id,
            created_at=broadcast.created_at.isoformat() if broadcast.created_at else "",
            updated_at=broadcast.updated_at.isoformat() if broadcast.updated_at else "",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error creating broadcast: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create broadcast: {str(e)}")


@router.get("/broadcasts", response_model=List[BroadcastResponse])
async def list_broadcasts(
    request: Request,
    status: Optional[str] = Query(None),
    limit: int = Query(default=100, ge=1, le=1000),
    admin_id: int = Depends(get_admin_user)
):
    """
    List scheduled broadcasts (admin only).
    
    Args:
        status: Filter by status (pending, completed, cancelled)
        limit: Maximum number of broadcasts to return
        admin_id: Admin user ID (from dependency)
    
    Returns:
        List of broadcasts
    """
    try:
        broadcasts_repo = BroadcastsRepository()
        broadcasts = broadcasts_repo.list_broadcasts(
            admin_id=admin_id,
            status=status,
            limit=limit,
        )
        
        return [
            BroadcastResponse(
                broadcast_id=b.broadcast_id,
                admin_id=b.admin_id,
                message=b.message,
                target_user_ids=b.target_user_ids,
                scheduled_time_utc=b.scheduled_time_utc.isoformat(),
                status=b.status,
                bot_token_id=b.bot_token_id,
                created_at=b.created_at.isoformat() if b.created_at else "",
                updated_at=b.updated_at.isoformat() if b.updated_at else "",
            )
            for b in broadcasts
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error listing broadcasts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list broadcasts: {str(e)}")


@router.get("/broadcasts/{broadcast_id}", response_model=BroadcastResponse)
async def get_broadcast(
    request: Request,
    broadcast_id: str,
    admin_id: int = Depends(get_admin_user)
):
    """
    Get broadcast details (admin only).
    
    Args:
        broadcast_id: Broadcast ID
        admin_id: Admin user ID (from dependency)
    
    Returns:
        Broadcast details
    """
    try:
        broadcasts_repo = BroadcastsRepository()
        broadcast = broadcasts_repo.get_broadcast(broadcast_id)
        
        if not broadcast:
            raise HTTPException(status_code=404, detail="Broadcast not found")
        
        # Verify admin owns this broadcast
        if broadcast.admin_id != str(admin_id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        return BroadcastResponse(
            broadcast_id=broadcast.broadcast_id,
            admin_id=broadcast.admin_id,
            message=broadcast.message,
            target_user_ids=broadcast.target_user_ids,
            scheduled_time_utc=broadcast.scheduled_time_utc.isoformat(),
            status=broadcast.status,
            bot_token_id=broadcast.bot_token_id,
            created_at=broadcast.created_at.isoformat() if broadcast.created_at else "",
            updated_at=broadcast.updated_at.isoformat() if broadcast.updated_at else "",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting broadcast: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get broadcast: {str(e)}")


@router.patch("/broadcasts/{broadcast_id}", response_model=BroadcastResponse)
async def update_broadcast(
    request: Request,
    broadcast_id: str,
    update_request: UpdateBroadcastRequest,
    admin_id: int = Depends(get_admin_user)
):
    """
    Update a scheduled broadcast (admin only).
    
    Args:
        broadcast_id: Broadcast ID
        update_request: Update request
        admin_id: Admin user ID (from dependency)
    
    Returns:
        Updated broadcast
    """
    try:
        from zoneinfo import ZoneInfo
        
        broadcasts_repo = BroadcastsRepository()
        broadcast = broadcasts_repo.get_broadcast(broadcast_id)
        
        if not broadcast:
            raise HTTPException(status_code=404, detail="Broadcast not found")
        
        # Verify admin owns this broadcast
        if broadcast.admin_id != str(admin_id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Can only update pending broadcasts
        if broadcast.status != "pending":
            raise HTTPException(status_code=400, detail="Can only update pending broadcasts")
        
        # Parse scheduled time if provided
        scheduled_dt = None
        if update_request.scheduled_time_utc:
            try:
                scheduled_dt = datetime.fromisoformat(update_request.scheduled_time_utc.replace('Z', '+00:00'))
                if scheduled_dt.tzinfo is None:
                    scheduled_dt = scheduled_dt.replace(tzinfo=ZoneInfo("UTC"))
                scheduled_dt = scheduled_dt.astimezone(ZoneInfo("UTC"))
                
                # Check if time is in the past
                now_utc = datetime.now(ZoneInfo("UTC"))
                if scheduled_dt < now_utc:
                    raise HTTPException(status_code=400, detail="Scheduled time cannot be in the past")
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid scheduled_time_utc format: {e}")
        
        # Update broadcast
        success = broadcasts_repo.update_broadcast(
            broadcast_id=broadcast_id,
            message=update_request.message,
            target_user_ids=update_request.target_user_ids,
            scheduled_time_utc=scheduled_dt,
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update broadcast")
        
        # Get updated broadcast
        updated_broadcast = broadcasts_repo.get_broadcast(broadcast_id)
        if not updated_broadcast:
            raise HTTPException(status_code=500, detail="Failed to retrieve updated broadcast")
        
        return BroadcastResponse(
            broadcast_id=updated_broadcast.broadcast_id,
            admin_id=updated_broadcast.admin_id,
            message=updated_broadcast.message,
            target_user_ids=updated_broadcast.target_user_ids,
            scheduled_time_utc=updated_broadcast.scheduled_time_utc.isoformat(),
            status=updated_broadcast.status,
            bot_token_id=updated_broadcast.bot_token_id,
            created_at=updated_broadcast.created_at.isoformat() if updated_broadcast.created_at else "",
            updated_at=updated_broadcast.updated_at.isoformat() if updated_broadcast.updated_at else "",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating broadcast: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update broadcast: {str(e)}")


@router.delete("/broadcasts/{broadcast_id}")
async def cancel_broadcast(
    request: Request,
    broadcast_id: str,
    admin_id: int = Depends(get_admin_user)
):
    """
    Cancel a scheduled broadcast (admin only).
    
    Args:
        broadcast_id: Broadcast ID
        admin_id: Admin user ID (from dependency)
    
    Returns:
        Success message
    """
    try:
        broadcasts_repo = BroadcastsRepository()
        broadcast = broadcasts_repo.get_broadcast(broadcast_id)
        
        if not broadcast:
            raise HTTPException(status_code=404, detail="Broadcast not found")
        
        # Verify admin owns this broadcast
        if broadcast.admin_id != str(admin_id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Can only cancel pending broadcasts
        if broadcast.status != "pending":
            raise HTTPException(status_code=400, detail="Can only cancel pending broadcasts")
        
        # Cancel broadcast
        success = broadcasts_repo.cancel_broadcast(broadcast_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to cancel broadcast")
        
        return {"status": "success", "message": "Broadcast cancelled successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error cancelling broadcast: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel broadcast: {str(e)}")


@router.get("/templates")
async def list_admin_templates(
    request: Request,
    admin_id: int = Depends(get_admin_user)
):
    """List all templates (admin only, includes inactive)."""
    try:
        templates_repo = TemplatesRepository()
        # Get all templates, including inactive
        templates = templates_repo.list_templates(is_active=None)
        return {"templates": templates}
    except Exception as e:
        logger.exception(f"Error listing admin templates: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list templates: {str(e)}")


@router.post("/templates")
async def create_admin_template(
    request: Request,
    template_data: Dict[str, Any],
    admin_id: int = Depends(get_admin_user)
):
    """Create a new template (admin only)."""
    try:
        templates_repo = TemplatesRepository()
        
        # Validate required fields (simplified schema)
        required_fields = ["title", "category", "target_value"]
        for field in required_fields:
            if field not in template_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Set defaults for optional fields
        template_data.setdefault("metric_type", "count")
        template_data.setdefault("is_active", True)
        
        template_id = templates_repo.create_template(template_data)
        logger.info(f"Admin {admin_id} created template {template_id}")
        return {"status": "success", "template_id": template_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error creating template: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create template: {str(e)}")


@router.put("/templates/{template_id}")
async def update_admin_template(
    request: Request,
    template_id: str,
    template_data: Dict[str, Any],
    admin_id: int = Depends(get_admin_user)
):
    """Update an existing template (admin only)."""
    try:
        templates_repo = TemplatesRepository()
        
        # Check if template exists
        existing = templates_repo.get_template(template_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Template not found")
        
        success = templates_repo.update_template(template_id, template_data)
        if not success:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        logger.info(f"Admin {admin_id} updated template {template_id}")
        return {"status": "success", "message": "Template updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating template: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update template: {str(e)}")


@router.delete("/templates/{template_id}")
async def delete_admin_template(
    request: Request,
    template_id: str,
    admin_id: int = Depends(get_admin_user)
):
    """Delete a template (admin only, with safety checks)."""
    try:
        templates_repo = TemplatesRepository()
        
        # Check if template exists
        existing = templates_repo.get_template(template_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Template not found")
        
        # Check if template is in use
        in_use_check = templates_repo.check_template_in_use(template_id)
        if in_use_check["in_use"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Template cannot be deleted because it is in use",
                    "reasons": in_use_check["reasons"]
                }
            )
        
        # Delete template
        success = templates_repo.delete_template(template_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete template")
        
        logger.info(f"Admin {admin_id} deleted template {template_id}")
        return {"status": "success", "message": "Template deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting template: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete template: {str(e)}")


@router.post("/templates/generate")
async def generate_template_draft(
    request: Request,
    generate_request: GenerateTemplateRequest,
    admin_id: int = Depends(get_admin_user)
):
    """Generate a template draft from a prompt using AI (admin only)."""
    try:
        # Load LLM config
        cfg = load_llm_env()
        
        # Initialize chat model (same as LLMHandler)
        chat_model = None
        if cfg.get("GCP_PROJECT_ID", ""):
            chat_model = ChatGoogleGenerativeAI(
                model=cfg["GCP_GEMINI_MODEL"],
                project=cfg["GCP_PROJECT_ID"],
                location=cfg["GCP_LOCATION"],
                temperature=0.7,
            )
        
        if not chat_model and cfg.get("OPENAI_API_KEY", ""):
            chat_model = ChatOpenAI(
                openai_api_key=cfg["OPENAI_API_KEY"],
                temperature=0.7,
                model="gpt-4o-mini",
            )
        
        if not chat_model:
            raise HTTPException(status_code=500, detail="No LLM configured")
        
        # Create prompt for template generation (simplified schema)
        system_prompt = """You are a template generator for a goal-tracking app. Generate a promise template from a user's description.

Output ONLY valid JSON with these fields:
{
  "title": "string (short, clear title, e.g., 'Exercise Daily', 'Read Books')",
  "description": "string (optional - brief motivation or details, 1 sentence max)",
  "category": "string (one of: 'health', 'fitness', 'learning', 'productivity', 'mindfulness', 'creativity', 'finance', 'social', 'self-care', 'other')",
  "target_value": number (how many per week, e.g., 7 for daily, 3 for 3x/week),
  "metric_type": "string ('count' for times/week or 'hours' for hours/week)",
  "emoji": "string (single emoji that represents this activity, e.g., '🏃', '📚', '💪')"
}

Rules:
- title should be short and actionable (2-4 words)
- If user mentions hours/week, use metric_type='hours'
- If user mentions times/week, days/week, or daily, use metric_type='count'
- For daily habits, target_value=7; for 3x/week, target_value=3; etc.
- Pick a relevant emoji from: 🏃📚💪🧘🎯✍️🎨🎵💻🌱💧😴🍎💰🧠❤️
- Output ONLY the JSON object, no markdown, no explanation"""
        
        user_prompt = f"Generate a promise template for: {generate_request.prompt}"
        
        # Call LLM
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = chat_model.invoke(messages)
        content = response.content if hasattr(response, 'content') else str(response)
        
        # Parse JSON (handle markdown code blocks if present)
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        draft = json.loads(content)
        
        # Validate required fields
        if "title" not in draft:
            raise HTTPException(status_code=500, detail="Generated template missing required field: title")
        if "target_value" not in draft:
            draft["target_value"] = 7  # Default to daily
        
        # Set defaults for optional fields
        draft.setdefault("description", "")
        draft.setdefault("category", "other")
        draft.setdefault("metric_type", "count")
        draft.setdefault("emoji", "🎯")
        
        # Validate enums
        valid_categories = ['health', 'fitness', 'learning', 'productivity', 'mindfulness', 'creativity', 'finance', 'social', 'self-care', 'other']
        if draft["category"] not in valid_categories:
            draft["category"] = "other"
        if draft["metric_type"] not in ["hours", "count"]:
            draft["metric_type"] = "count"
        
        # Clamp target_value
        if draft["target_value"] <= 0:
            draft["target_value"] = 1
        
        # Set is_active default
        draft["is_active"] = True
        
        logger.info(f"Admin {admin_id} generated template draft from prompt: {generate_request.prompt[:50]}")
        return draft
        
    except json.JSONDecodeError as e:
        logger.exception(f"Failed to parse LLM response as JSON: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to parse AI response: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error generating template draft: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate template draft: {str(e)}")


@router.post("/promises")
async def create_promise_for_user(
    request: Request,
    promise_request: CreatePromiseForUserRequest,
    admin_id: int = Depends(get_admin_user)
):
    """Create a promise for a user (admin only)."""
    try:
        from services.planner_api_adapter import PlannerAPIAdapter
        from datetime import date as date_type
        from datetime import time as time_type
        
        # Validate visibility
        if promise_request.visibility not in ["private", "followers", "clubs", "public"]:
            raise HTTPException(status_code=400, detail="Visibility must be 'private', 'followers', 'clubs', or 'public'")
        
        # Parse dates
        start_date_obj = None
        end_date_obj = None
        if promise_request.start_date:
            try:
                start_date_obj = date_type.fromisoformat(promise_request.start_date)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid start_date format: {promise_request.start_date}. Expected YYYY-MM-DD")
        
        if promise_request.end_date:
            try:
                end_date_obj = date_type.fromisoformat(promise_request.end_date)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid end_date format: {promise_request.end_date}. Expected YYYY-MM-DD")
        
        # Validate dates
        if start_date_obj and end_date_obj and start_date_obj > end_date_obj:
            raise HTTPException(status_code=400, detail="start_date must be <= end_date")
        
        # Validate hours_per_week
        if promise_request.hours_per_week < 0:
            raise HTTPException(status_code=400, detail="hours_per_week must be >= 0")
        
        # Create promise using PlannerAPIAdapter
        plan_keeper = PlannerAPIAdapter(request.app.state.root_dir)
        result = plan_keeper.add_promise(
            user_id=promise_request.target_user_id,
            promise_text=promise_request.text,
            num_hours_promised_per_week=promise_request.hours_per_week,
            recurring=promise_request.recurring,
            start_date=start_date_obj,
            end_date=end_date_obj
        )
        
        # Extract promise_id from result message (format: "#P123456 Promise 'text' added successfully.")
        match = re.search(r'#([PT]\w+)', result)
        if not match:
            raise HTTPException(status_code=500, detail="Failed to extract promise ID from creation result")
        promise_id = match.group(1)
        
        # Update visibility and description if provided
        promises_repo = PromisesRepository()
        promise = promises_repo.get_promise(promise_request.target_user_id, promise_id)
        if not promise:
            raise HTTPException(status_code=500, detail="Failed to retrieve created promise")
        
        if promise_request.visibility != "private" or promise_request.description:
            promise.visibility = promise_request.visibility
            if promise_request.description:
                promise.description = promise_request.description
            promises_repo.upsert_promise(promise_request.target_user_id, promise)
        
        # Create reminders if provided
        if promise_request.reminders:
            # Get user's timezone
            settings_repo = SettingsRepository()
            settings = settings_repo.get_settings(promise_request.target_user_id)
            user_tz = settings.timezone if settings and settings.timezone and settings.timezone != "DEFAULT" else "UTC"
            
            # Get promise_uuid
            user_str = str(promise_request.target_user_id)
            with get_db_session() as session:
                promise_uuid = resolve_promise_uuid(session, user_str, promise_id)
                if not promise_uuid:
                    raise HTTPException(status_code=500, detail="Failed to resolve promise UUID")
            
            # Convert reminders to ReminderRequest format
            reminders_repo = RemindersRepository()
            dispatch_service = ReminderDispatchService()
            
            reminders_data = []
            for rem in promise_request.reminders:
                if not rem.enabled:
                    continue
                
                # Validate weekday
                if rem.weekday < 0 or rem.weekday > 6:
                    raise HTTPException(status_code=400, detail=f"Invalid weekday: {rem.weekday}. Must be 0-6 (Monday-Sunday)")
                
                # Validate time format
                try:
                    time_parts = rem.time.split(":")
                    if len(time_parts) != 2:
                        raise ValueError
                    hour = int(time_parts[0])
                    minute = int(time_parts[1])
                    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                        raise ValueError
                    time_obj = time_type(hour, minute)
                except (ValueError, IndexError):
                    raise HTTPException(status_code=400, detail=f"Invalid time format: {rem.time}. Expected HH:MM")
                
                reminder_data = {
                    "promise_uuid": promise_uuid,
                    "kind": "fixed_time",
                    "weekday": rem.weekday,
                    "time_local": time_obj,
                    "tz": user_tz,
                    "enabled": True
                }
                
                # Compute next_run_at_utc
                next_run = dispatch_service.compute_next_run_at_utc(reminder_data, promise_request.target_user_id)
                if next_run:
                    reminder_data["next_run_at_utc"] = dt_to_utc_iso(next_run)
                
                reminders_data.append(reminder_data)
            
            # Replace reminders
            if reminders_data:
                reminders_repo.replace_reminders(promise_uuid, reminders_data)
        
        logger.info(f"Admin {admin_id} created promise {promise_id} for user {promise_request.target_user_id}")
        return {"status": "success", "promise_id": promise_id, "message": result}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error creating promise for user: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create promise: {str(e)}")


@router.get("/graph/follow")
async def get_follow_graph(
    request: Request,
    limit: int = Query(default=2000, ge=1, le=10000, description="Max number of follow edges to return"),
    admin_id: int = Depends(get_admin_user)
):
    """
    Return the full follow graph for admin visualisation.

    Response shape:
    {
        "nodes": [{ "id": str, "username": str|null, "first_name": str|null,
                    "follower_count": int, "following_count": int }],
        "edges": [{ "source": str, "target": str }],
        "total_edges": int,
        "total_nodes": int
    }
    """
    try:
        with get_db_session() as session:
            # Fetch all active follow edges (most recent first)
            edges_rows = session.execute(
                text("""
                    SELECT source_user_id, target_user_id
                    FROM user_relationships
                    WHERE relationship_type = 'follow'
                      AND is_active = 1
                    ORDER BY created_at_utc DESC
                    LIMIT :limit
                """),
                {"limit": limit}
            ).fetchall()

            if not edges_rows:
                return {"nodes": [], "edges": [], "total_edges": 0, "total_nodes": 0}

            edges = [{"source": str(r[0]), "target": str(r[1])} for r in edges_rows]

            # Collect all unique user IDs
            user_ids: set = set()
            for e in edges:
                user_ids.add(e["source"])
                user_ids.add(e["target"])

            # Build per-user follower/following counts from the edge list (no extra query)
            follower_count: Dict[str, int] = {}
            following_count: Dict[str, int] = {}
            for e in edges:
                following_count[e["source"]] = following_count.get(e["source"], 0) + 1
                follower_count[e["target"]] = follower_count.get(e["target"], 0) + 1

            # Fetch display info for all involved users from user_settings
            if user_ids:
                placeholders = ", ".join([f":uid_{i}" for i in range(len(user_ids))])
                params = {f"uid_{i}": uid for i, uid in enumerate(user_ids)}
                settings_rows = session.execute(
                    text(f"""
                        SELECT user_id, first_name, username
                        FROM user_settings
                        WHERE user_id IN ({placeholders})
                    """),
                    params
                ).fetchall()
            else:
                settings_rows = []

            user_info: Dict[str, Dict[str, Any]] = {}
            for row in settings_rows:
                user_info[str(row[0])] = {
                    "username": row[2],
                    "first_name": row[1],
                }

            nodes = []
            for uid in user_ids:
                info = user_info.get(uid, {})
                nodes.append({
                    "id": uid,
                    "username": info.get("username"),
                    "first_name": info.get("first_name"),
                    "follower_count": follower_count.get(uid, 0),
                    "following_count": following_count.get(uid, 0),
                })

            return {
                "nodes": nodes,
                "edges": edges,
                "total_edges": len(edges),
                "total_nodes": len(nodes),
            }

    except Exception as e:
        logger.exception(f"Error fetching follow graph: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch follow graph: {str(e)}")


@router.post("/promote")
async def promote_staging_to_prod(
    request: Request,
    admin_id: int = Depends(get_admin_user)
):
    """
    Promote staging database to production (admin only).
    This copies all data from staging to production database.
    WARNING: This will overwrite all production data!
    """
    try:
        prod_url = os.getenv("DATABASE_URL_PROD")
        staging_url = os.getenv("DATABASE_URL_STAGING")
        
        if not prod_url:
            raise HTTPException(status_code=500, detail="DATABASE_URL_PROD environment variable is not set")
        
        if not staging_url:
            raise HTTPException(status_code=500, detail="DATABASE_URL_STAGING environment variable is not set")
        
        logger.warning(f"Admin {admin_id} initiated staging to production promotion")
        logger.warning(f"Staging: {staging_url}")
        logger.warning(f"Production: {prod_url}")
        
        # Dump staging database
        logger.info("Dumping staging database...")
        dump_process = subprocess.run(
            ["pg_dump", staging_url],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if dump_process.returncode != 0:
            error_msg = dump_process.stderr or "Unknown error during pg_dump"
            logger.error(f"pg_dump failed: {error_msg}")
            raise HTTPException(status_code=500, detail=f"Failed to dump staging database: {error_msg}")
        
        dump_sql = dump_process.stdout
        
        # Restore to production
        logger.info("Restoring to production database...")
        restore_process = subprocess.run(
            ["psql", prod_url],
            input=dump_sql,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )
        
        if restore_process.returncode != 0:
            error_msg = restore_process.stderr or "Unknown error during psql restore"
            logger.error(f"psql restore failed: {error_msg}")
            raise HTTPException(status_code=500, detail=f"Failed to restore to production: {error_msg}")
        
        # CRITICAL: Sync sequences after restore
        # pg_dump includes explicit IDs, but sequences don't auto-update
        # This prevents duplicate key errors on the next insert
        logger.info("Syncing PostgreSQL sequences after restore...")
        sync_sequences_sql = """
            DO $$
            DECLARE
                r RECORD;
                seq_name TEXT;
                max_val BIGINT;
            BEGIN
                FOR r IN (
                    SELECT 
                        t.table_name,
                        c.column_name
                    FROM information_schema.tables t
                    JOIN information_schema.columns c 
                        ON t.table_name = c.table_name 
                        AND t.table_schema = c.table_schema
                    WHERE t.table_schema = 'public'
                        AND t.table_type = 'BASE TABLE'
                        AND c.column_default LIKE 'nextval%'
                )
                LOOP
                    seq_name := pg_get_serial_sequence('public.' || r.table_name, r.column_name);
                    IF seq_name IS NOT NULL THEN
                        EXECUTE format('SELECT COALESCE(MAX(%I), 0) FROM %I', r.column_name, r.table_name) INTO max_val;
                        EXECUTE format('SELECT setval(%L, GREATEST(%s, 1))', seq_name, max_val);
                        RAISE NOTICE 'Synced sequence % to %', seq_name, max_val;
                    END IF;
                END LOOP;
            END $$;
        """
        
        sync_process = subprocess.run(
            ["psql", prod_url, "-c", sync_sequences_sql],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if sync_process.returncode != 0:
            # Log warning but don't fail - data was restored successfully
            logger.warning(f"Sequence sync warning (data restored OK): {sync_process.stderr}")
        else:
            logger.info("Sequences synced successfully")
        
        logger.info(f"Admin {admin_id} successfully promoted staging to production")
        return {
            "status": "success",
            "message": "Staging database successfully promoted to production"
        }
        
    except subprocess.TimeoutExpired:
        logger.error("Promotion operation timed out")
        raise HTTPException(status_code=500, detail="Promotion operation timed out. Please check database status.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error promoting staging to production: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to promote staging to production: {str(e)}")


# ============================================================================
# Test Run Endpoints
# ============================================================================

@router.post("/tests/run", response_model=TestRunResponse)
async def run_tests(
    request: Request,
    test_request: RunTestsRequest,
    admin_id: int = Depends(get_admin_user)
):
    """
    Start a test run (admin only).
    Runs tests in a staging-only sandbox environment.
    """
    global _test_run_active
    
    # Check if a test run is already active
    with _test_run_lock:
        if _test_run_active:
            raise HTTPException(status_code=409, detail="A test run is already in progress")
        _test_run_active = True
    
    try:
        # Validate test suite
        if test_request.test_suite not in ['pytest', 'scenarios', 'both']:
            raise HTTPException(status_code=400, detail="test_suite must be 'pytest', 'scenarios', or 'both'")
        
        # Generate run ID
        run_id = str(uuid.uuid4())
        
        # Get staging database URL (required)
        staging_db_url = os.getenv("DATABASE_URL_STAGING")
        if not staging_db_url:
            raise HTTPException(status_code=500, detail="DATABASE_URL_STAGING environment variable is not set")
        
        # Create temporary sandbox directory
        sandbox_dir = tempfile.mkdtemp(prefix=f"zana_test_{run_id}_")
        
        # Get GCP credentials from environment (for LLM tests)
        gcp_project_id = os.getenv("GCP_PROJECT_ID")
        gcp_location = os.getenv("GCP_LOCATION", "us-central1")
        gcp_model = os.getenv("GCP_GEMINI_MODEL", "gemini-2.5-flash")
        gcp_creds_b64 = os.getenv("GCP_CREDENTIALS_B64")
        
        # Initialize test run record
        test_run = {
            'run_id': run_id,
            'status': 'running',
            'test_suite': test_request.test_suite,
            'started_at': datetime.now(timezone.utc).isoformat(),
            'completed_at': None,
            'exit_code': None,
            'sandbox_dir': sandbox_dir,
            'output': [],
            'report_path': None,
            'error': None
        }
        
        with _test_run_lock:
            _test_runs[run_id] = test_run
        
        # Start test run in background thread
        def run_tests_thread():
            try:
                # Build environment for subprocess (staging-only)
                env = os.environ.copy()
                env['ENVIRONMENT'] = 'staging'
                env['DATABASE_URL_STAGING'] = staging_db_url
                env['DATABASE_URL'] = staging_db_url  # Fallback
                env['ROOT_DIR'] = sandbox_dir
                
                # Remove production DB URLs to prevent accidental access
                env.pop('DATABASE_URL_PROD', None)
                
                # Add GCP credentials if available
                if gcp_project_id:
                    env['GCP_PROJECT_ID'] = gcp_project_id
                if gcp_location:
                    env['GCP_LOCATION'] = gcp_location
                if gcp_model:
                    env['GCP_GEMINI_MODEL'] = gcp_model
                if gcp_creds_b64:
                    env['GCP_CREDENTIALS_B64'] = gcp_creds_b64
                
                # Determine root directory for running tests
                # Find zana_planner directory by starting from this file's location
                current_file = __file__  # This file: tm_bot/webapp/routers/admin.py
                current = os.path.abspath(os.path.dirname(current_file))
                # Go up: routers -> webapp -> tm_bot -> zana_planner
                repo_root = None
                for _ in range(4):  # Max 4 levels up
                    if os.path.basename(current) == 'zana_planner' and os.path.exists(os.path.join(current, 'requirements.txt')):
                        repo_root = current
                        break
                    current = os.path.dirname(current)
                    if current == os.path.dirname(current):  # Reached root
                        break
                
                # Fallback: try to find from root_dir
                if not repo_root:
                    root_dir = request.app.state.root_dir
                    current = os.path.abspath(root_dir)
                    while current != os.path.dirname(current):
                        if os.path.basename(current) == 'zana_planner' and os.path.exists(os.path.join(current, 'requirements.txt')):
                            repo_root = current
                            break
                        current = os.path.dirname(current)
                
                if not repo_root:
                    raise ValueError("Could not find zana_planner directory. Ensure tests are run from the repository root.")
                
                # Change to repo root for test execution
                os.chdir(repo_root)
                
                # Build command based on test suite
                commands = []
                report_paths = []
                
                if test_request.test_suite in ['pytest', 'both']:
                    reports_dir = os.path.join(sandbox_dir, 'reports')
                    os.makedirs(reports_dir, exist_ok=True)
                    pytest_report = os.path.join(reports_dir, 'test_report.html')
                    commands.append({
                        'name': 'pytest',
                        'cmd': [
                            'python', '-m', 'pytest',
                            '--html', pytest_report,
                            '--self-contained-html',
                            '-m', 'not e2e',
                            '-v'
                        ],
                        'report': pytest_report
                    })
                
                if test_request.test_suite in ['scenarios', 'both']:
                    reports_dir = os.path.join(sandbox_dir, 'reports')
                    os.makedirs(reports_dir, exist_ok=True)
                    scenario_report = os.path.join(reports_dir, 'scenario_report.txt')
                    commands.append({
                        'name': 'scenarios',
                        'cmd': [
                            'python', '-m', 'tm_bot.platforms.testing.run_scenarios'
                        ],
                        'report': scenario_report
                    })
                
                # Run each command
                all_output = []
                exit_code = 0
                
                for cmd_info in commands:
                    cmd_name = cmd_info['name']
                    cmd = cmd_info['cmd']
                    report_path = cmd_info['report']
                    
                    logger.info(f"Running {cmd_name} test suite...")
                    
                    # Capture output
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        env=env,
                        cwd=repo_root
                    )
                    
                    # Stream output line by line
                    output_lines = []
                    for line in iter(process.stdout.readline, ''):
                        if not line:
                            break
                        line = line.rstrip()
                        output_lines.append(line)
                        all_output.append(f"[{cmd_name}] {line}")
                        
                        # Update test run with output
                        with _test_run_lock:
                            if run_id in _test_runs:
                                _test_runs[run_id]['output'].append(f"[{cmd_name}] {line}")
                    
                    process.wait()
                    cmd_exit_code = process.returncode
                    
                    if cmd_exit_code != 0:
                        exit_code = cmd_exit_code
                    
                    # Save report if it exists
                    if os.path.exists(report_path):
                        with _test_run_lock:
                            if run_id in _test_runs:
                                _test_runs[run_id]['report_path'] = report_path
                    
                    # For scenarios, also save output as report
                    if cmd_name == 'scenarios' and output_lines:
                        with open(report_path, 'w', encoding='utf-8') as f:
                            f.write('\n'.join(output_lines))
                        with _test_run_lock:
                            if run_id in _test_runs:
                                _test_runs[run_id]['report_path'] = report_path
                
                # Update test run status
                with _test_run_lock:
                    if run_id in _test_runs:
                        _test_runs[run_id]['status'] = 'completed' if exit_code == 0 else 'failed'
                        _test_runs[run_id]['completed_at'] = datetime.now(timezone.utc).isoformat()
                        _test_runs[run_id]['exit_code'] = exit_code
                        _test_runs[run_id]['output'] = all_output
                
            except Exception as e:
                logger.exception(f"Error running tests: {e}")
                with _test_run_lock:
                    if run_id in _test_runs:
                        _test_runs[run_id]['status'] = 'failed'
                        _test_runs[run_id]['completed_at'] = datetime.now(timezone.utc).isoformat()
                        _test_runs[run_id]['error'] = str(e)
            finally:
                global _test_run_active
                with _test_run_lock:
                    _test_run_active = False
        
        # Start thread
        thread = threading.Thread(target=run_tests_thread, daemon=True)
        thread.start()
        
        return TestRunResponse(
            run_id=run_id,
            status='running',
            test_suite=test_request.test_suite,
            started_at=test_run['started_at']
        )
        
    except HTTPException:
        with _test_run_lock:
            _test_run_active = False
        raise
    except Exception as e:
        logger.exception(f"Error starting test run: {e}")
        with _test_run_lock:
            _test_run_active = False
        raise HTTPException(status_code=500, detail=f"Failed to start test run: {str(e)}")


@router.get("/tests/stream/{run_id}")
async def stream_test_output(
    request: Request,
    run_id: str,
    token: Optional[str] = Query(None, description="Session token for authentication"),
    init_data: Optional[str] = Query(None, description="Telegram initData for authentication")
):
    """
    Stream test run output via Server-Sent Events (SSE).
    Note: EventSource doesn't support custom headers, so auth is passed via query params.
    """
    # Authenticate using query parameters (EventSource limitation)
    app = request.app
    user_id = None
    
    # Try session token first
    if token:
        auth_session_repo = app.state.auth_session_repo
        session = auth_session_repo.get_session(token)
        if session:
            user_id = session.user_id
    
    # Fall back to initData (URL-decoded automatically by FastAPI)
    if not user_id and init_data:
        try:
            from webapp.auth import validate_telegram_init_data, extract_user_id
            # FastAPI automatically URL-decodes query params, but handle edge cases
            validated = validate_telegram_init_data(init_data, app.state.bot_token)
            if validated:
                user_id = extract_user_id(validated)
        except Exception as e:
            logger.debug(f"Failed to validate initData from query param: {e}")
            pass
    
    # Also try headers as fallback (for direct browser access)
    if not user_id:
        try:
            from ..dependencies import get_current_user
            user_id = await get_current_user(request)
        except HTTPException:
            pass
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Check admin status
    from utils.admin_utils import is_admin
    if not is_admin(user_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    async def event_generator():
        last_index = 0
        
        while True:
            with _test_run_lock:
                if run_id not in _test_runs:
                    yield f"data: {json.dumps({'error': 'Test run not found'})}\n\n"
                    break
                
                test_run = _test_runs[run_id]
                status = test_run['status']
                output = test_run.get('output', [])
                
                # Send new output lines
                if len(output) > last_index:
                    for line in output[last_index:]:
                        yield f"data: {json.dumps({'type': 'output', 'line': line})}\n\n"
                    last_index = len(output)
                
                # Send status updates
                yield f"data: {json.dumps({'type': 'status', 'status': status, 'exit_code': test_run.get('exit_code')})}\n\n"
                
                # If completed, send final message and break
                if status in ['completed', 'failed']:
                    yield f"data: {json.dumps({'type': 'complete', 'status': status, 'exit_code': test_run.get('exit_code')})}\n\n"
                    break
            
            await asyncio.sleep(0.5)  # Poll every 500ms
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.get("/tests/report/{run_id}", response_model=TestReportResponse)
async def get_test_report(
    request: Request,
    run_id: str,
    admin_id: int = Depends(get_admin_user)
):
    """
    Get test run report (admin only).
    """
    with _test_run_lock:
        if run_id not in _test_runs:
            raise HTTPException(status_code=404, detail="Test run not found")
        
        test_run = _test_runs[run_id]
    
    # Read report content if available
    report_content = None
    if test_run.get('report_path') and os.path.exists(test_run['report_path']):
        try:
            with open(test_run['report_path'], 'r', encoding='utf-8') as f:
                report_content = f.read()
        except Exception as e:
            logger.warning(f"Failed to read report file: {e}")
    
    return TestReportResponse(
        run_id=test_run['run_id'],
        status=test_run['status'],
        test_suite=test_run['test_suite'],
        started_at=test_run['started_at'],
        completed_at=test_run.get('completed_at'),
        exit_code=test_run.get('exit_code'),
        report_content=report_content
    )
