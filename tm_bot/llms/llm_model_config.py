from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class RoleModels:
    router: str
    planner: str
    responder: str

    def as_dict(self) -> Dict[str, str]:
        return {
            "router": self.router,
            "planner": self.planner,
            "responder": self.responder,
        }


# Central model mapping for the bot runtime.
# Keep all role-model choices here rather than in .env.
MODEL_CONFIGS = {
    "gemini": RoleModels(
        router="gemini-2.5-flash-lite",
        planner="gemini-2.5-flash",
        responder="gemini-2.5-flash",
    ),
    "openai": RoleModels(
        router="gpt-4o-mini",
        planner="gpt-4o-mini",
        responder="gpt-4o-mini",
    ),
    "deepseek": RoleModels(
        router="deepseek-chat",
        planner="deepseek-chat",
        responder="deepseek-chat",
    ),
    "groq": RoleModels(
        router="openai/gpt-oss-20b",
        planner="llama-3.3-70b-versatile",
        responder="llama-3.3-70b-versatile",
    ),
}

# Cross-provider fallback defaults.
FALLBACK_MODELS = {
    "gemini": "gemini-2.5-flash-lite",
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
    "groq": "llama-3.3-70b-versatile",
}

# Some Gemini models are global-only.
GLOBAL_ONLY_PREFIXES: Tuple[str, ...] = ("gemini-3-",)


# Approximate per-1M-token pricing (USD), input/output.
# Used only for cost estimation in the admin LLM-usage dashboard.
# Update as provider prices change. Models not present here render with cost=None.
MODEL_PRICING: Dict[str, Tuple[float, float]] = {
    # Groq
    "openai/gpt-oss-20b": (0.10, 0.50),
    "openai/gpt-oss-120b": (0.15, 0.75),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
    "moonshotai/kimi-k2-instruct": (1.00, 3.00),
    "qwen/qwen3-32b": (0.29, 0.59),
    "deepseek-r1-distill-llama-70b": (0.75, 0.99),
    # Gemini (Vertex AI list price)
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
    # OpenAI
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    # DeepSeek
    "deepseek-chat": (0.27, 1.10),
}


def estimate_cost_usd(model_name: str, input_tokens: int, output_tokens: int) -> float | None:
    price = MODEL_PRICING.get((model_name or "").strip())
    if not price:
        return None
    in_price, out_price = price
    return (input_tokens * in_price + output_tokens * out_price) / 1_000_000.0


def normalize_provider_name(provider: str | None) -> str:
    raw = (provider or "").strip().lower()
    if raw in {"google", "gemini"}:
        return "gemini"
    if raw == "openai":
        return "openai"
    if raw == "deepseek":
        return "deepseek"
    if raw == "groq":
        return "groq"
    if raw == "auto":
        return "auto"
    return raw


def get_role_models(provider: str) -> RoleModels:
    key = normalize_provider_name(provider)
    if key not in MODEL_CONFIGS:
        raise ValueError(f"Unsupported provider for role model config: {provider}")
    return MODEL_CONFIGS[key]


def get_fallback_model(provider: str) -> str:
    key = normalize_provider_name(provider)
    model = FALLBACK_MODELS.get(key)
    if not model:
        raise ValueError(f"No fallback model configured for provider: {provider}")
    return model


def needs_global_location(*model_names: str) -> bool:
    for model in model_names:
        model_name = (model or "").strip()
        if any(model_name.startswith(prefix) for prefix in GLOBAL_ONLY_PREFIXES):
            return True
    return False
