"""LLM-backed helpers for curated user name variants."""

import json
import re
from dataclasses import dataclass
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from llms.llm_env_utils import load_llm_env
from utils.logger import get_logger


logger = get_logger(__name__)


@dataclass
class NameVariants:
    non_latin_name: Optional[str] = None
    latin_name: Optional[str] = None


def _clean_name(value: object) -> Optional[str]:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    if not cleaned or cleaned.lower() in {"null", "none", "unknown"}:
        return None
    return cleaned[:120]


def _strip_json_fence(content: str) -> str:
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def _build_chat_model():
    cfg = load_llm_env()
    provider = cfg.get("LLM_PROVIDER")
    temperature = 0.1

    if provider == "gemini" and cfg.get("GCP_PROJECT_ID"):
        return ChatGoogleGenerativeAI(
            model=cfg["LLM_RESPONDER_MODEL"],
            project=cfg["GCP_PROJECT_ID"],
            location=cfg["GCP_LLM_LOCATION"],
            temperature=temperature,
        )

    if provider == "openai" and cfg.get("OPENAI_API_KEY"):
        return ChatOpenAI(
            openai_api_key=cfg["OPENAI_API_KEY"],
            model=cfg["LLM_OPENAI_RESPONDER_MODEL"],
            temperature=temperature,
        )

    if provider == "deepseek" and cfg.get("DEEPSEEK_API_KEY"):
        return ChatOpenAI(
            openai_api_key=cfg["DEEPSEEK_API_KEY"],
            openai_api_base=cfg["DEEPSEEK_BASE_URL"],
            model=cfg["LLM_DEEPSEEK_RESPONDER_MODEL"],
            temperature=temperature,
        )

    if provider == "groq" and cfg.get("GROQ_API_KEY"):
        return ChatOpenAI(
            openai_api_key=cfg["GROQ_API_KEY"],
            openai_api_base=cfg["GROQ_BASE_URL"],
            model=cfg["LLM_GROQ_RESPONDER_MODEL"],
            temperature=temperature,
        )

    raise ValueError("No supported LLM provider configured for name variants.")


def guess_name_variants(
    *,
    first_name: Optional[str],
    last_name: Optional[str] = None,
    username: Optional[str] = None,
    existing_non_latin_name: Optional[str] = None,
    existing_latin_name: Optional[str] = None,
) -> NameVariants:
    """Guess missing Latin and non-Latin name variants without overwriting known values."""
    current_non_latin = _clean_name(existing_non_latin_name)
    current_latin = _clean_name(existing_latin_name)
    source_parts = [_clean_name(first_name), _clean_name(last_name)]
    source_name = " ".join(part for part in source_parts if part)

    if current_non_latin and current_latin:
        return NameVariants(current_non_latin, current_latin)
    if not source_name and not username and not current_non_latin and not current_latin:
        return NameVariants(current_non_latin, current_latin)

    system_prompt = """You infer searchable user-name variants for an admin tool.

Return ONLY valid JSON:
{
  "non_latin_name": string or null,
  "latin_name": string or null
}

Rules:
- Preserve any existing non_latin_name or latin_name provided by the caller.
- latin_name must use Latin characters, with normal capitalization.
- non_latin_name should use the user's likely native non-Latin script when inferable.
- If the name appears Persian/Iranian or the app context suggests Persian speakers, prefer Persian script for non_latin_name.
- Do not translate meaning; transliterate the person's name.
- Do not include usernames, @ signs, explanations, alternatives, or confidence text.
- Return null for a field only when there is not enough signal to make a useful guess."""

    user_prompt = json.dumps(
        {
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
            "existing_non_latin_name": current_non_latin,
            "existing_latin_name": current_latin,
        },
        ensure_ascii=False,
    )

    response = _build_chat_model().invoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    )
    content = response.content if hasattr(response, "content") else str(response)
    try:
        parsed = json.loads(_strip_json_fence(content))
    except Exception as exc:
        logger.warning("Failed to parse name variant LLM response %r: %s", content, exc)
        return NameVariants(current_non_latin, current_latin)

    return NameVariants(
        non_latin_name=current_non_latin or _clean_name(parsed.get("non_latin_name")),
        latin_name=current_latin or _clean_name(parsed.get("latin_name")),
    )

