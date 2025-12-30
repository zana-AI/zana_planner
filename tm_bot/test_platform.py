#!/usr/bin/env python3
"""
Quick test script for platform-independent bot.

This script demonstrates how to test the bot without Telegram.
Run: python -m tm_bot.test_platform
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from platforms.testing import MockPlatformAdapter, TestResponseService
from platforms.types import UserMessage, MessageType
from datetime import datetime


async def test_basic_functionality():
    """Test basic bot functionality with mock adapter."""
    print("=" * 60)
    print("Testing Platform-Independent Bot")
    print("=" * 60)
    print()
    
    # Create temporary directory for test data
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Using test data directory: {tmpdir}")
        print()
        
        # Create mock adapter
        print("1. Creating mock platform adapter...")
        mock_adapter = MockPlatformAdapter()
        print("   ✓ Mock adapter created")
        print()
        
        # Get response service
        print("2. Checking response service...")
        response_service = mock_adapter.response_service
        assert isinstance(response_service, TestResponseService)
        print("   ✓ Response service is TestResponseService")
        print()
        
        # Test sending a message
        print("3. Testing message sending...")
        await response_service.send_text(
            user_id=123,
            chat_id=123,
            text="Hello from test!"
        )
        
        messages = response_service.get_messages_for_user(123)
        assert len(messages) == 1
        assert messages[0]["text"] == "Hello from test!"
        print(f"   ✓ Message sent and captured: '{messages[0]['text']}'")
        print()
        
        # Test job scheduler
        print("4. Testing job scheduler...")
        scheduler = mock_adapter.job_scheduler
        
        job_executed = []
        def test_callback(context):
            job_executed.append(True)
            print(f"   → Job executed! Data: {context.data}")
        
        scheduler.schedule_daily(
            user_id=123,
            tz="UTC",
            callback=test_callback,
            hh=10,
            mm=30,
            name_prefix="test"
        )
        
        job = scheduler.get_job("test-123")
        assert job is not None
        print(f"   ✓ Job scheduled: {job.name} at {job.daily_time}")
        print()
        
        # Execute job manually
        print("5. Executing scheduled job...")
        await scheduler.execute_job("test-123")
        assert len(job_executed) == 1
        print("   ✓ Job executed successfully")
        print()
        
        # Test user info
        print("6. Testing user info...")
        user_info = mock_adapter.get_user_info(123)
        assert user_info["user_id"] == 123
        assert user_info["platform"] == "mock"
        print(f"   ✓ User info retrieved: {user_info}")
        print()
        
        print("=" * 60)
        print("All tests passed! ✓")
        print("=" * 60)
        print()
        print("Next steps:")
        print("  - Run CLI test: python -m tm_bot.platforms.testing.cli_test")
        print("  - Run unit tests: pytest tm_bot/tests/test_platform_abstraction.py")
        print("  - See examples: python -m tm_bot.platforms.testing.test_examples")


if __name__ == "__main__":
    try:
        asyncio.run(test_basic_functionality())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

