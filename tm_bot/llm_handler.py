import os
import logging
from dotenv import load_dotenv
from langchain.chat_models import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage, AIMessage
from langchain.memory import ChatMessageHistory
from langchain.output_parsers import StructuredOutputParser, ResponseSchema
from langchain_core.output_parsers import JsonOutputParser
from func_utils import get_function_args_info
from schema import UserPromise, UserAction, LLMResponse  # Ensure this path is correct
from planner_api import PlannerAPI
# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Define the schemas list
schemas = [LLMResponse] # , UserPromise, UserAction]
api_schema = [PlannerAPI.add_promise, PlannerAPI.add_action, PlannerAPI.get_promises, PlannerAPI.get_actions,
              PlannerAPI.update_setting, PlannerAPI.delete_promise, PlannerAPI.add_action]

class LLMHandler:
    def __init__(self):
        try:
            self.openai_key = os.getenv("OPENAI_API_KEY")
            if not self.openai_key:
                raise ValueError("OpenAI API key is not set in environment variables.")

            self.parser = JsonOutputParser(pydantic_object=LLMResponse)
            
            self.chat_model = ChatOpenAI(
                openai_api_key=self.openai_key,
                temperature=0.7,
                model="gpt-4o-mini"
            )
            
            self.chat_history = {}
        except Exception as e:
            logger.error(f"Failed to initialize LLMHandler: {str(e)}")
            raise

    def _initialize_context(self, user_id: str) -> None:
        base_model_schemas = ""
        for schema in schemas:
            base_model_schemas += f"class {schema.__name__}:\n"
            for field_name, field in schema.model_fields.items():
                base_model_schemas += f"\t{field_name}(description= {field.description}, type= {str(field.annotation)})\n"

        api_schema_str = ""
        for api in api_schema:
            api_schema_str += f"\t{api.__name__}:\n"
            api_schema_str += str(get_function_args_info(api))

        bot_commands = (
            "/nightly - Send nightly reminders about promises\n"
            "/week_report - Generate a weekly report of promises\n"
            "/list_promises - List all promises for the user\n"
        )

        system_message = SystemMessage(content=(
            "You are an assistant for a task management bot. "
            "When responding, return a JSON object referencing the action and any relevant fields. "
            "Always respond in English. "
            # f"Here are the base models for the schemas:\n{base_model_schemas}\n"
            f"Here are the API functions available:\n [{api_schema_str}]\n"
            f"Here are the bot commands:\n{bot_commands}"
        ))

        self.chat_history[user_id] = ChatMessageHistory()
        self.chat_history[user_id].add_message(system_message)

    def get_response(self, user_message: str, user_id: str) -> str:
        try:
            if user_id not in self.chat_history:
                self._initialize_context(user_id)

            # Add the user's message to the chat history
            self.chat_history[user_id].add_message(HumanMessage(content=user_message))

            # Get the AI's response
            try:
                response = self.chat_model(self.chat_history[user_id].messages)
            except Exception as e:
                logger.error(f"Error getting LLM response: {str(e)}")
                return {"error": "model_error", "function_call": "handle_error", 
                        "response_to_user": "I'm having trouble understanding that. Could you rephrase?"}

            # Add the AI's response to the chat history
            self.chat_history[user_id].add_message(AIMessage(content=response.content))

            # Parse the response
            try:
                return self.parser.parse(response.content)
            except Exception as e:
                logger.error(f"Error parsing response: {str(e)}")
                return {"error": "parsing_error", "function_call": "handle_error", 
                        "response_to_user": "I couldn't process that correctly. Please try again."}

        except Exception as e:
            logger.error(f"Unexpected error in get_response: {str(e)}")
            return {"error": "unexpected_error", "function_call": "handle_error", 
                    "response_to_user": "Something went wrong. Please try again later."}


# Example usage
if __name__ == "__main__":
    handler = LLMHandler()
    user_id = "user123"
    user_message = "I want to add a new promise to exercise regularly."
    response = handler.get_response(user_message, user_id)
    print(response)
