import os
import logging
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage, AIMessage
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.output_parsers import JsonOutputParser
from func_utils import get_function_args_info
from schema import UserPromise, UserAction, LLMResponse  # Ensure this path is correct
from planner_api import PlannerAPI
# Load environment variables
# load_dotenv()

logger = logging.getLogger(__name__)

# Define the schemas list
schemas = [LLMResponse] # , UserPromise, UserAction]


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

            self._initialize_context(user_id="-1")  # reserved
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
        api_schema = [func for func in dir(PlannerAPI) if
                      callable(getattr(PlannerAPI, func)) and not func.startswith("_")]

        for api in api_schema:
            # Retrieve the actual function object
            func_obj = getattr(PlannerAPI, api)
            api_schema_str += f"\t {api}({get_function_args_info(func_obj)}) \n"

        self.system_message_main = SystemMessage(content=(
            "You are an assistant for a task management bot. "
            "When responding, return a JSON object referencing the action and any relevant fields. "
            "Always respond in English. "
        ))

        self.system_message_api = SystemMessage(content=(
            "The output should be structured as follows: \n"
            "{\n"
            "\t\"function_call\": \"function_name\",\n"
            "\t\"function_args\": {\"arg1\": \"value1\", \"arg2\": \"value2\"},\n"
            "\t\"response_to_user\": \"Response to the user\"\n"
            "}\n"
            f"Here are the list of API functions available:\n [{api_schema_str}]\n"
        ))

        # self.chat_history[user_id] = ChatMessageHistory()
        # self.chat_history[user_id].add_message(system_message_main)
        # self.chat_history[user_id].add_message(system_message_api)

    def get_response_api(self, user_message: str, user_id: str) -> dict:
        try:
            if user_id not in self.chat_history:
                # self._initialize_context(user_id)
                self.chat_history[user_id] = ChatMessageHistory()

            self.chat_history[user_id].add_message(HumanMessage(content=user_message))

            try:
                response = self.chat_model([self.system_message_main, self.system_message_api] + self.chat_history[user_id].messages)
            except Exception as e:
                logger.error(f"Error getting LLM response: {str(e)}")
                return {"error": "model_error", "function_call": "handle_error", 
                        "response_to_user": "I'm having trouble understanding that. Could you rephrase?"}

            self.chat_history[user_id].add_message(AIMessage(content=response.content))

            try:
                return self.parser.parse(response.content)
            except Exception as e:
                logger.error(f"Error parsing response: {str(e)}")
                return {"error": "parsing_error", "function_call": "handle_error", 
                        "response_to_user": f"LLM Error: {str(e)}"}

        except Exception as e:
            logger.error(f"Unexpected error in get_response: {str(e)}")
            return {"error": "unexpected_error", "function_call": "handle_error", 
                    "response_to_user": f"Something went wrong. Error: {str(e)}"}

    def get_response_custom(self, user_message: str, user_id: str) -> str:
        try:
            if user_id not in self.chat_history:
                self.chat_history[user_id] = ChatMessageHistory()

            self.chat_history[user_id].add_message(HumanMessage(content=user_message))

            try:
                response = self.chat_model([self.system_message_main] + self.chat_history[user_id].messages)
            except Exception as e:
                logger.error(f"Error getting LLM response: {str(e)}")
                return "I'm having trouble understanding that. Could you rephrase?"

            self.chat_history[user_id].add_message(AIMessage(content=response.content))

            try:
                return self.parser.parse(response.content)
            except Exception as e:
                logger.error(f"Error parsing response: {str(e)}")
                return f"LLM Error: {str(e)}"

        except Exception as e:
            logger.error(f"Unexpected error in get_response: {str(e)}")
            return f"Something went wrong. Error: {str(e)}"

# Example usage
if __name__ == "__main__":
    _handler = LLMHandler()
    _user_id = "user123"
    _user_message = "I want to add a new promise to exercise regularly."
    _response = _handler.get_response_api(_user_message, _user_id)
    print(_response)
