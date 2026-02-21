"""
Monkey-patch for google-genai SDK to fix Gemini 3 thought_signature rejection.

See: https://github.com/langchain-ai/langchain-google/issues/1570
When langchain-google-genai sends prior AIMessages back to the API, the SDK's
encode_unserializable_types() base64-encodes thought_signature bytes, which the
API then rejects as "Thought signature is not valid". Replacing the encoded value
with the documented bypass string fixes multi-turn tool-calling with Gemini 3.

TODO: Remove this module when langchain-google-genai releases a version with
PR #1581 (or equivalent) merged (likely 4.3.0+).
"""

from __future__ import annotations

BYPASS_STRING = "skip_thought_signature_validator"


def _replace_thought_signatures(obj: object) -> object:
    """Recursively replace any thought_signature value with the bypass string."""
    if isinstance(obj, dict):
        return {
            k: BYPASS_STRING if k == "thought_signature" else _replace_thought_signatures(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_replace_thought_signatures(item) for item in obj]
    return obj


def apply_genai_patches() -> None:
    """Patch google.genai._common.encode_unserializable_types for thought_signature bypass."""
    try:
        import google.genai._common as _common_mod
    except ImportError:
        return

    _original_encode = getattr(_common_mod, "encode_unserializable_types", None)
    if _original_encode is None or getattr(_common_mod, "_genai_patch_applied", False):
        return

    def _patched_encode(data: dict) -> dict:
        result = _original_encode(data)
        if isinstance(result, dict):
            result = _replace_thought_signatures(result)
        return result

    _common_mod.encode_unserializable_types = _patched_encode
    _common_mod._genai_patch_applied = True  # type: ignore[attr-defined]
