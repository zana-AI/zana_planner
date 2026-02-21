# llm_env_utils.py
import os
import base64
import tempfile
from dotenv import load_dotenv

def load_llm_env():
    """
    Loads environment variables from .env and prepares credentials for Vertex AI.
    Also configures LangSmith tracing if LANGCHAIN_API_KEY is present.
    Returns a dict with project, location, model, and LangSmith settings.
    """
    load_dotenv()  # ensure .env is loaded

    openai_key = os.getenv("OPENAI_API_KEY", "")
    # if not self.openai_key:
    #     raise ValueError("OpenAI API key is not set in environment variables.")

    project_id = os.getenv("GCP_PROJECT_ID")
    location   = os.getenv("GCP_LOCATION", "us-central1")
    model_name = os.getenv("GCP_GEMINI_MODEL", "gemini-2.5-flash")

    # Some models (e.g. gemini-3-*) are only available in the "global" region.
    # Allow explicit override via GCP_LLM_LOCATION, otherwise auto-detect.
    _GLOBAL_ONLY_PREFIXES = ("gemini-3-",)
    llm_location = os.getenv("GCP_LLM_LOCATION") or (
        "global" if any(model_name.startswith(p) for p in _GLOBAL_ONLY_PREFIXES)
        else location
    )
    fallback_enabled = os.getenv("LLM_FALLBACK_ENABLED", "false").strip().lower() in ("1", "true", "yes")
    fallback_provider = os.getenv("LLM_FALLBACK_PROVIDER", "openai").strip().lower() or "openai"

    if not project_id:
        raise ValueError("GCP_PROJECT_ID is missing in .env")
    if not location:
        raise ValueError("GCP_LOCATION is missing in .env")

    # Handle base64 JSON credentials
    creds_b64 = os.getenv("GCP_CREDENTIALS_B64")
    if not creds_b64:
        raise ValueError("GCP_CREDENTIALS_B64 is missing in .env")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    tmp.write(base64.b64decode(creds_b64))
    tmp.close()
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name
    # os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"E:\workspace\ZanaAI\zana_planner\demo_features\vertex-access.json"

    # Configure LangSmith tracing if API key is present
    langsmith_api_key = os.getenv("LANGCHAIN_API_KEY", "")
    langsmith_project = os.getenv("LANGCHAIN_PROJECT", "zana-planner")
    langsmith_enabled = False
    
    if langsmith_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_PROJECT"] = langsmith_project
        os.environ["LANGCHAIN_API_KEY"] = langsmith_api_key
        langsmith_enabled = True

    def _float_env(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, str(default)))
        except (TypeError, ValueError):
            return default

    def _int_env(name: str, default: int, minimum: int = 0) -> int:
        try:
            value = int(os.getenv(name, str(default)))
        except (TypeError, ValueError):
            return default
        return max(minimum, value)

    def _bool_env(name: str, default: bool) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return str(raw).strip().lower() in ("1", "true", "yes", "on")

    gemini_thinking_level = (os.getenv("GEMINI_THINKING_LEVEL", "minimal") or "").strip().lower() or None
    if gemini_thinking_level not in {None, "minimal", "low", "medium", "high"}:
        gemini_thinking_level = "minimal"

    return {
        "GCP_PROJECT_ID": project_id,
        "GCP_LOCATION": location,
        "GCP_LLM_LOCATION": llm_location,
        "GCP_GEMINI_MODEL": model_name,
        "OPENAI_API_KEY": openai_key,
        "LLM_FALLBACK_ENABLED": fallback_enabled,
        "LLM_FALLBACK_PROVIDER": fallback_provider,
        "LANGSMITH_ENABLED": langsmith_enabled,
        "LANGSMITH_PROJECT": langsmith_project if langsmith_enabled else None,
        # Per-role temperatures: router/planner use low temp for structured output;
        # responder uses higher temp for natural-language variety.
        "LLM_ROUTER_TEMPERATURE": _float_env("LLM_ROUTER_TEMPERATURE", 0.2),
        "LLM_PLANNER_TEMPERATURE": _float_env("LLM_PLANNER_TEMPERATURE", 0.2),
        "LLM_RESPONDER_TEMPERATURE": _float_env("LLM_RESPONDER_TEMPERATURE", 0.7),
        # Gemini reliability/latency controls
        "LLM_REQUEST_TIMEOUT_SECONDS": _float_env("LLM_REQUEST_TIMEOUT_SECONDS", 30.0),
        # For google-genai retries, 1 means "single attempt, no retries".
        "LLM_MAX_RETRIES": _int_env("LLM_MAX_RETRIES", 1, minimum=1),
        "GEMINI_DISABLE_AFC": _bool_env("GEMINI_DISABLE_AFC", True),
        "GEMINI_INCLUDE_THOUGHTS": _bool_env("GEMINI_INCLUDE_THOUGHTS", False),
        "GEMINI_THINKING_LEVEL": gemini_thinking_level,
    }
