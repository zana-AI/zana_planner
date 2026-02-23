import os
import base64
import tempfile
from dotenv import load_dotenv
from llms.llm_model_config import (
    get_fallback_model,
    get_role_models,
    needs_global_location,
)


def load_llm_env():
    """
    Loads environment variables from .env and prepares credentials for Vertex AI.
    Also configures LangSmith tracing if LANGCHAIN_API_KEY is present.
    Returns a dict with project, location, model, and LangSmith settings.
    """
    load_dotenv()  # ensure .env is loaded

    openai_key = os.getenv("OPENAI_API_KEY", "")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url = (os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1") or "").strip() or "https://api.deepseek.com/v1"
    groq_key = os.getenv("GROQ_API_KEY", "")
    groq_base_url = (os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1") or "").strip() or "https://api.groq.com/openai/v1"
    groq_plan_tier = (os.getenv("GROQ_PLAN_TIER", "free") or "").strip().lower() or "free"
    if groq_plan_tier not in {"free", "developer"}:
        groq_plan_tier = "free"
    env_name = (os.getenv("ENV", "") or os.getenv("ENVIRONMENT", "")).strip().lower()
    llm_provider_requested = (os.getenv("LLM_PROVIDER", "auto") or "auto").strip().lower()

    project_id = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("GCP_LOCATION", "us-central1")
    creds_b64 = os.getenv("GCP_CREDENTIALS_B64")
    fallback_raw = os.getenv("LLM_FALLBACK_ENABLED")
    fallback_provider_raw = os.getenv("LLM_FALLBACK_PROVIDER")
    fallback_gemini_model = get_fallback_model("gemini")
    fallback_openai_model = get_fallback_model("openai")
    fallback_deepseek_model = get_fallback_model("deepseek")
    fallback_groq_model = get_fallback_model("groq")

    has_gemini_creds = bool(project_id and creds_b64 and location)
    if llm_provider_requested == "auto":
        # Code-owned default provider precedence:
        # prefer Groq when configured, then Gemini/OpenAI/DeepSeek.
        if groq_key:
            llm_provider = "groq"
        elif has_gemini_creds:
            llm_provider = "gemini"
        elif openai_key:
            llm_provider = "openai"
        elif deepseek_key:
            llm_provider = "deepseek"
        else:
            raise ValueError(
                "No LLM provider credentials found. Set Gemini (GCP_*), OpenAI (OPENAI_API_KEY), DeepSeek (DEEPSEEK_API_KEY), or Groq (GROQ_API_KEY)."
            )
    elif llm_provider_requested in {"gemini", "google"}:
        llm_provider = "gemini"
        if not has_gemini_creds:
            raise ValueError("LLM_PROVIDER=gemini but Gemini credentials are incomplete.")
    elif llm_provider_requested == "openai":
        llm_provider = "openai"
        if not openai_key:
            raise ValueError("LLM_PROVIDER=openai but OPENAI_API_KEY is missing.")
    elif llm_provider_requested == "deepseek":
        llm_provider = "deepseek"
        if not deepseek_key:
            raise ValueError("LLM_PROVIDER=deepseek but DEEPSEEK_API_KEY is missing.")
    elif llm_provider_requested == "groq":
        llm_provider = "groq"
        if not groq_key:
            raise ValueError("LLM_PROVIDER=groq but GROQ_API_KEY is missing.")
    else:
        raise ValueError(f"Unsupported LLM_PROVIDER='{llm_provider_requested}'")

    # Provider fallback choice is code-owned by default, with env override support.
    if fallback_provider_raw is not None:
        fallback_provider = fallback_provider_raw.strip().lower() or "openai"
    elif llm_provider == "groq":
        # Keep Groq fallback in-provider by default:
        # openai/gpt-oss-20b -> llama-3.3-70b-versatile.
        fallback_provider = "groq"
    elif llm_provider == "gemini":
        # Prefer Groq over DeepSeek/OpenAI when available for lower latency.
        if groq_key:
            fallback_provider = "groq"
        elif deepseek_key:
            fallback_provider = "deepseek"
        elif openai_key:
            fallback_provider = "openai"
        else:
            fallback_provider = "gemini"
    elif llm_provider == "openai":
        if groq_key:
            fallback_provider = "groq"
        elif deepseek_key:
            fallback_provider = "deepseek"
        elif has_gemini_creds:
            fallback_provider = "gemini"
        else:
            fallback_provider = "openai"
    elif llm_provider == "deepseek":
        if groq_key:
            fallback_provider = "groq"
        elif openai_key:
            fallback_provider = "openai"
        elif has_gemini_creds:
            fallback_provider = "gemini"
        else:
            fallback_provider = "deepseek"
    else:
        fallback_provider = "openai"

    if fallback_raw is None:
        # Code-owned fallback defaults:
        # - always enabled for Groq so preblocked/rate-limited model fallback works
        #   with only GROQ_API_KEY in env.
        # - keep existing staged-env default for other providers.
        fallback_enabled = llm_provider == "groq" or env_name in {"staging", "stage", "test", "testing"}
    else:
        fallback_enabled = str(fallback_raw).strip().lower() in ("1", "true", "yes")

    if llm_provider == "gemini":
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        tmp.write(base64.b64decode(creds_b64))
        tmp.close()
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name

    role_models = get_role_models(llm_provider).as_dict()
    openai_role_models = get_role_models("openai").as_dict()
    gemini_role_models = get_role_models("gemini").as_dict()
    deepseek_role_models = get_role_models("deepseek").as_dict()
    groq_role_models = get_role_models("groq").as_dict()

    # Some models (e.g. gemini-3-*) are only available in the "global" region.
    # Allow explicit override via GCP_LLM_LOCATION, otherwise auto-detect.
    if llm_provider == "gemini":
        llm_location = os.getenv("GCP_LLM_LOCATION") or (
            "global"
            if needs_global_location(
                role_models.get("router", ""),
                role_models.get("planner", ""),
                role_models.get("responder", ""),
            )
            else location
        )
    else:
        llm_location = os.getenv("GCP_LLM_LOCATION") or location

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

    # Non-Gemini providers rely on the provider-layer adapters.
    # Keep this code-owned so GROQ_API_KEY alone is enough to run Groq.
    default_provider_layer_enabled = (
        llm_provider in {"openai", "deepseek", "groq"}
        or env_name in {"staging", "stage", "test", "testing"}
    )
    default_strict_mutation = env_name in {"staging", "stage", "test", "testing"}
    feature_policy = (os.getenv("LLM_FEATURE_POLICY", "safe") or "safe").strip().lower()
    if feature_policy not in {"safe", "balanced", "full"}:
        feature_policy = "safe"

    def _feature_policy_for_role(role: str) -> str:
        role_raw = (os.getenv(f"LLM_FEATURE_POLICY_{role.upper()}", "") or "").strip().lower()
        if role_raw in {"safe", "balanced", "full"}:
            return role_raw
        return feature_policy

    return {
        "LLM_PROVIDER": llm_provider,
        "LLM_PROVIDER_REQUESTED": llm_provider_requested,
        "LLM_PROVIDER_LAYER_ENABLED": _bool_env("LLM_PROVIDER_LAYER_ENABLED", default_provider_layer_enabled),
        "LLM_FEATURE_POLICY": feature_policy,
        "LLM_FEATURE_POLICY_ROUTER": _feature_policy_for_role("router"),
        "LLM_FEATURE_POLICY_PLANNER": _feature_policy_for_role("planner"),
        "LLM_FEATURE_POLICY_RESPONDER": _feature_policy_for_role("responder"),
        "STRICT_MUTATION_EXECUTION": _bool_env("STRICT_MUTATION_EXECUTION", default_strict_mutation),
        "GCP_PROJECT_ID": project_id,
        "GCP_LOCATION": location,
        "GCP_LLM_LOCATION": llm_location,
        # Backward-compatibility key used by some helper modules.
        "GCP_GEMINI_MODEL": gemini_role_models["planner"],
        "LLM_ROUTER_MODEL": role_models["router"],
        "LLM_PLANNER_MODEL": role_models["planner"],
        "LLM_RESPONDER_MODEL": role_models["responder"],
        "LLM_OPENAI_ROUTER_MODEL": openai_role_models["router"],
        "LLM_OPENAI_PLANNER_MODEL": openai_role_models["planner"],
        "LLM_OPENAI_RESPONDER_MODEL": openai_role_models["responder"],
        "OPENAI_API_KEY": openai_key,
        "DEEPSEEK_API_KEY": deepseek_key,
        "DEEPSEEK_BASE_URL": deepseek_base_url,
        "GROQ_API_KEY": groq_key,
        "GROQ_BASE_URL": groq_base_url,
        "GROQ_PLAN_TIER": groq_plan_tier,
        # Backward-compatibility key used by some helper modules.
        "OPENAI_MODEL": openai_role_models["responder"],
        "LLM_DEEPSEEK_ROUTER_MODEL": deepseek_role_models["router"],
        "LLM_DEEPSEEK_PLANNER_MODEL": deepseek_role_models["planner"],
        "LLM_DEEPSEEK_RESPONDER_MODEL": deepseek_role_models["responder"],
        "LLM_GROQ_ROUTER_MODEL": groq_role_models["router"],
        "LLM_GROQ_PLANNER_MODEL": groq_role_models["planner"],
        "LLM_GROQ_RESPONDER_MODEL": groq_role_models["responder"],
        "LLM_FALLBACK_ENABLED": fallback_enabled,
        "LLM_FALLBACK_PROVIDER": fallback_provider,
        "LLM_FALLBACK_GEMINI_MODEL": fallback_gemini_model,
        "LLM_FALLBACK_OPENAI_MODEL": fallback_openai_model,
        "LLM_FALLBACK_DEEPSEEK_MODEL": fallback_deepseek_model,
        "LLM_FALLBACK_GROQ_MODEL": fallback_groq_model,
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
