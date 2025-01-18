import logging
import os
import csv
import yaml
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    filters,
)
from telegram.request import HTTPXRequest
from llm_handler import LLMHandler  # Import the LLM handler
from plan_keeper import PlanKeeper  # Import the PlanKeeper class


# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

ROOT_DIR = r'C:\Users\Mohamed CHETOUANI\Dropbox\Javad_plan\TEMP_USER_DIR'


class PlanKeeperBot:
    def __init__(self, token: str):
        request = HTTPXRequest(connect_timeout=10, read_timeout=20)
        self.application = Application.builder().token(token).build()
        self.llm_handler = LLMHandler()  # Instantiate the LLM handler
        self.plan_keeper = PlanKeeper(ROOT_DIR)  # Instantiate the PlanKeeper class

        # Register handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    async def start(self, update: Update, context: CallbackContext) -> None:
        """Send a message when the command /start is issued."""
        user_id = update.effective_user.id
        created = self.create_user_directory(user_id)
        if created:
            await update.message.reply_text('Hi! Welcome to plan keeper. Your user directory has been created.')
        else:
            await update.message.reply_text('Hi! Welcome back.')

    async def handle_message(self, update: Update, context: CallbackContext) -> None:
        user_message = update.message.text
        # logger.info(f"Received message: {user_message}")
        
        # Get the response from the LLM
        response = self.llm_handler.get_response(user_message)
        # response = self.plan_keeper.process_message(user_message)

        await update.message.reply_text(response)

    def call_plan_keeper(self, llm_response: str) -> str:
        """
        Process user message by sending it to the LLM and executing the identified action.
        """

        # Interpret LLM response (you'll need to customize this to match your LLM's output format)
        if "add_promise" in llm_response:
            return self.plan_keeper.add_promise(
                promise_text=llm_response["promise_text"],
                num_hours_promised_per_week=llm_response["num_hours_promised_per_week"],
                start_date=llm_response["start_date"],
                end_date=llm_response["end_date"],
                promise_angle=llm_response["promise_angle"],
                promise_radius=llm_response["promise_radius"]
            )
        elif "add_action" in llm_response:
            return self.plan_keeper.add_action(
                date=llm_response["date"],
                time=llm_response["time"],
                promise_id=llm_response["promise_id"],
                time_spent=llm_response["time_spent"]
            )
        elif "update_setting" in llm_response:
            return self.plan_keeper.update_setting(
                setting_key=llm_response["setting_key"],
                setting_value=llm_response["setting_value"]
            )
        else:
            return "I didn't understand your request. Can you rephrase?"

    def create_user_directory(self, user_id: int) -> bool:
        """Create a directory for the user if it doesn't exist and initialize files."""
        user_dir = os.path.join(ROOT_DIR, str(user_id))
        if not os.path.exists(user_dir):
            os.makedirs(user_dir)
            self.initialize_files(user_dir)
            return True
        return False

    def initialize_files(self, user_dir: str) -> None:
        """Initialize the required files in the user's directory."""
        promises_file = os.path.join(user_dir, 'promises.csv')
        actions_file = os.path.join(user_dir, 'actions.csv')
        settings_file = os.path.join(user_dir, 'settings.yaml')

        # Create promises.csv and actions.csv with headers
        for file_path in [promises_file, actions_file]:
            with open(file_path, 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(['id', 'content'])  # Example headers, adjust as needed

        # Create settings.yaml with default settings
        default_settings = {'setting1': 'value1', 'setting2': 'value2'}  # Example settings, adjust as needed
        with open(settings_file, 'w') as file:
            yaml.dump(default_settings, file)

    def run(self):
        """Start the bot."""
        self.application.run_polling()


if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    bot = PlanKeeperBot(BOT_TOKEN)
    bot.run()
