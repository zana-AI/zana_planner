"""
Platform-agnostic base handler classes.

These classes contain the core business logic that is independent of
the platform (Telegram, Discord, etc.). Platform-specific handlers
should inherit from these and add platform-specific code.
"""

from abc import ABC
from typing import Optional, List, Dict, Any
from datetime import datetime

from platforms.types import UserMessage, BotResponse, CallbackQuery, Keyboard
from platforms.interfaces import IResponseService
from services.planner_api_adapter import PlannerAPIAdapter
from llms.llm_handler import LLMHandler
from handlers.messages_store import get_user_language, Language
from utils.logger import get_logger

logger = get_logger(__name__)


class BaseMessageHandler(ABC):
    """Base class for platform-agnostic message handling."""
    
    def __init__(
        self,
        plan_keeper: PlannerAPIAdapter,
        llm_handler: LLMHandler,
        response_service: IResponseService,
        root_dir: str,
    ):
        """Initialize base message handler."""
        self.plan_keeper = plan_keeper
        self.llm_handler = llm_handler
        self.response_service = response_service
        self.root_dir = root_dir
    
    def get_user_timezone(self, user_id: int) -> str:
        """Get user timezone using the settings service."""
        return self.plan_keeper.settings_service.get_user_timezone(user_id)
    
    def set_user_timezone(self, user_id: int, tzname: str) -> None:
        """Set user timezone using the settings service."""
        self.plan_keeper.settings_service.set_user_timezone(user_id, tzname)
    
    async def handle_text_message(self, message: UserMessage) -> BotResponse:
        """
        Handle a text message from a user.
        
        This is the core message handling logic that works with
        platform-agnostic types. Platform-specific handlers should
        call this method after converting platform types.
        """
        user_id = message.user_id
        user_message = message.text or ""
        user_lang = get_user_language(user_id)
        
        # Log user message
        self.response_service.log_user_message(
            user_id=user_id,
            content=user_message,
            message_id=message.message_id,
            chat_id=message.chat_id,
        )
        
        # Get user language code for LLM
        user_lang_code = user_lang.value if user_lang else "en"
        
        # Process through LLM
        llm_response = self.llm_handler.get_response_api(
            user_message, str(user_id),
            user_language=user_lang_code
        )
        
        # Check for errors
        if "error" in llm_response:
            error_msg = llm_response["response_to_user"]
            return BotResponse(text=error_msg, parse_mode="Markdown")
        
        # Process the LLM response
        try:
            func_call_response = self.call_planner_api(user_id, llm_response)
            response_text = llm_response.get("response_to_user", "")
            formatted_response = self._format_response(response_text, func_call_response)
            
            return BotResponse(text=formatted_response)
        except Exception as e:
            error_msg = f"Error processing request: {str(e)}"
            logger.error(f"Error processing request for user {user_id}: {str(e)}")
            return BotResponse(text=error_msg)
    
    def call_planner_api(self, user_id: int, llm_response: dict) -> str:
        """Process user message by sending it to the LLM and executing the identified action."""
        try:
            # If the agent already executed tools, avoid double-calling the API.
            if llm_response.get("executed_by_agent"):
                return llm_response.get("tool_outputs") or ""

            # Interpret LLM response
            function_name = llm_response.get("function_call", None)
            if function_name is None:
                return ""
            
            func_args = llm_response.get("function_args", {})
            func_args["user_id"] = user_id
            
            # Get the corresponding method from plan_keeper
            if hasattr(self.plan_keeper, function_name):
                method = getattr(self.plan_keeper, function_name)
                return method(**func_args)
            else:
                return f"Function {function_name} not found in PlannerAPI"
        except Exception as e:
            return f"Error executing function: {str(e)}"
    
    def _format_response(self, llm_response: str, func_call_response) -> str:
        """Format the response for display."""
        try:
            from utils.formatting import format_response_html
            return format_response_html(llm_response, func_call_response)
        except Exception as e:
            logger.error(f"Error formatting response: {str(e)}")
            return "Error formatting response"


class BaseCallbackHandler(ABC):
    """Base class for platform-agnostic callback handling."""
    
    def __init__(
        self,
        plan_keeper: PlannerAPIAdapter,
        response_service: IResponseService,
    ):
        """Initialize base callback handler."""
        self.plan_keeper = plan_keeper
        self.response_service = response_service
    
    def get_user_timezone(self, user_id: int) -> str:
        """Get user timezone using the settings service."""
        return self.plan_keeper.settings_service.get_user_timezone(user_id)
    
    async def handle_callback(self, query: CallbackQuery) -> Optional[BotResponse]:
        """
        Handle a callback query from a user.
        
        This is the core callback handling logic that works with
        platform-agnostic types. Platform-specific handlers should
        call this method after converting platform types.
        
        Returns:
            BotResponse if a response should be sent, None otherwise
        """
        # Parse callback data
        from cbdata import decode_cb
        cb = decode_cb(query.data)
        action = cb.get("a")
        
        # Route to specific handlers based on action
        # This is a simplified version - full implementation in platform-specific handlers
        logger.info(f"Handling callback action: {action} for user {query.user_id}")
        
        # Return None by default - platform-specific handlers will implement full logic
        return None

