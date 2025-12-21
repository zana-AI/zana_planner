from __future__ import annotations

import inspect
import os
from datetime import datetime
from typing import Callable, Dict, List, Optional

from contextvars import ContextVar

from langchain.tools import StructuredTool
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_google_vertexai import ChatVertexAI
from langchain_openai import ChatOpenAI

from llms.agent import AgentState, create_plan_execute_graph
from llms.func_utils import get_function_args_info
from llms.llm_env_utils import load_llm_env
from llms.schema import LLMResponse, UserAction
from llms.planning_schema import Plan
from services.planner_api_adapter import PlannerAPIAdapter
from utils.logger import get_logger

logger = get_logger(__name__)
_DEBUG_ENABLED = os.getenv("LLM_DEBUG", "0") == "1" or os.getenv("ENV", "").lower() == "staging"

# Define the schemas list
schemas = [LLMResponse]  # , UserPromise, UserAction]

# Context var to carry the active user_id during tool execution
_current_user_id: ContextVar[Optional[str]] = ContextVar("current_user_id", default=None)


def _sanitize_user_id(user_id: str) -> str:
    """Allow only digit-only user identifiers to avoid cross-user access or path abuse."""
    if user_id is None:
        raise ValueError("user_id is required")
    user_id_str = str(user_id).strip()
    if not user_id_str.isdigit():
        raise ValueError("Invalid user_id")
    return user_id_str


def _wrap_tool(fn: Callable, tool_name: str) -> Callable:
    """Wrap adapter methods to enforce the active user_id and ignore model-provided user_id."""

    def wrapped(**kwargs):
        safe_user_id = _current_user_id.get()
        if not safe_user_id:
            raise ValueError("No active user_id set")
        
        # Strip any user_id provided by the model/tool call
        kwargs.pop("user_id", None)
        
        # Remove 'kwargs' if it was incorrectly passed as a keyword argument
        # This prevents errors like "got an unexpected keyword argument 'kwargs'"
        if "kwargs" in kwargs:
            logger.warning(f"Tool {tool_name} received 'kwargs' as a keyword argument, removing it")
            kwargs.pop("kwargs", None)
        
        # Validate parameters against function signature
        try:
            sig = inspect.signature(fn)
            valid_params = set(sig.parameters.keys()) - {"self", "user_id"}
            
            # Filter out any parameters that aren't in the function signature
            invalid_params = set(kwargs.keys()) - valid_params
            if invalid_params:
                logger.warning(
                    f"Tool {tool_name} received invalid parameters: {invalid_params}. "
                    f"Valid parameters are: {valid_params}. Removing invalid ones."
                )
                for param in invalid_params:
                    kwargs.pop(param, None)
        except Exception as e:
            # If signature inspection fails, log but continue
            if _DEBUG_ENABLED:
                logger.warning(f"Could not inspect signature for {tool_name}: {e}")
        
        if _DEBUG_ENABLED:
            logger.info(
                {
                    "event": "tool_invoke",
                    "tool": tool_name,
                    "user_id": safe_user_id,
                    "args_keys": list(kwargs.keys()),
                }
            )
        
        try:
            return fn(user_id=safe_user_id, **kwargs)
        except TypeError as e:
            # Provide more helpful error message
            logger.error(
                f"Error calling {tool_name} with parameters {list(kwargs.keys())}: {e}"
            )
            raise

    wrapped.__name__ = tool_name
    wrapped.__doc__ = fn.__doc__
    return wrapped


