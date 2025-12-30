"""
Example tests for the platform-independent bot.

These examples show how to test the bot using mock and CLI adapters.
"""

import asyncio
import os
import tempfile
from datetime import datetime

from platforms.testing import MockPlatformAdapter, CLIPlatformAdapter, TestResponseService
from platforms.types import UserMessage, MessageType
from tm_bot.planner_bot import PlannerBot
from utils.logger import get_logger

logger = get_logger(__name__)


async def test_mock_adapter_basic():
    """Basic test using MockPlatformAdapter."""
    # Create temporary directory for test data
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create mock adapter
        mock_adapter = MockPlatformAdapter()
        
        # Create bot with mock adapter
        bot = PlannerBot(mock_adapter, root_dir=tmpdir)
        
        # Get response service to check outputs
        response_service = mock_adapter.response_service
        
        # Simulate a user message
        message = UserMessage(
            user_id=123,
            chat_id=123,
            text="/start",
            message_type=MessageType.COMMAND,
            timestamp=datetime.now()
        )
        
        # Note: In a real test, you would call the handler directly
        # For now, this shows the structure
        print("Mock adapter test setup complete")
        print(f"Response service type: {type(response_service)}")
        
        # Check that response service is ready
        assert response_service is not None
        print("✓ Mock adapter test passed")


async def test_cli_adapter_interactive():
    """Test CLI adapter in interactive mode."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cli_adapter = CLIPlatformAdapter(user_id=1)
        bot = PlannerBot(cli_adapter, root_dir=tmpdir)
        
        # Test processing a single message
        response = await cli_adapter.process_input("/start", user_id=1)
        
        if response:
            print(f"Bot response: {response.text}")
        else:
            print("No response (command may need handler registration)")
        
        print("✓ CLI adapter test passed")


async def test_response_service_capture():
    """Test that TestResponseService captures responses correctly."""
    response_service = TestResponseService()
    
    # Simulate sending messages
    await response_service.send_text(
        user_id=123,
        chat_id=123,
        text="Hello, this is a test message"
    )
    
    await response_service.send_text(
        user_id=123,
        chat_id=123,
        text="This is another message"
    )
    
    # Check captured messages
    messages = response_service.get_messages_for_user(123)
    assert len(messages) == 2
    assert messages[0]["text"] == "Hello, this is a test message"
    assert messages[1]["text"] == "This is another message"
    
    # Check last message
    last = response_service.get_last_message()
    assert last["text"] == "This is another message"
    
    print("✓ Response service capture test passed")


async def test_job_scheduler():
    """Test that job scheduler works with mock adapter."""
    mock_adapter = MockPlatformAdapter()
    scheduler = mock_adapter.job_scheduler
    
    # Schedule a daily job
    def test_callback(context):
        print(f"Job executed with data: {context.data}")
    
    scheduler.schedule_daily(
        user_id=123,
        tz="UTC",
        callback=test_callback,
        hh=10,
        mm=30,
        name_prefix="test"
    )
    
    # Check that job was scheduled
    job = scheduler.get_job("test-123")
    assert job is not None
    assert job.daily_time.hour == 10
    assert job.daily_time.minute == 30
    
    # Execute the job manually
    await scheduler.execute_job("test-123")
    
    executed = scheduler.get_executed_jobs()
    assert len(executed) == 1
    assert executed[0]["name"] == "test-123"
    
    print("✓ Job scheduler test passed")


async def run_all_tests():
    """Run all example tests."""
    print("=" * 60)
    print("Running Platform-Independent Bot Tests")
    print("=" * 60)
    
    try:
        await test_mock_adapter_basic()
        await test_response_service_capture()
        await test_job_scheduler()
        # CLI test is interactive, skip in automated tests
        # await test_cli_adapter_interactive()
        
        print("\n" + "=" * 60)
        print("All tests passed! ✓")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


async def run_scenario_tests():
    """Run comprehensive scenario tests."""
    print("\n" + "=" * 60)
    print("Running Scenario Tests")
    print("=" * 60)
    print("\nFor comprehensive scenario testing, run:")
    print("  python -m tm_bot.platforms.testing.scenario_tests")
    print("\nOr run a specific scenario:")
    print("  python -m tm_bot.platforms.testing.scenario_tests <scenario_name>")
    print("\nSee README_SCENARIOS.md for more information.")


if __name__ == "__main__":
    asyncio.run(run_all_tests())

