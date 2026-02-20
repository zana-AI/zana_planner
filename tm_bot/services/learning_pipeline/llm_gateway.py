"""
Gemini-first LLM gateway with optional emergency fallback.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_vertexai import ChatVertexAI
from langchain_openai import ChatOpenAI

from llms.llm_env_utils import load_llm_env
from utils.logger import get_logger

logger = get_logger(__name__)


class LearningLLMGateway:
    def __init__(self) -> None:
        self._vertex_model = None
        self._fallback_model = None
        cfg = {}
        try:
            cfg = load_llm_env()
        except Exception as exc:
            logger.warning("LLM env load failed for learning pipeline: %s", exc)
            cfg = {}
        self._fallback_enabled = bool(cfg.get("LLM_FALLBACK_ENABLED")) or (
            os.getenv("LLM_FALLBACK_ENABLED", "false").strip().lower() in ("1", "true", "yes")
        )
        self._fallback_provider = (
            str(cfg.get("LLM_FALLBACK_PROVIDER") or os.getenv("LLM_FALLBACK_PROVIDER", "openai")).strip().lower()
            or "openai"
        )

        gcp_project = cfg.get("GCP_PROJECT_ID") or os.getenv("GCP_PROJECT_ID")
        gcp_location = cfg.get("GCP_LLM_LOCATION") or cfg.get("GCP_LOCATION") or os.getenv("GCP_LOCATION", "us-central1")
        gcp_model = cfg.get("GCP_GEMINI_MODEL") or os.getenv("GCP_GEMINI_MODEL", "gemini-2.5-flash")
        openai_api_key = cfg.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")

        if gcp_project:
            try:
                self._vertex_model = ChatVertexAI(
                    model=gcp_model,
                    project=gcp_project,
                    location=gcp_location,
                    temperature=0.2,
                )
            except Exception as exc:
                logger.warning("Gemini model init failed: %s", exc)
                self._vertex_model = None

        if self._fallback_enabled and self._fallback_provider == "openai" and openai_api_key:
            try:
                self._fallback_model = ChatOpenAI(
                    openai_api_key=openai_api_key,
                    model="gpt-4o-mini",
                    temperature=0.2,
                )
            except Exception as exc:
                logger.warning("OpenAI fallback init failed: %s", exc)
                self._fallback_model = None

    def available(self) -> bool:
        return self._vertex_model is not None or self._fallback_model is not None

    def invoke(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> Tuple[str, str, bool]:
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        if self._vertex_model is not None:
            try:
                output = self._vertex_model.invoke(messages)
                text = _to_text(output)
                if text:
                    return text, _model_name(self._vertex_model), False
            except Exception as exc:
                logger.warning("Gemini invoke failed: %s", exc)
        if self._fallback_enabled and self._fallback_model is not None:
            try:
                output = self._fallback_model.invoke(messages)
                text = _to_text(output)
                if text:
                    logger.warning(
                        "learning_pipeline_llm_fallback_used provider=%s model=%s",
                        self._fallback_provider,
                        _model_name(self._fallback_model),
                    )
                    return text, _model_name(self._fallback_model), True
            except Exception as exc:
                logger.warning("Fallback invoke failed: %s", exc)
        raise RuntimeError("No LLM response available")


def _to_text(message_obj) -> str:
    value = getattr(message_obj, "content", "")
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        return "\n".join(parts).strip()
    return str(value or "").strip()


def _model_name(model_obj) -> str:
    return getattr(model_obj, "model_name", None) or getattr(model_obj, "model", None) or "unknown_model"
