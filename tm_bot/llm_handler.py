import os
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

# Define the schemas list
schemas = [LLMResponse] # , UserPromise, UserAction]
api_schema = [PlannerAPI.add_promise, PlannerAPI.add_action, PlannerAPI.get_promises, PlannerAPI.get_actions,
              PlannerAPI.update_setting, PlannerAPI.delete_promise, PlannerAPI.add_action]

class LLMHandler:
    def __init__(self):
        # Retrieve OpenAI API key from environment variables
        self.openai_key = os.getenv("OPENAI_API_KEY")
        if not self.openai_key:
            raise ValueError("OpenAI API key is not set in environment variables.")

        # Initialize the structured output parser with the defined schemas
        # self.parser = StructuredOutputParser.from_response_schemas([LLMResponse])
        self.parser = JsonOutputParser(pydantic_object=LLMResponse)

        # Initialize the ChatOpenAI model with the correct model name
        self.chat_model = ChatOpenAI(
            openai_api_key=self.openai_key,
            temperature=0.7,
            model="gpt-4o-mini"  # Specify the model
        )

        # Initialize chat history storage
        self.chat_history = {}

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

        system_message = SystemMessage(content=(
            "You are an assistant for a task management bot. "
            "When responding, return a JSON object referencing the action and any relevant fields."
            "Here are the base models for the schemas:\n" + base_model_schemas + "\n"
            f"Here are the API functions available:\n [{api_schema_str}]"
        ))

        self.chat_history[user_id] = ChatMessageHistory()
        self.chat_history[user_id].add_message(system_message)

    def get_response(self, user_message: str, user_id: str) -> str:
        if user_id not in self.chat_history:
            self._initialize_context(user_id)

        try:
            # Add the user's message to the chat history
            self.chat_history[user_id].add_message(HumanMessage(content=user_message))

            # Get the AI's response
            response = self.chat_model(self.chat_history[user_id].messages)

            # Add the AI's response to the chat history
            self.chat_history[user_id].add_message(AIMessage(content=response.content))

            # Parse the AI's response using the structured output parser
            parsed_response = self.parser.parse(response.content)

            return parsed_response
        except Exception as e:
            return f"An error occurred: {str(e)}"


# Example usage
if __name__ == "__main__":
    handler = LLMHandler()
    user_id = "user123"
    user_message = "I want to add a new promise to exercise regularly."
    response = handler.get_response(user_message, user_id)
    print(response)
