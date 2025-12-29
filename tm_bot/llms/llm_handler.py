from __future__ import annotations

import os
from contextlib import nullcontext
from datetime import datetime
from typing import Callable, Dict, List, Optional

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
from llms.tool_wrappers import _current_user_id, _sanitize_user_id, _wrap_tool
from services.planner_api_adapter import PlannerAPIAdapter
from utils.logger import get_logger

# LangSmith tracing support
try:
    from langsmith import traceable
    from langchain_core.tracers.context import tracing_v2_enabled
    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False
    traceable = lambda **kwargs: lambda f: f  # no-op decorator
    tracing_v2_enabled = nullcontext

logger = get_logger(__name__)
_DEBUG_ENABLED = os.getenv("LLM_DEBUG", "0") == "1" or os.getenv("ENV", "").lower() == "staging"

# Generic, user-safe LLM failure message (avoid leaking provider internals).
_LLM_USER_FACING_ERROR = "I'm having trouble right now. Please try again in a moment."

# Define the schemas list
schemas = [LLMResponse]  # , UserPromise, UserAction]


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
            
            # Store LangSmith config for tracing
            self._langsmith_enabled = cfg.get("LANGSMITH_ENABLED", False)
            self._langsmith_project = cfg.get("LANGSMITH_PROJECT")
            
            logger.info(
                {
                    "event": "llm_handler_init",
                    "model": getattr(self.chat_model, "model_name", None) or getattr(self.chat_model, "model", None),
                    "adapter_root": adapter_root,
                    "max_iterations": self.max_iterations,
                    "debug": _DEBUG_ENABLED,
                    "langsmith_enabled": self._langsmith_enabled,
                    "langsmith_project": self._langsmith_project,
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
            "You are Zana, a friendly and proactive task management assistant. "
            "Help users track their promises (goals) and log time spent on them. "
            "Be encouraging, concise, and action-oriented. "
            "When users mention activities, assume they want to log time unless they clearly ask something else. "
            "Use emojis sparingly (✅ for success, 🔥 for streaks, 📊 for reports). "
            "If the user is just chatting, respond warmly without using tools."
        )

        self.system_message_api = SystemMessage(
            content=(
                "AVAILABLE TOOLS (use only when needed):\n"
                f"{tools_overview}\n\n"
                "TOOL USAGE GUIDELINES:\n"
                "- Use exact argument names from signatures above.\n"
                "- When promise_id is unknown but user mentions a topic, use search_promises first.\n"
                "- Default time_spent to 1.0 hour if user says 'worked on X' without specifying duration.\n"
                "- Prefer action over asking: make reasonable assumptions from context."
            )
        )

        # Planner prompt: must output a structured plan JSON (no chain-of-thought).
        self.system_message_planner_prompt = (
            "You are the PLANNER for a task management assistant.\n"
            "Your job: produce a short, high-level plan (NOT chain-of-thought) that the executor can follow.\n\n"
            
            "CORE PRINCIPLES:\n"
            "1. BE PROACTIVE: Make reasonable assumptions rather than asking. Users prefer action over questions.\n"
            "2. INFER CONTEXT: Use search_promises to find promise IDs when the user mentions a topic by name.\n"
            "3. USE DEFAULTS: When time_spent is not specified, default to 1.0 hour.\n"
            "4. RESOLVE AMBIGUITY: If a promise name is mentioned (e.g., 'sport', 'reading'), search for it first.\n\n"
            
            "RULES:\n"
            "- Output ONLY valid JSON.\n"
            "- Do NOT call tools directly; just plan which tools to call.\n"
            "- Keep 'purpose' short and user-safe (no internal reasoning).\n"
            "- Prefer tool steps over asking the user when data can be obtained from tools.\n"
            "- Never ask for things that are tool-accessible (timezone, language, settings, promise lists).\n"
            "- Ask the user ONLY when truly blocked (e.g., completely ambiguous request with no context).\n"
            "- If you must ask, ask ONCE and request ALL missing fields together.\n"
            "- Keep plans short (1-4 steps; never more than 6).\n"
            "- After mutation tools (add/update/delete/log), add a verify step, then respond.\n"
            "- For casual chat, set final_response_if_no_tools and return empty steps.\n\n"
            
            "SMART DEFAULTS & INFERENCE:\n"
            "- 'log time on X' / 'worked on X' without duration → time_spent=1.0\n"
            "- 'log 2 hours on sport' → search_promises('sport'), then add_action with found ID\n"
            "- 'delete my reading promise' → search_promises('reading'), then delete with found ID\n"
            "- 'how am I doing?' → get_weekly_report()\n"
            "- 'my promises' / 'show tasks' → get_promises()\n\n"
            
            "EXAMPLES:\n\n"
            
            "User: 'I just did 2 hours of sport'\n"
            "Plan: {\"steps\": [\n"
            "  {\"kind\": \"tool\", \"purpose\": \"Find sport promise\", \"tool_name\": \"search_promises\", \"tool_args\": {\"query\": \"sport\"}},\n"
            "  {\"kind\": \"tool\", \"purpose\": \"Log the time\", \"tool_name\": \"add_action\", \"tool_args\": {\"promise_id\": \"FROM_SEARCH\", \"time_spent\": 2.0}},\n"
            "  {\"kind\": \"tool\", \"purpose\": \"Verify action\", \"tool_name\": \"get_last_action_on_promise\", \"tool_args\": {\"promise_id\": \"FROM_SEARCH\"}},\n"
            "  {\"kind\": \"respond\", \"purpose\": \"Confirm to user\", \"response_hint\": \"Confirm time logged, show streak if relevant\"}\n"
            "]}\n\n"
            
            "User: 'worked on reading'\n"
            "Plan: {\"steps\": [\n"
            "  {\"kind\": \"tool\", \"purpose\": \"Find reading promise\", \"tool_name\": \"search_promises\", \"tool_args\": {\"query\": \"reading\"}},\n"
            "  {\"kind\": \"tool\", \"purpose\": \"Log 1 hour (default)\", \"tool_name\": \"add_action\", \"tool_args\": {\"promise_id\": \"FROM_SEARCH\", \"time_spent\": 1.0}},\n"
            "  {\"kind\": \"respond\", \"purpose\": \"Confirm\", \"response_hint\": \"Confirm 1 hour logged\"}\n"
            "]}\n\n"
            
            "User: 'how is my progress?'\n"
            "Plan: {\"steps\": [\n"
            "  {\"kind\": \"tool\", \"purpose\": \"Get weekly summary\", \"tool_name\": \"get_weekly_report\", \"tool_args\": {}},\n"
            "  {\"kind\": \"respond\", \"purpose\": \"Present progress\", \"response_hint\": \"Summarize progress encouragingly\"}\n"
            "]}\n\n"
            
            "User: 'hi there!'\n"
            "Plan: {\"steps\": [], \"final_response_if_no_tools\": \"Hello! How can I help you with your tasks today?\"}\n\n"
            
            "JSON SCHEMA:\n"
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
            # Guard: never send empty prompts to providers.
            user_message = "" if user_message is None else str(user_message)
            if not user_message.strip():
                return {
                    "error": "empty_message",
                    "function_call": "no_op",
                    "response_to_user": "Please type a message (it looks like it was empty).",
                }

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
                # Wrap with LangSmith tracing if enabled
                if self._langsmith_enabled and LANGSMITH_AVAILABLE:
                    with tracing_v2_enabled(
                        project_name=self._langsmith_project,
                        tags=[f"user:{safe_user_id}", f"lang:{user_language or 'en'}"],
                        metadata={
                            "user_id": safe_user_id,
                            "user_language": user_language or "en",
                            "message_preview": user_message[:100],
                            "history_turns": len(prior_history),
                        },
                    ):
                        result_state = self.agent_app.invoke(state)
                else:
                    result_state = self.agent_app.invoke(state)
            finally:
                _current_user_id.reset(token)
            final_messages = result_state.get("messages", messages)
            final_response = result_state.get("final_response")
            pending_clarification = result_state.get("pending_clarification")

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
                "pending_clarification": pending_clarification,
            }
        except Exception as e:
            # Do not leak raw provider errors (Vertex/Gemini often includes request/payload details).
            # Log full details for debugging, but return a user-safe message.
            logger.exception("Unexpected error in get_response_api")
            return {
                "error": "llm_error",
                "function_call": "handle_error",
                "response_to_user": _LLM_USER_FACING_ERROR,
                "executed_by_agent": True,  # Prevent legacy path from re-executing
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
            user_message = "" if user_message is None else str(user_message)
            if not user_message.strip():
                return "Please type a message (it looks like it was empty)."

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
                logger.exception("Error getting LLM response")
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
            logger.exception("Unexpected error in get_response_custom")
            return _LLM_USER_FACING_ERROR

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
                    func=_wrap_tool(candidate, attr_name, debug_enabled=_DEBUG_ENABLED),
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
