import os
import csv
from urllib.parse import uses_relative

import yaml
import logging

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
from planner_api import PlannerAPI  # Import the PlannerAPI class


# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class PlannerAPIBot:
    def __init__(self, token: str):
        request = HTTPXRequest(connect_timeout=10, read_timeout=20)
        self.application = Application.builder().token(token).build()
        self.llm_handler = LLMHandler()  # Instantiate the LLM handler
        self.plan_keeper = PlannerAPI(ROOT_DIR)  # Instantiate the PlannerAPI class

        # Register handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    async def start(self, update: Update, _context: CallbackContext) -> None:
        """Send a message when the command /start is issued."""
        user_id = update.effective_user.id
        created = self.create_user_directory(user_id)
        if created:
            await update.message.reply_text('Hi! Welcome to plan keeper. Your user directory has been created.')
        else:
            await update.message.reply_text('Hi! Welcome back.')

    async def handle_message(self, update: Update, _context: CallbackContext) -> None:
        user_message = update.message.text
        user_id = update.effective_user.id
        # logger.info(f"Received message: {user_message}")
        
        # Get the response from the LLM
        llm_response = self.llm_handler.get_response(user_message, user_id)
        # response = self.plan_keeper.process_message(user_message)

        # Process the LLM response

        func_call_response = self.call_planner_api(user_id, llm_response)
        # Process list/dict responses for better readability
        if isinstance(func_call_response, (list, dict)):
            if isinstance(func_call_response, list):
                # Format list items with newlines and bullet points
                formatted_response = "\n• " + "\n• ".join(str(item) for item in func_call_response)
                func_call_response = formatted_response
            elif isinstance(func_call_response, dict):
                # Format dictionary items with newlines and key-value pairs
                formatted_response = "\n".join(f"{key}: {value}" for key, value in func_call_response.items())
                func_call_response = formatted_response
        logger.info(f"func_call_response: {func_call_response}")
        # Format the LLM response as code block for better readability in Telegram
        formatted_llm = f"*LLM Response:*\n`{llm_response}`"
        
        # Format the function response with proper line breaks and markdown
        formatted_func = f"\n\n*Result:*\n{func_call_response}"
        
        # Send formatted message using Telegram's markdown parsing
        await update.message.reply_text(
            formatted_llm + formatted_func,
            parse_mode='Markdown'
        )

    def call_planner_api(self, user_id, llm_response: str) -> str:
        """
        Process user message by sending it to the LLM and executing the identified action.
        """
        try:
            # Interpret LLM response (you'll need to customize this to match your LLM's output format)
            # Get the function name and arguments from the LLM response
            function_name = llm_response.get("function_call")
            func_args = llm_response.get("function_args", {})

            # Add user_id to function arguments
            func_args["user_id"] = user_id

            # Get the corresponding method from plan_keeper
            if hasattr(self.plan_keeper, function_name):
                method = getattr(self.plan_keeper, function_name)
                # Call the method with unpacked arguments
                return method(**func_args)
            else:
                return f"Function {function_name} not found in PlannerAPI"
        except Exception as e:
            return f"Error executing function: {str(e)}"
        return None

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
    ROOT_DIR = os.getenv("ROOT_DIR")
    load_dotenv()
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    bot = PlannerAPIBot(BOT_TOKEN)
    bot.run()
