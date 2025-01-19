import os
from dotenv import load_dotenv
from telegram import Bot
import asyncio
import logging

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def test_bot_connection():
    """Test the Telegram bot connection and basic functionality."""
    try:
        # Load environment variables
        load_dotenv()
        bot_token = os.getenv("BOT_TOKEN")
        
        if not bot_token:
            raise ValueError("BOT_TOKEN not found in environment variables")
        
        # Initialize bot
        bot = Bot(token=bot_token)
        
        # Get bot information
        bot_info = await bot.get_me()
        logger.info("Bot Connection Test Results:")
        logger.info(f"✓ Successfully connected to bot: @{bot_info.username}")
        logger.info(f"✓ Bot ID: {bot_info.id}")
        logger.info(f"✓ Bot Name: {bot_info.first_name}")
        
        # Test if bot can access environment
        root_dir = os.getenv("ROOT_DIR")
        if root_dir:
            logger.info(f"✓ ROOT_DIR is set to: {root_dir}")
        else:
            logger.warning("⚠ ROOT_DIR environment variable not found")
            
        return True

    except Exception as e:
        logger.error(f"❌ Error testing bot connection: {str(e)}")
        return False
    
if __name__ == "__main__":
    asyncio.run(test_bot_connection()) 