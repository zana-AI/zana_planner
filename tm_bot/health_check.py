import os
import requests
from dotenv import load_dotenv

def check_bot_health():
    """
    Check if the bot is responding to Telegram's getMe API endpoint.
    """
    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN")

    if not bot_token:
        print("❌ BOT_TOKEN not found in environment variables")
        return False

    try:
        response = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=10)
        data = response.json()

        if data["ok"]:
            bot_info = data["result"]
            print("✓ Bot is running")
            print(f"✓ Bot username: @{bot_info['username']}")
            print(f"✓ Bot ID: {bot_info['id']}")
            return True
        print("❌ Bot is not responding correctly")
        return False

    except Exception as e:
        print(f"❌ Error checking bot health: {str(e)}")
        return False

if __name__ == "__main__":
    check_bot_health()