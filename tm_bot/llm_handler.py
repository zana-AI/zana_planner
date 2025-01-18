import os
from langchain.chat_models import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage, AIMessage
from langchain.memory import ChatMessageHistory
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class LLMHandler:
    def __init__(self):
        # Fetch the OpenAI API key from environment variables
        self.openai_key = os.getenv("OPENAI_API_KEY")
        if not self.openai_key:
            raise ValueError("OpenAI API key is not set in environment variables.")
        
        # Initialize the LangChain OpenAI Chat Model
        self.chat_model = ChatOpenAI(
            openai_api_key=self.openai_key,
            temperature=0.7,  # Adjust based on your use case
            model="gpt-4o-mini"  # Specify the model
        )
        print("LLMHandler initialized successfully")
        
        # Initialize chat history for the user        
        self.chat_history = {} # ChatMessageHistory()

    def _initialize_context(self, user_id: str) -> None:
        """Send initial context to the LLM."""
        system_message = SystemMessage(content=(
            "You are an assistant for a task management bot. "
            "The bot manages promises, actions, and settings for the user. "
            "Here are the functions the bot can execute:\n"
            "1. `add_promise`: Add a promise with the following fields:\n"
            "   - promise_text: The text of the promise.\n"
            "   - promise_id: A unique 12-character ID derived from the promise text.\n"
            "   - num_hours_promised_per_week: The number of hours promised per week.\n"
            "   - start_date: The start date of the promise (YYYY-MM-DD).\n"
            "   - end_date: The end date of the promise (YYYY-MM-DD).\n"
            "   - promise_angle: A value between 0 and 360 representing an angle.\n"
            "   - promise_radius: A value between 1 and 100 representing the radius in years.\n"
            "2. `add_action`: Log an action with the following fields:\n"
            "   - date: The date of the action (YYYY-MM-DD).\n"
            "   - time: The time of the action (HH:MM).\n"
            "   - promise_id: The ID of the promise the action relates to.\n"
            "   - time_spent: The time spent in hours.\n"
            "3. `update_setting`: Update a setting with the following fields:\n"
            "   - setting_key: The key of the setting to update.\n"
            "   - setting_value: The new value for the setting.\n"
            "When responding, return a JSON object specifying the action and required fields. "
            "If you cannot determine the action, ask the user for clarification."
        ))
        self.chat_history[user_id] = ChatMessageHistory()

    def get_response(self, user_message: str, user_id: str) -> str:
        """
        Sends a message to the LLM and retrieves the response.
        """

        # check if the chat history is empty
        if user_id not in self.chat_history:
            self._initialize_context(user_id)

        try:
            # Add the user's message to the chat history
            self.chat_history[user_id].add_message(HumanMessage(content=user_message))
            
            # Send the chat history to the LLM and get a response
            response = self.chat_model(self.chat_history[user_id].messages)
            
            # Add the LLM's response to the chat history
            self.chat_history[user_id].add_message(AIMessage(content=response.content))
            
            return response.content
        except Exception as e:
            return f"An error occurred while processing your request: {e}"