class LLMHandler:
    def __init__(
        self,
        root_dir: Optional[str] = None,
        max_iterations: Optional[int] = None,
        progress_callback: Optional[Callable[[str, dict], None]] = None,
    ):
        """
        LLM handler orchestrated by LangGraph to allow tool-using loops.

        Args:
            root_dir: Base path for PlannerAPIAdapter. Defaults to ROOT_DIR env or cwd.
            max_iterations: Hard cap on agent iterations. Defaults to LLM_MAX_ITERATIONS env or 6.
            progress_callback: Optional callback(event, payload) for UI-agnostic progress.
        """
        try:
            # Sanitize environment-provided ROOT_DIR early (adapter will still handle paths)
            cfg = load_llm_env()  # returns dict with project, location, model

            self.chat_model = None
            if cfg.get("GCP_PROJECT_ID", ""):
                self.chat_model = ChatVertexAI(
                    model=cfg["GCP_GEMINI_MODEL"],
                    project=cfg["GCP_PROJECT_ID"],
                    location=cfg["GCP_LOCATION"],
                    temperature=0.7,
                )

            if not self.chat_model and cfg.get("OPENAI_API_KEY", ""):
                self.chat_model = ChatOpenAI(
                    openai_api_key=cfg["OPENAI_API_KEY"],
                    temperature=0.7,
                    model="gpt-4o-mini",
                )

            if not self.chat_model:
                raise ValueError("No LLM configured. Provide GCP or OpenAI credentials.")

            self.parser = JsonOutputParser(pydantic_object=LLMResponse)
            self.max_iterations = max_iterations or int(os.getenv("LLM_MAX_ITERATIONS", "6"))
            self.chat_history: Dict[str, List[BaseMessage]] = {}
            self._progress_callback_default = progress_callback
            self._progress_callback: Optional[Callable[[str, dict], None]] = progress_callback

            adapter_root = root_dir or os.getenv("ROOT_DIR") or os.getcwd()
            self.plan_adapter = PlannerAPIAdapter(adapter_root)
            self.tools = self._build_tools(self.plan_adapter)

            self._initialize_context()
            self.planner_parser = JsonOutputParser(pydantic_object=Plan)

            self.agent_app = create_plan_execute_graph(
                tools=self.tools,
                planner_model=self.chat_model,   # no tools bound (planner must not call tools)
                responder_model=self.chat_model, # no tools bound (responder must not call tools)
                planner_prompt=self.system_message_planner_prompt,
                emit_plan=_DEBUG_ENABLED,
                max_iterations=self.max_iterations,
                progress_getter=lambda: self._progress_callback,
            )
            logger.info(
                {
                    "event": "llm_handler_init",
                    "model": getattr(self.chat_model, "model_name", None) or getattr(self.chat_model, "model", None),
                    "adapter_root": adapter_root,
                    "max_iterations": self.max_iterations,
                    "debug": _DEBUG_ENABLED,
                }
            )
        except Exception as e:
            logger.error(f"Failed to initialize LLMHandler: {str(e)}")
            raise

    def _initialize_context(self) -> None:
        """Precompute system prompts and tool descriptions."""
        tool_lines = []
        for tool in self.tools:
            name = getattr(tool, "name", "unknown")
            desc = (getattr(tool, "description", "") or "").strip()
            arg_names = []
            if hasattr(self.plan_adapter, name):
                arg_names = list(get_function_args_info(getattr(self.plan_adapter, name)).keys())
            arg_sig = ", ".join(arg_names)
            tool_lines.append(f"- {name}({arg_sig}) :: {desc}")

        tools_overview = "\n".join(tool_lines)

        self.system_message_main_base = (
            "You are an assistant for a task management bot. "
            "Use the provided tools to inspect, add, or update promises and actions. "
            "If the user is only chatting, respond briefly and do not call tools (use no_op). "
            "Keep responses concise and actionable."
        )

        self.system_message_api = SystemMessage(
            content=(
                "Available planner tools (call only when relevant):\n"
                f"{tools_overview}\n"
                "If required arguments are missing, ask for them briefly before calling tools."
            )
        )

        # Planner prompt: must output a structured plan JSON (no chain-of-thought).
        self.system_message_planner_prompt = (
            "You are the PLANNER for a task management assistant.\n"
            "Your job: produce a short, high-level plan (NOT chain-of-thought) that the executor can follow.\n"
            "Rules:\n"
            "- Output ONLY valid JSON.\n"
            "- Do NOT call tools.\n"
            "- Do NOT include any hidden reasoning; keep 'purpose' short and user-safe.\n"
            "- Prefer using tools to read user settings and action history when needed.\n"
            "- For questions like 'my preferred language', plan to call get_setting(setting_key='language').\n"
            "- For questions like 'how many actions today', plan to call count_actions_today().\n"
            "- If the request can be answered without tools, set final_response_if_no_tools.\n\n"
            "JSON schema (informal):\n"
            "{\n"
            '  "steps": [\n'
            "    {\n"
            '      "kind": "tool" | "respond" | "ask_user",\n'
            '      "purpose": "short reason",\n'
            '      "tool_name": "tool_name_if_kind_tool",\n'
            '      "tool_args": { "arg": "value" },\n'
            '      "question": "question_if_kind_ask_user",\n'
            '      "response_hint": "hint_if_kind_respond"\n'
            "    }\n"
            "  ],\n"
            '  "final_response_if_no_tools": "optional string"\n'
            "}\n"
        )

    def _get_system_message_main(self, user_language: str = None) -> SystemMessage:
        """Get system message with language instruction if provided."""
        # Add current date and time information
        now = datetime.now()
        current_date_str = now.strftime("%A, %B %d, %Y")
        current_time_str = now.strftime("%H:%M")
        
        content = self.system_message_main_base
        content += f"\n\nCurrent date and time: {current_date_str} at {current_time_str}. "
        content += "You have access to the current date and should use it when answering questions about dates, weeks, or time periods. Do not ask the user for the current date - use the date provided above. "
        
        if user_language and user_language != "en":
            # Map language codes to full names
            lang_map = {
                "fa": "Persian (Farsi)",
                "fr": "French",
                "en": "English"
            }
            lang_name = lang_map.get(user_language, "the user's preferred language")
            content += f"Respond in {lang_name} unless the user explicitly uses English. "
        else:
            content += "Respond in English. "
        return SystemMessage(content=content)

    def get_response_api(
        self,
        user_message: str,
        user_id: str,
        user_language: str = None,
        progress_callback: Optional[Callable[[str, dict], None]] = None,
    ) -> dict:
        """
        Main entry for multi-iteration agentic responses.
        Executes planner tools inside the LangGraph loop and returns the final reply.
        """
        # Allow per-call progress callback; fall back to default.
        self._progress_callback = progress_callback or self._progress_callback_default
        if _DEBUG_ENABLED and not self._progress_callback:
            # Debug-only visibility: log high-level plan/steps and tool results (no chain-of-thought).
            def _log_progress(event: str, payload: dict) -> None:
                try:
                    logger.info({"event": f"agent_progress:{event}", **(payload or {})})
                except Exception:
                    pass

            self._progress_callback = _log_progress

        try:
            safe_user_id = _sanitize_user_id(user_id)

            prior_history = self.chat_history.get(safe_user_id, [])

            messages: List[BaseMessage] = [
                self._get_system_message_main(user_language),
                self.system_message_api,
                *prior_history,
                HumanMessage(content=user_message),
            ]
            if _DEBUG_ENABLED:
                logger.info(
                    {
                        "event": "agent_start",
                        "user_id": safe_user_id,
                        "lang": user_language or "en",
                        "history_turns": len(prior_history),
                        "message_preview": user_message[:200],
                    }
                )

            state: AgentState = {
                "messages": messages,
                "iteration": 0,
                "plan": None,
                "step_idx": 0,
                "final_response": None,
                "planner_error": None,
            }
            token = _current_user_id.set(safe_user_id)
            try:
                result_state = self.agent_app.invoke(state)
            finally:
                _current_user_id.reset(token)
            final_messages = result_state.get("messages", messages)
            final_response = result_state.get("final_response")

            final_ai = self._get_last_ai(final_messages)
            last_tool_call = self._get_last_tool_call(final_messages)
            tool_messages = [m for m in final_messages if isinstance(m, ToolMessage)]

            # Update chat history with condensed human/AI turns (excluding system/tool chatter)
            self.chat_history[safe_user_id] = self._condense_history(final_messages)

            stop_reason = (
                "max_iterations"
                if result_state.get("iteration", 0) >= self.max_iterations
                else "completed"
            )
            if final_ai and getattr(final_ai, "tool_calls", None) and stop_reason == "completed":
                stop_reason = "tool_calls_executed"
            if not final_ai:
                stop_reason = "no_final_ai_message"

            self._emit_progress(
                "completed",
                {
                    "stop_reason": stop_reason,
                    "iteration": result_state.get("iteration", 0),
                    "last_tool": last_tool_call.get("name") if last_tool_call else None,
                },
            )
            if _DEBUG_ENABLED:
                logger.info(
                    {
                        "event": "agent_end",
                        "user_id": safe_user_id,
                        "stop_reason": stop_reason,
                        "iteration": result_state.get("iteration", 0),
                        "last_tool": last_tool_call.get("name") if last_tool_call else None,
                        "tool_calls_count": len(getattr(final_ai, "tool_calls", []) or []),
                        "tool_msgs": len(tool_messages),
                        "final_ai_preview": (final_ai.content[:200] if final_ai else None),
                    }
                )

            return {
                "function_call": last_tool_call.get("name") if last_tool_call else "no_op",
                "function_args": last_tool_call.get("args", {}) if last_tool_call else {},
                "response_to_user": (
                    final_response
                    or (final_ai.content if final_ai else None)
                    or "I'm having trouble responding right now."
                ),
                "executed_by_agent": True,
                "tool_calls": getattr(final_ai, "tool_calls", None) or [],
                "tool_outputs": [tm.content for tm in tool_messages],
                "stop_reason": stop_reason,
            }
        except Exception as e:
            logger.error(f"Unexpected error in get_response_api: {str(e)}")
            return {
                "error": "unexpected_error",
                "function_call": "handle_error",
                "response_to_user": f"Something went wrong. Error: {str(e)}",
            }
        finally:
            # Reset per-call progress callback
            self._progress_callback = self._progress_callback_default

    def get_response_custom(self, user_message: str, user_id: str, user_language: str = None) -> str:
        try:
            safe_user_id = _sanitize_user_id(user_id)

            if safe_user_id not in self.chat_history:
                self.chat_history[safe_user_id] = []

            history = self.chat_history[safe_user_id]
            messages: List[BaseMessage] = [HumanMessage(content=user_message)]

            # Add language-aware system message if language is specified
            if user_language and user_language != "en":
                system_msg = self._get_system_message_main(user_language)
                messages = [system_msg] + history + messages
            else:
                messages = history + messages

            try:
                response = self.chat_model(messages)
            except Exception as e:
                logger.error(f"Error getting LLM response: {str(e)}")
                return "I'm having trouble understanding that. Could you rephrase?"

            if isinstance(response, AIMessage):
                content = response.content
            else:
                content = getattr(response, "content", str(response))

            history.extend([messages[-1], AIMessage(content=content)])

            try:
                return self.parser.parse(content)
            except Exception as e:
                logger.error(f"Error parsing response: {str(e)}")
                return content

        except Exception as e:
            logger.error(f"Unexpected error in get_response: {str(e)}")
            return f"Something went wrong. Error: {str(e)}"

    def set_progress_callback(self, callback: Optional[Callable[[str, dict], None]]) -> None:
        """Set a default progress callback for future agent runs."""
        self._progress_callback_default = callback
        self._progress_callback = callback

    def _build_tools(self, adapter: PlannerAPIAdapter):
        """Convert adapter methods into LangChain StructuredTool objects."""
        tools = []
        for attr_name in dir(adapter):
            if attr_name.startswith("_"):
                continue
            candidate = getattr(adapter, attr_name)
            if not callable(candidate):
                continue
            doc = (candidate.__doc__ or "").strip() or f"Planner action {attr_name}"
            try:
                tool = StructuredTool.from_function(
                    func=_wrap_tool(candidate, attr_name),
                    name=attr_name,
                    description=doc,
                )
                tools.append(tool)
            except Exception as e:
                logger.warning(f"Skipping tool {attr_name}: {e}")
        return tools

    def _condense_history(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """Keep a lightweight history of human/AI turns (no system/tool chatter)."""
        condensed = [m for m in messages if isinstance(m, (HumanMessage, AIMessage))]
        # Keep last 12 turns to avoid unbounded growth.
        return condensed[-12:]

    @staticmethod
    def _get_last_ai(messages: List[BaseMessage]) -> Optional[AIMessage]:
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                return msg
        return None

    @staticmethod
    def _get_last_tool_call(messages: List[BaseMessage]) -> Optional[dict]:
        """Return the last tool call dict emitted by the agent, if any."""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                return msg.tool_calls[-1]
        return None

    def _emit_progress(self, event: str, payload: dict) -> None:
        """Best-effort progress emission (UI-agnostic)."""
        cb = self._progress_callback
        if cb:
            try:
                cb(event, payload)
            except Exception:
                # Never let progress callbacks break the agent
                pass


# Example usage
if __name__ == "__main__":
    _handler = LLMHandler()
    _user_id = "user123"
    _user_message = "I want to add a new promise to exercise regularly."
    _response = _handler.get_response_api(_user_message, _user_id)
    print(_response)
