"""
FastAPI response service for web app interactions.

This service handles responses that are sent back to the web app
via WebSocket or stored for polling.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import asyncio

from ..interfaces import IResponseService
from ..types import Keyboard, MediaFile
from utils.logger import get_logger

logger = get_logger(__name__)


class FastAPIResponseService(IResponseService):
    """
    Response service for FastAPI platform.
    
    Stores responses for retrieval via API or sends via WebSocket.
    """
    
    def __init__(self):
        """Initialize FastAPI response service."""
        self._responses: Dict[int, List[Dict[str, Any]]] = {}  # user_id -> list of responses
        self._websocket_connections: Dict[int, Any] = {}  # user_id -> WebSocket
        self._lock = asyncio.Lock()
    
    def register_websocket(self, user_id: int, websocket: Any) -> None:
        """Register a WebSocket connection for a user."""
        self._websocket_connections[user_id] = websocket
        logger.info(f"WebSocket registered for user {user_id}")
    
    def unregister_websocket(self, user_id: int) -> None:
        """Unregister a WebSocket connection for a user."""
        if user_id in self._websocket_connections:
            del self._websocket_connections[user_id]
            logger.info(f"WebSocket unregistered for user {user_id}")
    
    async def _send_via_websocket(self, user_id: int, response: Dict[str, Any]) -> bool:
        """Send response via WebSocket if available."""
        websocket = self._websocket_connections.get(user_id)
        if websocket:
            try:
                await websocket.send_json(response)
                return True
            except Exception as e:
                logger.error(f"Error sending via WebSocket to user {user_id}: {e}")
                self.unregister_websocket(user_id)
        return False
    
    async def _store_response(self, user_id: int, response: Dict[str, Any]) -> None:
        """Store response for later retrieval."""
        async with self._lock:
            if user_id not in self._responses:
                self._responses[user_id] = []
            self._responses[user_id].append(response)
            # Keep only last 100 responses per user
            if len(self._responses[user_id]) > 100:
                self._responses[user_id] = self._responses[user_id][-100:]
    
    async def send_text(
        self,
        user_id: int,
        chat_id: int,
        text: str,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
        disable_web_page_preview: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Send a text message to the user."""
        response = {
            "type": "text",
            "user_id": user_id,
            "chat_id": chat_id,
            "text": text,
            "keyboard": self._keyboard_to_dict(keyboard) if keyboard else None,
            "parse_mode": parse_mode,
            "reply_to_message_id": reply_to_message_id,
            "timestamp": datetime.now().isoformat(),
        }
        
        # Try to send via WebSocket first
        sent = await self._send_via_websocket(user_id, response)
        
        # Always store for polling fallback
        await self._store_response(user_id, response)
        
        return response
    
    async def send_photo(
        self,
        user_id: int,
        chat_id: int,
        photo: Any,
        caption: Optional[str] = None,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Send a photo to the user."""
        # For web app, we'll return a URL or base64 data
        photo_data = None
        if isinstance(photo, str):
            photo_data = photo  # URL or base64
        elif hasattr(photo, 'file_id'):
            photo_data = photo.file_id
        
        response = {
            "type": "photo",
            "user_id": user_id,
            "chat_id": chat_id,
            "photo": photo_data,
            "caption": caption,
            "keyboard": self._keyboard_to_dict(keyboard) if keyboard else None,
            "parse_mode": parse_mode,
            "timestamp": datetime.now().isoformat(),
        }
        
        await self._send_via_websocket(user_id, response)
        await self._store_response(user_id, response)
        
        return response
    
    async def send_voice(
        self,
        user_id: int,
        chat_id: int,
        voice: Any,
    ) -> Optional[Dict[str, Any]]:
        """Send a voice message to the user."""
        voice_data = None
        if isinstance(voice, str):
            voice_data = voice
        elif hasattr(voice, 'file_id'):
            voice_data = voice.file_id
        
        response = {
            "type": "voice",
            "user_id": user_id,
            "chat_id": chat_id,
            "voice": voice_data,
            "timestamp": datetime.now().isoformat(),
        }
        
        await self._send_via_websocket(user_id, response)
        await self._store_response(user_id, response)
        
        return response
    
    async def edit_message(
        self,
        user_id: int,
        chat_id: int,
        message_id: int,
        text: str,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Edit an existing message."""
        response = {
            "type": "edit",
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "keyboard": self._keyboard_to_dict(keyboard) if keyboard else None,
            "parse_mode": parse_mode,
            "timestamp": datetime.now().isoformat(),
        }
        
        await self._send_via_websocket(user_id, response)
        await self._store_response(user_id, response)
        
        return response
    
    async def delete_message(
        self,
        chat_id: int,
        message_id: int,
    ) -> bool:
        """Delete a message."""
        # For web app, we'll store a delete instruction
        response = {
            "type": "delete",
            "chat_id": chat_id,
            "message_id": message_id,
            "timestamp": datetime.now().isoformat(),
        }
        
        # Try to find user_id from stored responses
        user_id = None
        for uid, responses in self._responses.items():
            if any(r.get("message_id") == message_id for r in responses):
                user_id = uid
                break
        
        if user_id:
            await self._send_via_websocket(user_id, response)
            await self._store_response(user_id, response)
        
        return True
    
    def log_user_message(
        self,
        user_id: int,
        content: str,
        message_id: Optional[int] = None,
        chat_id: Optional[int] = None,
    ) -> None:
        """Log a user message for conversation history."""
        # Store user message for context
        log_entry = {
            "type": "user_message",
            "user_id": user_id,
            "content": content,
            "message_id": message_id,
            "chat_id": chat_id,
            "timestamp": datetime.now().isoformat(),
        }
        asyncio.create_task(self._store_response(user_id, log_entry))
    
    def get_responses(self, user_id: int, since: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get stored responses for a user, optionally filtered by timestamp."""
        responses = self._responses.get(user_id, [])
        
        if since:
            since_iso = since.isoformat()
            responses = [r for r in responses if r.get("timestamp", "") >= since_iso]
        
        return responses
    
    def clear_responses(self, user_id: int) -> None:
        """Clear stored responses for a user."""
        if user_id in self._responses:
            self._responses[user_id] = []
    
    def _keyboard_to_dict(self, keyboard: Keyboard) -> Dict[str, Any]:
        """Convert platform-agnostic Keyboard to dict."""
        return {
            "buttons": [
                [
                    {
                        "text": btn.text,
                        "callback_data": btn.callback_data,
                        "url": btn.url,
                    }
                    for btn in row
                ]
                for row in keyboard.buttons
            ]
        }


