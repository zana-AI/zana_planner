# Testing Guide for Platform-Independent Bot

This guide explains how to test the bot using the platform abstraction layer.

## Testing Options

### 1. Mock Platform Adapter (Unit Testing)

The `MockPlatformAdapter` allows you to test the bot logic without any external dependencies.

**Features:**
- No Telegram connection required
- Fast execution
- Captures all responses for assertions
- Can simulate user messages

**Example:**

```python
import asyncio
from platforms.testing import MockPlatformAdapter
from tm_bot.planner_bot import PlannerBot

async def test_bot():
    # Create mock adapter
    mock_adapter = MockPlatformAdapter()
    
    # Create bot with mock adapter
    bot = PlannerBot(mock_adapter, root_dir="/tmp/test_data")
    
    # Simulate a user message
    from platforms.types import UserMessage, MessageType
    from datetime import datetime
    
    message = UserMessage(
        user_id=123,
        chat_id=123,
        text="Hello, add a promise to exercise 5 hours per week",
        message_type=MessageType.TEXT,
        timestamp=datetime.now()
    )
    
    # Process message through handlers
    # (This would need to be integrated with the handlers)
    
    # Check responses
    response_service = mock_adapter.response_service
    assert len(response_service.sent_messages) > 0
    print(f"Bot responded: {response_service.get_last_message()['text']}")

if __name__ == "__main__":
    asyncio.run(test_bot())
```

### 2. CLI Platform Adapter (Interactive Testing)

The `CLIPlatformAdapter` allows you to interact with the bot directly from the command line.

**Usage:**

```python
import asyncio
from platforms.testing import CLIPlatformAdapter
from tm_bot.planner_bot import PlannerBot

async def run_cli_bot():
    # Create CLI adapter
    cli_adapter = CLIPlatformAdapter(user_id=1)
    
    # Create bot
    bot = PlannerBot(cli_adapter, root_dir="/tmp/test_data")
    
    # Run interactive CLI
    await cli_adapter.run_interactive()

if __name__ == "__main__":
    asyncio.run(run_cli_bot())
```

Or create a simple script:

```bash
python -m tm_bot.platforms.testing.cli_test
```

### 3. Test Response Service

The `TestResponseService` captures all bot responses for easy assertion:

```python
from platforms.testing import TestResponseService

response_service = TestResponseService()

# After bot processes a message
messages = response_service.get_messages_for_user(user_id=123)
assert len(messages) > 0
assert "promise" in messages[0]["text"].lower()
```

## Creating Test Files

See `test_examples.py` for complete examples.


