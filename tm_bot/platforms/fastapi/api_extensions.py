"""
FastAPI API extensions for bot interactions.

Extends the existing webapp API with bot interaction endpoints.
"""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from webapp.auth import validate_telegram_init_data, extract_user_id
from platforms.fastapi.response_service import FastAPIResponseService
from platforms.fastapi.adapter import FastAPIPlatformAdapter
from platforms.types import UserMessage, MessageType
from platforms.testing.cli_handler_wrapper import CLIHandlerWrapper
from utils.logger import get_logger

logger = get_logger(__name__)


# Request/Response Models
class SendMessageRequest(BaseModel):
    """Request model for sending a message."""
    text: str
    message_id: Optional[int] = None


class SendMessageResponse(BaseModel):
    """Response model for sending a message."""
    success: bool
    response_id: Optional[str] = None
    message: Optional[str] = None


class BotResponseModel(BaseModel):
    """Model for bot response."""
    type: str
    text: Optional[str] = None
    keyboard: Optional[Dict[str, Any]] = None
    timestamp: str


class GetResponsesResponse(BaseModel):
    """Response model for getting responses."""
    responses: List[BotResponseModel]
    count: int


def create_user_auth_dependency(app: FastAPI):
    """
    Create a dependency function that validates Telegram auth.
    This factory function allows us to access app state.
    """
    async def get_user_id_from_header(
        x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data"),
        authorization: Optional[str] = Header(None),
    ) -> int:
        """
        Validate Telegram auth and return user_id.
        Reusable dependency for endpoints.
        """
        init_data = x_telegram_init_data
        
        if not init_data and authorization:
            if authorization.startswith("Bearer "):
                init_data = authorization[7:]
            else:
                init_data = authorization
        
        if not init_data:
            raise HTTPException(
                status_code=401,
                detail="Missing Telegram authentication data"
            )
        
        # Get bot token from app state or environment
        bot_token = getattr(app.state, 'bot_token', None) or os.getenv("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            raise HTTPException(
                status_code=500,
                detail="Bot token not configured"
            )
        
        validated = validate_telegram_init_data(init_data, bot_token)
        if not validated:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired Telegram authentication"
            )
        
        user_id = extract_user_id(validated)
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Could not extract user ID"
            )
        
        return user_id
    
    return get_user_id_from_header


