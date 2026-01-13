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
            # Initialize conversation repository for context injection
            from repositories.conversation_repo import ConversationRepository
            self.conversation_repo = ConversationRepository(adapter_root)

            self._initialize_context()
            self.planner_parser = JsonOutputParser(pydantic_object=Plan)

            self.agent_app = create_plan_execute_graph(
                tools=self.tools,
                planner_model=self.chat_model,   # no tools bound (planner must not call tools)
                responder_model=self.chat_model, # no tools bound (responder must not call tools)
                planner_prompt=self.system_message_planner_prompt,
                emit_plan=True,  # Always emit plan for user visibility
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
            "You are Xaana, a friendly and proactive task management assistant. "
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
        # Structured with clear sections for better LLM understanding
        self.system_message_planner_prompt = (
            "=== ROLE ===\n"
            "You are the PLANNER for a task management assistant.\n"
            "Your job: produce a short, high-level plan (NOT chain-of-thought) that the executor can follow.\n\n"
            
            "=== INTENT DETECTION ===\n"
            "Before planning, identify the user's primary intent. Common intents include (but can be otherwise):\n"
            "- LOG_ACTION: User wants to record time spent on an activity/promise (past tense: 'I did X', 'I worked on Y', 'I spent time on Z')\n"
            "- EDIT_ACTION: User wants to modify an existing logged action (wrong duration/date/promise)\n"
            "- DELETE_ACTION: User wants to remove an incorrect action\n"
            "- LIST_ACTIONS / QUERY_ACTIONS: User wants to see their logged actions\n"
            "- CREATE_PROMISE: User wants to add a new goal/promise (PREFER templates over free-form). "
            "IMPORTANT: This includes one-time promises and reminders. "
            "If user says 'I want to X tomorrow/next week/on [date]' or 'I need to X at [time]', "
            "this is CREATE_PROMISE for a one-time commitment, NOT LOG_ACTION. "
            "Temporal phrases like 'tomorrow', 'next week', 'on Friday', 'at 3pm' indicate future commitments/reminders.\n"
            "- EDIT_PROMISE: User wants to modify a promise (rename, change target, category, etc.)\n"
            "- DELETE_PROMISE: User wants to remove a promise\n"
            "- QUERY_PROGRESS: User wants to know progress/status (weekly report, streaks, totals)\n"
            "- PLAN_NEXT / GET_IDEAS: User wants suggestions for what to do next or how to proceed\n"
            "- COACHING / HOW_TO: User wants advice or strategy\n"
            "- SETTINGS: User wants to change preferences (language, timezone, notifications)\n"
            "- CLARIFY / DISAMBIGUATE: User is answering a question you asked (slot-filling)\n"
            "- USER_CORRECTION / MISTAKE: User is correcting their own mistake or flagging an error\n"
            "- NO_OP / CHAT: Casual conversation, no action needed\n\n"
            "Set 'detected_intent' to an open-text label describing the intent.\n"
            "Set 'intent_confidence' to 'high', 'medium', or 'low' based on how clear the intent is.\n"
            "Set 'safety.requires_confirmation' to true if:\n"
            "  - The plan includes a mutation tool (add_*, create_*, update_*, delete_*, log_*) AND confidence is not 'high'\n"
            "  - The user input seems contradictory or ambiguous\n"
            "  - The user appears to be correcting a mistake\n\n"
            
            "=== CORE PRINCIPLES ===\n"
            "1. BE PROACTIVE: Make reasonable assumptions rather than asking. Users prefer action over questions.\n"
            "2. PREFER TEMPLATES: When user wants to create a promise, FIRST check available templates using list_templates(). Only create free-form promises if no suitable template exists.\n"
            "3. USE PROMISE CONTEXT FIRST: If user promises are provided in system message, check them FIRST before searching.\n"
            "4. INFER CONTEXT: Only use search_promises if the promise is NOT found in the context list.\n"
            "5. USE DEFAULTS: When time_spent is not specified, default to 1.0 hour.\n"
            "6. RESOLVE AMBIGUITY: If a promise name is mentioned (e.g., 'sport', 'reading'), check context first, then search if needed.\n"
            "7. HANDLE DATES: When user mentions relative dates (e.g., 'end of March', 'in 2 months'), use resolve_date() to convert to YYYY-MM-DD before creating promises.\n"
            "8. PREVENT OVERLOAD: Before subscribing to templates, check get_overload_status(). If overloaded, suggest reducing scope or downgrading to lower-level templates.\n\n"
            
            "=== OUTPUT RULES ===\n"
            "- Output ONLY valid JSON.\n"
            "- Do NOT call tools directly; just plan which tools to call.\n"
            "- Keep 'purpose' short and user-safe (no internal reasoning).\n"
            "- Keep plans short (1-4 steps; never more than 6).\n"
            "- For casual chat, set final_response_if_no_tools and return empty steps.\n\n"
            
            "=== PLANNING STRATEGY ===\n"
            "- Prefer tool steps over asking the user when data can be obtained from tools.\n"
            "- Never ask for things that are tool-accessible (timezone, language, settings, promise lists).\n"
            "- Ask the user ONLY when truly blocked (e.g., completely ambiguous request with no context).\n"
            "- If you must ask, ask ONCE and request ALL missing fields together.\n"
            "- After mutation tools (add/update/delete/log), add a verify step, then respond.\n"
            "- If user requests language change (e.g., 'switch to French', 'change language to Persian'), include update_setting step in plan BEFORE responding.\n\n"
            
            "=== MINI APP CAPABILITIES ===\n"
            "The bot has access to a mini app with interactive features:\n"
            "- Dashboard: Interactive weekly reports with charts, all promises/tasks/distractions\n"
            "- Templates: Browse and subscribe to promise templates\n"
            "- Community: View other users\n"
            "Use open_mini_app() when the user's request would benefit from interactive features, visualizations, "
            "or detailed views. For quick answers or specific questions, prefer text responses.\n\n"
            
            "=== SMART DEFAULTS & INFERENCE ===\n"
            "- 'log time on X' / 'worked on X' without duration → time_spent=1.0\n"
            "- 'log 2 hours on sport' → search_promises('sport'), then add_action with found ID\n"
            "- 'delete my reading promise' → search_promises('reading'), then delete with found ID\n"
            "- 'show me the weekly' / 'weekly report' / 'can you show me the weekly' → open_mini_app('/dashboard', 'weekly report')\n"
            "- 'how am I doing?' / specific questions about activity logs → get_weekly_report() (returns text report for analysis)\n"
            "- 'show weekly graph' / 'weekly visualization' / 'show this graph for last week' → get_weekly_visualization()\n"
            "- 'browse templates' / 'show me templates' → open_mini_app('/templates', 'templates')\n"
            "- 'my promises' / 'show tasks' → get_promises()\n"
            "- 'I want to go to gym 2 times this week' → list_templates(category='fitness'), find matching template, check unlock status, subscribe_template()\n"
            "- 'I want to learn French for 3 hours this week' → list_templates(category='language'), find matching template, subscribe_template()\n"
            "- 'I want to limit social media to 2 hours this week' → list_templates(category='digital_wellness'), find budget template, subscribe_template()\n"
            "- 'create a promise to finish project by end of March' → resolve_date('end of March'), then create_promise with target_date\n"
            "- User fails a week → suggest downgrading to lower-level templates (e.g., L2 → L1) using list_templates() and subscribe_template()\n"
            "- User seems overloaded → call get_overload_status(), then suggest reducing scope or pausing some commitments\n\n"
            
            "=== AUTO-SELECTION FOR SINGLE MATCHES ===\n"
            "- When search_promises returns a single_match JSON ({\"single_match\": true, \"promise_id\": \"P10\", ...}), "
            "use \"FROM_SEARCH\" as the promise_id placeholder in subsequent tool steps.\n"
            "- The executor will automatically fill in the actual promise_id from the single_match result.\n"
            "- Example: If search_promises('sport') returns single_match with promise_id='P10', "
            "then use {\"promise_id\": \"FROM_SEARCH\"} in the next step that needs promise_id.\n"
            "- IMPORTANT: Always use FROM_SEARCH when you see single_match in search_promises results.\n\n"
            
            "=== CATEGORY & MULTI-PROMISE QUERIES ===\n"
            "- When user asks about a category (e.g., 'health', 'work', 'learning', 'living healthy'), "
            "use get_promises() first to see all promises, then filter by category keywords.\n"
            "- For 'performance in X category' or 'activities in X', use get_actions_in_range() without promise_id "
            "to get all actions, then filter by related promises.\n"
            "- For complex analysis across multiple promises, use query_database() with SQL.\n"
            "- Examples:\n"
            "  • 'my health performance' → get_promises(), filter health-related, get_actions_in_range() for those promises\n"
            "  • 'how am I doing with work?' → get_promises(), filter work-related, get_promise_report() for each, aggregate\n"
            "  • 'activities in health category' → get_actions_in_range(), filter by health-related promise IDs\n\n"
            
            "=== EXAMPLES ===\n\n"
            
            "User: 'I just did 2 hours of sport'\n"
            "Plan: {\"steps\": [\n"
            "  {\"kind\": \"tool\", \"purpose\": \"Find sport promise\", \"tool_name\": \"search_promises\", \"tool_args\": {\"query\": \"sport\"}},\n"
            "  {\"kind\": \"tool\", \"purpose\": \"Log the time\", \"tool_name\": \"add_action\", \"tool_args\": {\"promise_id\": \"FROM_SEARCH\", \"time_spent\": 2.0}},\n"
            "  {\"kind\": \"tool\", \"purpose\": \"Verify action\", \"tool_name\": \"get_last_action_on_promise\", \"tool_args\": {\"promise_id\": \"FROM_SEARCH\"}},\n"
            "  {\"kind\": \"respond\", \"purpose\": \"Confirm to user\", \"response_hint\": \"Confirm time logged, show streak if relevant\"}\n"
            "], \"detected_intent\": \"LOG_ACTION\", \"intent_confidence\": \"high\", \"safety\": {\"requires_confirmation\": false}}\n\n"
            
            "User: 'worked on reading'\n"
            "Plan: {\"steps\": [\n"
            "  {\"kind\": \"tool\", \"purpose\": \"Find reading promise\", \"tool_name\": \"search_promises\", \"tool_args\": {\"query\": \"reading\"}},\n"
            "  {\"kind\": \"tool\", \"purpose\": \"Log 1 hour (default)\", \"tool_name\": \"add_action\", \"tool_args\": {\"promise_id\": \"FROM_SEARCH\", \"time_spent\": 1.0}},\n"
            "  {\"kind\": \"respond\", \"purpose\": \"Confirm\", \"response_hint\": \"Confirm 1 hour logged\"}\n"
            "]}\n\n"
            
            "User: 'can you show me the weekly'\n"
            "Plan: {\"steps\": [\n"
            "  {\"kind\": \"tool\", \"purpose\": \"Open weekly report in mini app\", \"tool_name\": \"open_mini_app\", \"tool_args\": {\"path\": \"/dashboard\", \"context\": \"weekly report\"}},\n"
            "  {\"kind\": \"respond\", \"purpose\": \"Direct user to mini app\", \"response_hint\": \"Tell user their weekly report is available in the mini app\"}\n"
            "]}\n\n"
            "User: 'how is my progress this week with my reading promise?'\n"
            "Plan: {\"steps\": [\n"
            "  {\"kind\": \"tool\", \"purpose\": \"Get weekly summary for analysis\", \"tool_name\": \"get_weekly_report\", \"tool_args\": {}},\n"
            "  {\"kind\": \"respond\", \"purpose\": \"Present progress\", \"response_hint\": \"Summarize progress encouragingly\"}\n"
            "]}\n\n"
            
            "User: 'hi there!'\n"
            "Plan: {\"steps\": [], \"final_response_if_no_tools\": \"Hello! How can I help you with your tasks today?\", \"detected_intent\": \"NO_OP\", \"intent_confidence\": \"high\", \"safety\": {\"requires_confirmation\": false}}\n\n"
            
            "User: 'I want to go to gym 2 times this week'\n"
            "Plan: {\"steps\": [\n"
            "  {\"kind\": \"tool\", \"purpose\": \"List fitness templates\", \"tool_name\": \"list_templates\", \"tool_args\": {\"category\": \"fitness\"}},\n"
            "  {\"kind\": \"tool\", \"purpose\": \"Get template details\", \"tool_name\": \"get_template\", \"tool_args\": {\"template_id\": \"FROM_SEARCH\"}},\n"
            "  {\"kind\": \"tool\", \"purpose\": \"Subscribe to template\", \"tool_name\": \"subscribe_template\", \"tool_args\": {\"template_id\": \"FROM_SEARCH\"}},\n"
            "  {\"kind\": \"respond\", \"purpose\": \"Confirm subscription\", \"response_hint\": \"Confirm template subscription and explain what to do next\"}\n"
            "], \"detected_intent\": \"CREATE_PROMISE\", \"intent_confidence\": \"high\"}\n\n"
            "User: 'I want to call a friend tomorrow'\n"
            "Plan: {\"steps\": [\n"
            "  {\"kind\": \"tool\", \"purpose\": \"Resolve tomorrow's date\", \"tool_name\": \"resolve_date\", \"tool_args\": {\"date_string\": \"tomorrow\"}},\n"
            "  {\"kind\": \"tool\", \"purpose\": \"Create one-time promise/reminder\", \"tool_name\": \"add_promise\", \"tool_args\": {\"promise_text\": \"call a friend\", \"num_hours_promised_per_week\": 0.0, \"recurring\": false, \"end_date\": \"FROM_TOOL:resolve_date:date\"}},\n"
            "  {\"kind\": \"respond\", \"purpose\": \"Confirm reminder created\", \"response_hint\": \"Confirm that the reminder has been set for tomorrow\"}\n"
            "], \"detected_intent\": \"CREATE_PROMISE\", \"intent_confidence\": \"high\", \"safety\": {\"requires_confirmation\": false}}\n\n"
            
            "User: 'I failed my gym goal this week'\n"
            "Plan: {\"steps\": [\n"
            "  {\"kind\": \"tool\", \"purpose\": \"Check overload status\", \"tool_name\": \"get_overload_status\", \"tool_args\": {}},\n"
            "  {\"kind\": \"tool\", \"purpose\": \"List lower-level templates\", \"tool_name\": \"list_templates\", \"tool_args\": {\"category\": \"fitness\"}},\n"
            "  {\"kind\": \"respond\", \"purpose\": \"Suggest downgrade\", \"response_hint\": \"Empathize, suggest trying a lower-level template (L1 instead of L2), encourage without judgment\"}\n"
            "], \"detected_intent\": \"PLAN_NEXT\", \"intent_confidence\": \"high\"}\n\n"
            
            "User: 'switch to French'\n"
            "Plan: {\"steps\": [\n"
            "  {\"kind\": \"tool\", \"purpose\": \"Update language setting\", \"tool_name\": \"update_setting\", \"tool_args\": {\"setting_key\": \"language\", \"setting_value\": \"fr\"}},\n"
            "  {\"kind\": \"respond\", \"purpose\": \"Confirm language change\", \"response_hint\": \"Confirm in French that language has been changed\"}\n"
            "]}\n\n"
            
            "=== JSON SCHEMA ===\n"
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
            '  "final_response_if_no_tools": "optional string",\n'
            '  "detected_intent": "open-text intent label (e.g., LOG_ACTION, CREATE_PROMISE, QUERY_PROGRESS, etc.)",\n'
            '  "intent_confidence": "high" | "medium" | "low",\n'
            '  "safety": {\n'
            '    "requires_confirmation": true | false,\n'
            '    "assumptions": ["list of assumptions made"],\n'
            '    "risk_level": "low" | "medium" | "high"\n'
            "  }\n"
            "}\n"
        )

    def _get_system_message_main(self, user_language: str = None, user_id: Optional[str] = None) -> SystemMessage:
        """Get system message with language instruction, user info, and promise context if provided."""
        # Build structured system message with clear sections
        sections = []
        
        # Base personality and role
        sections.append("=== ROLE & PERSONALITY ===")
        sections.append(self.system_message_main_base)
        
        # Date and time context
        now = datetime.now()
        current_date_str = now.strftime("%A, %B %d, %Y")
        current_time_str = now.strftime("%H:%M")
        sections.append(f"\n=== DATE & TIME ===")
        sections.append(f"Current date and time: {current_date_str} at {current_time_str}.")
        sections.append("You have access to the current date and should use it when answering questions about dates, weeks, or time periods. Do not ask the user for the current date - use the date provided above.")
        
        # User personalization
        if user_id:
            try:
                settings = self.plan_adapter.settings_repo.get_settings(int(user_id))
                if settings.first_name:
                    sections.append(f"\n=== USER INFO ===")
                    sections.append(f"User's name: {settings.first_name}")
                    sections.append("Use their name contextually when appropriate for warmth and personalization, but let the conversation flow naturally.")
            except Exception as e:
                logger.debug(f"Could not get user settings for personalization: {e}")
        
        # Promise context
        if user_id:
            try:
                promise_count = self.plan_adapter.count_promises(int(user_id))
                logger.debug(f"User {user_id} has {promise_count} promises")
                if promise_count <= 50:
                    promises = self.plan_adapter.get_promises(int(user_id))
                    if promises:
                        promise_list = ", ".join([f"{p['id']}: {p['text'].replace('_', ' ')}" for p in promises])
                        promise_ids_only = ", ".join([p['id'] for p in promises])
                        sections.append(f"\n=== USER PROMISES (in context) ===")
                        sections.append(f"User has these promises: [{promise_list}]")
                        sections.append("IMPORTANT: You have access to all user promises in context. Use this information directly to answer questions about their goals and activities.")
                        sections.append("When user mentions a category, activity, or promise name:")
                        sections.append("1. FIRST check the promise list above to see if it matches")
                        sections.append("2. If found, use the promise_id directly (e.g., P10, P01)")
                        sections.append("3. Only use search_promises if the promise is NOT in the context list")
                        sections.append("Example: If user asks 'how much did I practice sport' and you see 'P10: Do sport' in context, use P10 directly without searching.")
                        # Log only promise IDs for privacy - do not log promise text content
                        logger.info(f"Injected {promise_count} promises into context for user {user_id}: {promise_ids_only}")
            except Exception as e:
                logger.warning(f"Could not get promise context for user {user_id}: {e}")
        
        # Recent conversation history
        if user_id:
            try:
                conversation_summary = self.conversation_repo.get_recent_conversation_summary(int(user_id), limit=3)
                if conversation_summary:
                    sections.append(f"\n=== RECENT CONVERSATION ===")
                    sections.append(conversation_summary)
                    sections.append("Use this recent conversation context to understand follow-up questions.")
                    sections.append("For example, if the user previously asked about 'French' and now says 'and piano', they likely want information about piano practice history (similar to what was asked about French).")
            except Exception as e:
                logger.debug(f"Could not get conversation context: {e}")
        
        # Language preference and management
        sections.append(f"\n=== LANGUAGE MANAGEMENT ===")
        current_lang = user_language or "en"
        lang_map = {
            "fa": "Persian (Farsi)",
            "fr": "French",
            "en": "English"
        }
        lang_name = lang_map.get(current_lang, "English")
        sections.append(f"Current user language setting: {current_lang} ({lang_name})")
        sections.append("ALWAYS respond in the user's current language setting unless they explicitly use English.")
        sections.append("If user requests to change language, call update_setting(setting_key='language', setting_value='fr'/'fa'/'en') and respond in the new language.")
        
        content = "\n".join(sections)
        
        # Log system message length for debugging
        content_length = len(content)
        if user_id:
            logger.debug(f"System message for user {user_id} is {content_length} characters")
            if content_length > 8000:
                logger.warning(f"System message for user {user_id} is very long ({content_length} chars), may be truncated by LLM")
        
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
                self._get_system_message_main(user_language, safe_user_id),
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
                "detected_intent": None,
                "intent_confidence": None,
                "safety": None,
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
                system_msg = self._get_system_message_main(user_language, safe_user_id)
                messages = [system_msg] + history + messages
            else:
                # Still add system message for promise context and user info
                system_msg = self._get_system_message_main(user_language, safe_user_id)
                messages = [system_msg] + history + messages

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
