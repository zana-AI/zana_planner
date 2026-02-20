"""
CLI platform adapter for direct command-line interaction and testing.

This adapter allows the bot to be used from the command line, enabling
direct end-to-end testing and manual interaction.
"""

from typing import Callable, Optional, Dict, Any
from datetime import datetime
import sys

from ..interfaces import (
    IPlatformAdapter,
    IResponseService,
    IJobScheduler,
    IKeyboardBuilder,
    IMessageHandler,
    ICallbackHandler,
)
from .test_response_service import TestResponseService
from .mock_scheduler import MockJobScheduler
from ..telegram.keyboard_adapter import TelegramKeyboardAdapter
from ..types import UserMessage, MessageType, BotResponse
from utils.logger import get_logger

logger = get_logger(__name__)


class CLIPlatformAdapter(IPlatformAdapter):
    """CLI implementation of IPlatformAdapter for command-line interaction."""
    
    def __init__(self, user_id: int = 1):
        """
        Initialize CLI platform adapter.
        
        Args:
            user_id: Default user ID for CLI interactions
        """
        self._user_id = user_id
        self._chat_id = user_id
        self._response_service = TestResponseService()  # Reuse test service for output
        self._job_scheduler = MockJobScheduler()
        self._keyboard_builder = TelegramKeyboardAdapter()
        
        # Store handlers
        self._message_handlers: Dict[str, IMessageHandler] = {}
        self._callback_handlers: Dict[str, ICallbackHandler] = {}
        self._command_handlers: Dict[str, Callable] = {}
    
    @property
    def response_service(self) -> IResponseService:
        """Get the response service for this platform."""
        return self._response_service
    
    @property
    def job_scheduler(self) -> IJobScheduler:
        """Get the job scheduler for this platform."""
        return self._job_scheduler
    
    @property
    def keyboard_builder(self) -> IKeyboardBuilder:
        """Get the keyboard builder for this platform."""
        return self._keyboard_builder
    
    def register_message_handler(self, handler: IMessageHandler) -> None:
        """Register a message handler."""
        self._message_handlers["default"] = handler
        logger.debug("CLI: Message handler registered")
    
    def register_callback_handler(self, handler: ICallbackHandler) -> None:
        """Register a callback handler."""
        self._callback_handlers["default"] = handler
        logger.debug("CLI: Callback handler registered")
    
    def register_command_handler(self, command: str, handler: Callable) -> None:
        """Register a command handler."""
        self._command_handlers[command] = handler
        logger.debug(f"CLI: Command handler registered for /{command}")
    
    async def start(self) -> None:
        """Start the CLI interface."""
        print("CLI Bot Interface Started")
        print("Type 'exit' or 'quit' to stop")
        print("Type '/help' for available commands")
        print("-" * 50)
    
    async def stop(self) -> None:
        """Stop the CLI interface."""
        print("\nCLI Bot Interface Stopped")
    
    def get_user_info(self, user_id: int) -> dict:
        """Get user information."""
        return {
            "user_id": user_id,
            "username": "cli_user",
            "first_name": "CLI User",
            "platform": "cli"
        }
    
    def set_handlers(self, bot):
        """Set the bot so CLI routes all input through bot.dispatch() (called by PlannerBot)."""
        from .cli_handler_wrapper import CLIHandlerWrapper
        self._handler_wrapper = CLIHandlerWrapper(bot=bot)
    
    async def process_input(self, text: str, user_id: Optional[int] = None) -> Optional[BotResponse]:
        """
        Process user input and return response.
        
        Args:
            text: User input text
            user_id: Optional user ID (defaults to adapter's user_id)
        
        Returns:
            BotResponse if a response should be displayed
        """
        user_id = user_id or self._user_id
        
        # Check if handlers are set
        if not hasattr(self, '_handler_wrapper') or self._handler_wrapper is None:
            return BotResponse(text="Handlers not initialized. Bot may still be starting up.")
        
        # Check if it's a command
        if text.startswith('/'):
            command = text.split()[0][1:]  # Remove leading '/'
            args = text.split()[1:] if len(text.split()) > 1 else []
            
            # Handle command through wrapper
            result = await self._handler_wrapper.handle_command(command, user_id, args)
            
            # Get response from response service
            messages = self._response_service.get_messages_for_user(user_id)
            if messages:
                last_msg = messages[-1]
                return BotResponse(text=last_msg.get("text", "Command executed"))
            else:
                return BotResponse(text=result or "Command executed")
        
        # Process as regular message
        result = await self._handler_wrapper.handle_message(text, user_id)
        
        # Get response from response service
        messages = self._response_service.get_messages_for_user(user_id)
        if messages:
            last_msg = messages[-1]
            return BotResponse(text=last_msg.get("text", "Message processed"))
        else:
            return BotResponse(text=result or "Message processed")
    
    async def run_interactive(self) -> None:
        """Run interactive CLI loop."""
        await self.start()
        
        try:
            while True:
                try:
                    user_input = input("\nYou: ").strip()
                    
                    if not user_input:
                        continue
                    
                    if user_input.lower() in ('exit', 'quit', 'q'):
                        break
                    
                    if user_input == '/help':
                        print("\nAvailable commands:")
                        commands = ["start", "me", "promises", "nightly", "morning", "weekly", 
                                   "zana", "pomodoro", "settimezone", "language", "version", "broadcast"]
                        for cmd in commands:
                            print(f"  /{cmd}")
                        continue
                    
                    # Clear previous messages to get fresh response
                    if hasattr(self._response_service, 'clear'):
                        # Don't clear - we want to see all messages
                        pass
                    
                    # Process input
                    response = await self.process_input(user_input)
                    
                    # Get response from response service (handlers send responses there)
                    messages = self._response_service.get_messages_for_user(self._user_id)
                    
                    if messages:
                        # Show the last message(s) sent
                        # Show up to last 3 messages in case multiple were sent
                        recent_messages = messages[-3:]
                        for msg in recent_messages:
                            text = msg.get('text', '')
                            if text and text.strip():
                                print(f"\nBot: {text}")
                        if response and response.keyboard:
                            print(f"[Keyboard with {len(response.keyboard.buttons)} rows]")
                    elif response and response.text:
                        print(f"\nBot: {response.text}")
                    else:
                        print("\nBot: (processing...)")
                
                except KeyboardInterrupt:
                    break
                except EOFError:
                    break
                except Exception as e:
                    print(f"\nError: {e}")
                    logger.error(f"CLI error: {e}", exc_info=True)
                    import traceback
                    traceback.print_exc()
        
        finally:
            await self.stop()

