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
}

# Cross-provider fallback defaults.
FALLBACK_MODELS = {
    "gemini": "gemini-2.5-flash-lite",
    "openai": "gpt-4o-mini",
}

# Some Gemini models are global-only.
GLOBAL_ONLY_PREFIXES: Tuple[str, ...] = ("gemini-3-",)


def normalize_provider_name(provider: str | None) -> str:
    raw = (provider or "").strip().lower()
    if raw in {"google", "gemini"}:
        return "gemini"
    if raw == "openai":
        return "openai"
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
