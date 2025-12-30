"""
Unit tests for platform abstraction layer.

These tests verify that the platform abstraction works correctly
and can be used for testing without Telegram.
"""

import pytest
import asyncio
import tempfile
from datetime import datetime

from platforms.testing import (
    MockPlatformAdapter,
    CLIPlatformAdapter,
    TestResponseService,
)
from platforms.types import UserMessage, MessageType, BotResponse
from platforms.interfaces import IResponseService, IJobScheduler


class TestMockPlatformAdapter:
    """Test MockPlatformAdapter functionality."""
    
    def test_adapter_creation(self):
        """Test that mock adapter can be created."""
        adapter = MockPlatformAdapter()
        assert adapter is not None
        assert adapter.response_service is not None
        assert adapter.job_scheduler is not None
        assert adapter.keyboard_builder is not None
    
    def test_response_service_interface(self):
        """Test that response service implements IResponseService."""
        adapter = MockPlatformAdapter()
        assert isinstance(adapter.response_service, IResponseService)
    
    def test_job_scheduler_interface(self):
        """Test that job scheduler implements IJobScheduler."""
        adapter = MockPlatformAdapter()
        assert isinstance(adapter.job_scheduler, IJobScheduler)
    
    def test_user_info(self):
        """Test getting user info."""
        adapter = MockPlatformAdapter()
        info = adapter.get_user_info(123)
        assert info["user_id"] == 123
        assert info["platform"] == "mock"
    
    def test_set_user_info(self):
        """Test setting user info."""
        adapter = MockPlatformAdapter()
        adapter.set_user_info(123, {"custom_field": "value"})
        info = adapter.get_user_info(123)
        assert info["custom_field"] == "value"


class TestTestResponseService:
    """Test TestResponseService functionality."""
    
    @pytest.mark.asyncio
    async def test_send_text(self):
        """Test sending text messages."""
        service = TestResponseService()
        
        message = await service.send_text(
            user_id=123,
            chat_id=123,
            text="Test message"
        )
        
        assert message is not None
        assert len(service.sent_messages) == 1
        assert service.sent_messages[0]["text"] == "Test message"
        assert service.sent_messages[0]["user_id"] == 123
    
    @pytest.mark.asyncio
    async def test_send_photo(self):
        """Test sending photos."""
        service = TestResponseService()
        
        message = await service.send_photo(
            user_id=123,
            chat_id=123,
            photo="fake_photo_data",
            caption="Test photo"
        )
        
        assert message is not None
        assert len(service.sent_photos) == 1
        assert service.sent_photos[0]["caption"] == "Test photo"
    
    @pytest.mark.asyncio
    async def test_edit_message(self):
        """Test editing messages."""
        service = TestResponseService()
        
        # First send a message
        await service.send_text(123, 123, "Original")
        
        # Then edit it
        edited = await service.edit_message(
            user_id=123,
            chat_id=123,
            message_id=1,
            text="Edited"
        )
        
        assert edited is not None
        assert len(service.edited_messages) == 1
        assert service.edited_messages[0]["text"] == "Edited"
    
    @pytest.mark.asyncio
    async def test_delete_message(self):
        """Test deleting messages."""
        service = TestResponseService()
        
        result = await service.delete_message(123, 1)
        
        assert result is True
        assert len(service.deleted_messages) == 1
    
    def test_log_user_message(self):
        """Test logging user messages."""
        service = TestResponseService()
        
        service.log_user_message(123, "User said hello", message_id=1, chat_id=123)
        
        assert len(service.logged_messages) == 1
        assert service.logged_messages[0]["content"] == "User said hello"
    
    def test_get_messages_for_user(self):
        """Test getting messages for a specific user."""
        service = TestResponseService()
        
        # Send messages to different users
        asyncio.run(service.send_text(123, 123, "Message 1"))
        asyncio.run(service.send_text(456, 456, "Message 2"))
        asyncio.run(service.send_text(123, 123, "Message 3"))
        
        user_messages = service.get_messages_for_user(123)
        assert len(user_messages) == 2
        assert user_messages[0]["text"] == "Message 1"
        assert user_messages[1]["text"] == "Message 3"
    
    def test_clear(self):
        """Test clearing captured messages."""
        service = TestResponseService()
        
        asyncio.run(service.send_text(123, 123, "Test"))
        assert len(service.sent_messages) == 1
        
        service.clear()
        assert len(service.sent_messages) == 0


class TestMockJobScheduler:
    """Test MockJobScheduler functionality."""
    
    def test_schedule_daily(self):
        """Test scheduling daily jobs."""
        from platforms.testing.mock_scheduler import MockJobScheduler
        
        scheduler = MockJobScheduler()
        
        def callback(context):
            pass
        
        scheduler.schedule_daily(
            user_id=123,
            tz="UTC",
            callback=callback,
            hh=10,
            mm=30,
            name_prefix="test"
        )
        
        job = scheduler.get_job("test-123")
        assert job is not None
        assert job.daily_time.hour == 10
        assert job.daily_time.minute == 30
    
    @pytest.mark.asyncio
    async def test_execute_job(self):
        """Test executing jobs."""
        from platforms.testing.mock_scheduler import MockJobScheduler
        
        scheduler = MockJobScheduler()
        executed = []
        
        def callback(context):
            executed.append(context.data)
        
        scheduler.schedule_once(
            name="test-job",
            callback=callback,
            when_dt=datetime.now(),
            data={"test": "data"}
        )
        
        await scheduler.execute_job("test-job")
        
        assert len(executed) == 1
        assert executed[0]["test"] == "data"
        assert len(scheduler.get_executed_jobs()) == 1


class TestCLIAdapter:
    """Test CLIPlatformAdapter functionality."""
    
    def test_adapter_creation(self):
        """Test that CLI adapter can be created."""
        adapter = CLIPlatformAdapter(user_id=1)
        assert adapter is not None
        assert adapter.response_service is not None
    
    @pytest.mark.asyncio
    async def test_process_input(self):
        """Test processing user input."""
        adapter = CLIPlatformAdapter(user_id=1)
        
        # Process a simple input
        response = await adapter.process_input("Hello", user_id=1)
        
        # Response may be None if no handlers are registered
        # This is expected behavior
        assert response is None or isinstance(response, BotResponse)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

