import os
import sys
from pathlib import Path
import logging
from typing import List, Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage, AIMessage
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.output_parsers import JsonOutputParser
from llms.func_utils import get_function_args_info
from llms.schema import UserAction, LLMResponse  # Ensure this path is correct
# load_dotenv()
# sys.path.append(str(Path(__file__).parent.parent))
# sys.path.append(str(Path(__file__).parent.parent.parent))
from services.planner_api_adapter import PlannerAPIAdapter
from langchain_google_vertexai import ChatVertexAI
from llms.llm_env_utils import load_llm_env

logger = logging.getLogger(__name__)

# Define the schemas list
schemas = [LLMResponse]  # , UserPromise, UserAction]


class LLMHandler:
    def __init__(self):
        try:
            cfg = load_llm_env()  # returns dict with project, location, model

            if cfg.get("OPENAI_API_KEY", ""):
                self.chat_model = ChatOpenAI(
                    openai_api_key=cfg["OPENAI_API_KEY"],
                    temperature=0.7,
                    model="gpt-4o-mini"
                )

            elif cfg.get("GCP_PROJECT_ID", ""):
                self.chat_model = ChatVertexAI(
                    model=cfg["GCP_GEMINI_MODEL"],
                    project=cfg["GCP_PROJECT_ID"],
                    location=cfg["GCP_LOCATION"],
                    temperature=0.7,
                )

            self.parser = JsonOutputParser(pydantic_object=LLMResponse)
            
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
        api_schema = [func for func in dir(PlannerAPIAdapter) if
                      callable(getattr(PlannerAPIAdapter, func)) and not func.startswith("_")]

        for api in api_schema:
            # Retrieve the actual function object
            func_obj = getattr(PlannerAPIAdapter, api)
            api_schema_str += f"\t {api}({get_function_args_info(func_obj)}) \n"

        self.system_message_main = SystemMessage(content=(
            "You are an assistant for a task management bot. "
            "When responding, return a JSON object referencing the action and any relevant fields. "
            # "Always respond in English. "
        ))

        self.system_message_api = SystemMessage(content=(
            "The output should be structured as follows: \n"
            "{\n"
            "\t\"function_call\": \"function_name\",\n"
            "\t\"function_args\": {\"arg1\": \"value1\", \"arg2\": \"value2\"},\n"
            "\t\"response_to_user\": \"Response to the user\"\n"
            "}\n"
            "IMPORTANT: Keep JSON keys, function names, and arguments in ENGLISH and NEVER translate them. "
            "Only the 'response_to_user' text may be localized/adapted to the user’s language and tone.\n"
            f"Here are the list of API functions available:\n [{api_schema_str}]\n"
        ))

        # TODO: Uncomment these lines to enable chat history with system messages
        # self.chat_history[user_id] = ChatMessageHistory()
        # self.chat_history[user_id].add_message(system_message_main)
        # self.chat_history[user_id].add_message(system_message_api)

    def get_response_api(self, user_message: str, user_id: str) -> dict:
        try:
            if user_id not in self.chat_history:
                # TODO: Uncomment to enable per-user context initialization
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
                # Return the raw response content wrapped in the expected format
                return {
                    "function_call": "handle_error", 
                    "response_to_user": response.content
                }

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
                response = self.chat_model(self.chat_history[user_id].messages)
            except Exception as e:
                logger.error(f"Error getting LLM response: {str(e)}")
                return "I'm having trouble understanding that. Could you rephrase?"

            self.chat_history[user_id].add_message(AIMessage(content=response.content))

            try:
                return self.parser.parse(response.content)
            except Exception as e:
                logger.error(f"Error parsing response: {str(e)}")
                # Return the raw response content directly
                return response.content

        except Exception as e:
            logger.error(f"Unexpected error in get_response: {str(e)}")
            return f"Something went wrong. Error: {str(e)}"

    def translate_with_style(
            self,
            text: str,
            target_lang: str,
            user_id: str = "-1",
            intimacy_level: int = 5,
            examples: Optional[List[str]] = None
    ) -> str:
        """
        LLM-based tone-aware translation.
        - 'intimacy_level' controls tone (1–5). Defaults to 5 so existing calls keep working.
        - 'examples' (optional) lets you pass few-shot style examples at call time.
        Preserves placeholders like {hours}, {date}, #{promise_id}; instructs model not to translate JSON/code.
        """
        try:
            if user_id not in self.chat_history:
                self.chat_history[user_id] = ChatMessageHistory()

            ex_block = ""
            if examples:
                # Join examples verbatim; keep this tiny to avoid refactors.
                ex_block = "\n[EXAMPLES]\n" + "\n".join(examples)

            style_sys = SystemMessage(content=(
                                                  "[STYLE_TRANSLATION]\n"
                                                  f"TARGET_LANG: {target_lang}\n"
                                                  f"INTIMACY_LEVEL: {intimacy_level}\n"
                                                  "Rules:\n"
                                                  "- Preserve placeholders exactly: {like_this}, #{promise_id}.\n"
                                                  "- Do NOT translate or alter JSON objects, code blocks, or function names.\n"
                                                  "- Adjust tone to the given INTIMACY_LEVEL while keeping the same intent.\n"
                                                  "- Return ONLY the adapted text (no extra commentary).\n"
                                              ) + ex_block)

            human = HumanMessage(content=f"<<TEXT_START>>\n{text}\n<<TEXT_END>>")

            response = self.chat_model([style_sys] + self.chat_history[user_id].messages + [human])

            self.chat_history[user_id].add_message(
                HumanMessage(content=f"[i18n to {target_lang} L{intimacy_level}] {text}"))
            self.chat_history[user_id].add_message(AIMessage(content=response.content))

            return response.content.strip()
        except Exception as e:
            logger.error(f"translate_with_style failed: {e}")
            return text


# Example usage
if __name__ == "__main__":
    _handler = LLMHandler()
    _user_id = "user123"
    _user_message = "I want to add a new promise to exercise regularly."
    _response = _handler.get_response_api(_user_message, _user_id)
    print(_response)
