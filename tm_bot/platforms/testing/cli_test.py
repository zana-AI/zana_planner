"""
CLI test script for interactive bot testing.

Run this script to interact with the bot directly from the command line
without requiring a Telegram connection.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from platforms.testing import CLIPlatformAdapter
from tm_bot.planner_bot import PlannerBot
from utils.logger import get_logger

logger = get_logger(__name__)


async def main():
    """Run CLI bot interface."""
    # Use a test data directory
    root_dir = os.getenv("ROOT_DIR", "/tmp/zana_test_data")
    os.makedirs(root_dir, exist_ok=True)
    
    print("=" * 60)
    print("Xaana AI Bot - CLI Testing Interface")
    print("=" * 60)
    print(f"Data directory: {root_dir}")
    print()
    
    # Create CLI adapter
    cli_adapter = CLIPlatformAdapter(user_id=1)
    
    # Create bot
    try:
        bot = PlannerBot(cli_adapter, root_dir=root_dir)
        print("Bot initialized successfully!")
        print()
    except Exception as e:
        print(f"Error initializing bot: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Run interactive CLI
    try:
        await cli_adapter.run_interactive()
    except KeyboardInterrupt:
        print("\n\nExiting...")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())