def add_bot_routes(
    app: FastAPI,
        bot_adapter: FastAPIPlatformAdapter,
        handler_wrapper: CLIHandlerWrapper,
) -> None:
    """
    Add bot interaction routes to FastAPI app.
    
    Args:
        app: FastAPI application
        bot_adapter: FastAPI platform adapter
        handler_wrapper: CLI handler wrapper for processing messages
    """
    # Create auth dependency with app context
    get_user_id = create_user_auth_dependency(app)
    
    response_service: FastAPIResponseService = bot_adapter.response_service
    
    @app.post("/api/bot/message", response_model=SendMessageResponse)
    async def send_message(
        request: SendMessageRequest,
        user_id: int = Depends(get_user_id),
    ):
        """
        Send a message to the bot and get a response.
        """
        try:
            # Create user message
            user_message = UserMessage(
                user_id=user_id,
                chat_id=user_id,
                text=request.text,
                message_type=MessageType.TEXT,
                timestamp=datetime.now(),
                message_id=request.message_id,
            )
            
            # Process message
            if request.text.startswith('/'):
                # Handle command
                command = request.text.split()[0][1:]
                args = request.text.split()[1:] if len(request.text.split()) > 1 else []
                await handler_wrapper.handle_command(command, user_id, args)
            else:
                # Handle regular message
                await handler_wrapper.handle_message(request.text, user_id)
            
            # Get responses
            responses = response_service.get_responses(user_id)
            
            return SendMessageResponse(
                success=True,
                response_id=str(len(responses)),
                message="Message processed"
            )
            
        except Exception as e:
            logger.error(f"Error processing message for user {user_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/bot/responses", response_model=GetResponsesResponse)
    async def get_responses(
        user_id: int = Depends(get_user_id),
        since: Optional[str] = None,
    ):
        """
        Get bot responses for the authenticated user.
        
        Args:
            since: Optional ISO timestamp to get responses since that time
        """
        try:
            since_dt = None
            if since:
                try:
                    since_dt = datetime.fromisoformat(since)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid since format")
            
            responses = response_service.get_responses(user_id, since=since_dt)
            
            # Convert to response models
            response_models = [
                BotResponseModel(
                    type=r.get("type", "text"),
                    text=r.get("text"),
                    keyboard=r.get("keyboard"),
                    timestamp=r.get("timestamp", datetime.now().isoformat()),
                )
                for r in responses
            ]
            
            return GetResponsesResponse(
                responses=response_models,
                count=len(response_models)
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting responses for user {user_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.delete("/api/bot/responses")
    async def clear_responses(
        user_id: int = Depends(get_user_id),
    ):
        """Clear stored responses for the user."""
        try:
            response_service.clear_responses(user_id)
            return {"success": True, "message": "Responses cleared"}
        except Exception as e:
            logger.error(f"Error clearing responses for user {user_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.websocket("/api/bot/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """
        WebSocket endpoint for real-time bot interactions.
        
        Client sends: {"type": "message", "text": "..."}
        Server sends: {"type": "response", "text": "...", "keyboard": {...}}
        """
        await websocket.accept()
        user_id = None
        
        try:
            # Get init data from query params or first message
            init_data = websocket.query_params.get("initData")
            
            if not init_data:
                # Try to get from first message
                first_msg = await websocket.receive_json()
                init_data = first_msg.get("initData")
            
            if not init_data:
                await websocket.close(code=1008, reason="Authentication required")
                return
            
            # Validate auth
            import os
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            if not bot_token:
                await websocket.close(code=1011, reason="Server configuration error")
                return
            
            validated = validate_telegram_init_data(init_data, bot_token)
            if not validated:
                await websocket.close(code=1008, reason="Invalid authentication")
                return
            
            user_id = extract_user_id(validated)
            if not user_id:
                await websocket.close(code=1008, reason="Could not extract user ID")
                return
            
            # Register WebSocket
            response_service.register_websocket(user_id, websocket)
            
            await websocket.send_json({
                "type": "connected",
                "user_id": user_id,
                "message": "Connected to bot"
            })
            
            # Listen for messages
            while True:
                try:
                    data = await websocket.receive_json()
                    
                    if data.get("type") == "message":
                        text = data.get("text", "")
                        
                        # Process message
                        if text.startswith('/'):
                            command = text.split()[0][1:]
                            args = text.split()[1:] if len(text.split()) > 1 else []
                            await handler_wrapper.handle_command(command, user_id, args)
                        else:
                            await handler_wrapper.handle_message(text, user_id)
                        
                        # Get latest response
                        responses = response_service.get_responses(user_id)
                        if responses:
                            latest = responses[-1]
                            await websocket.send_json({
                                "type": "response",
                                "text": latest.get("text"),
                                "keyboard": latest.get("keyboard"),
                                "timestamp": latest.get("timestamp"),
                            })
                    
                    elif data.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                    
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error(f"Error in WebSocket for user {user_id}: {e}", exc_info=True)
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e)
                    })
        
        except Exception as e:
            logger.error(f"WebSocket error: {e}", exc_info=True)
        finally:
            if user_id:
                response_service.unregister_websocket(user_id)
    
    logger.info("Bot interaction routes added to FastAPI app")


def create_bot_api(
    root_dir: str,
    bot_token: str,
    static_dir: Optional[str] = None,
) -> FastAPI:
    """
    Create a FastAPI app with bot interaction endpoints.
    
    This extends the existing webapp API with bot interaction capabilities.
    
    Args:
        root_dir: Root directory for user data
        bot_token: Telegram bot token
        static_dir: Optional static files directory
    
    Returns:
        Configured FastAPI app with bot routes
    """
    # Import existing webapp API creator
    from webapp.api import create_webapp_api
    
    # Create base webapp API
    app = create_webapp_api(root_dir, bot_token, static_dir)
    
    # Store bot_token in app state for auth dependency
    app.state.bot_token = bot_token
    
    # Create FastAPI platform adapter
    bot_adapter = FastAPIPlatformAdapter(app=app)
    bot_adapter.app = app
    
    # Initialize bot with adapter (late import to avoid circular imports)
    from tm_bot.planner_bot import PlannerBot  # pylint: disable=import-error
    bot = PlannerBot(bot_adapter, root_dir=root_dir)
    
    # Create handler wrapper
    if bot.message_handlers and bot.callback_handlers:
        handler_wrapper = CLIHandlerWrapper(bot.message_handlers, bot.callback_handlers)
        
        # Add bot routes
        add_bot_routes(app, bot_adapter, handler_wrapper)
        
        # Store bot and adapter in app state for access
        app.state.bot = bot
        app.state.bot_adapter = bot_adapter
        app.state.handler_wrapper = handler_wrapper
    
    logger.info("FastAPI bot API created with bot interaction endpoints")
    
    return app

