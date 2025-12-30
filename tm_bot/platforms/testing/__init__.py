"""
Testing adapters for platform abstraction.

These adapters allow testing the bot without requiring actual platform connections
(Telegram, Discord, etc.). They can also be used for CLI interfaces.
"""

from .mock_adapter import MockPlatformAdapter
from .cli_adapter import CLIPlatformAdapter
from .test_response_service import TestResponseService

__all__ = [
    "MockPlatformAdapter",
    "CLIPlatformAdapter",
    "TestResponseService",
]

