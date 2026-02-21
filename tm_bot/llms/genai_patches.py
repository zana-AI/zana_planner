"""
Monkey-patch for google-genai SDK to fix Gemini 3 thought_signature rejection
and to disable AFC so LangGraph controls the tool loop (avoids long hangs).

See: https://github.com/langchain-ai/langchain-google/issues/1570
When langchain-google-genai sends prior AIMessages back to the API, the SDK's
encode_unserializable_types() base64-encodes thought_signature bytes, which the
API then rejects as "Thought signature is not valid". Replacing the encoded value
with the documented bypass string fixes multi-turn tool-calling with Gemini 3.

AFC (Automatic Function Calling) is enabled by default with max_remote_calls=10,
so a single model.invoke() can do up to 10 internal API round-trips and appear
stuck. We set maximum_remote_calls=0 so the SDK returns after one response and
our LangGraph executor handles tool execution.

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


def _apply_afc_disable_patch() -> None:
    """Set automatic_function_calling.maximum_remote_calls=0 on generate_content config.

    So each invoke() returns after one model response; LangGraph runs tools and
    calls the model again instead of the SDK doing many internal round-trips.
    """
    try:
        from google.genai import types
        AutomaticFunctionCallingConfig = getattr(
            types, "AutomaticFunctionCallingConfig", None
        )
        if AutomaticFunctionCallingConfig is None:
            return
        afc_zero = AutomaticFunctionCallingConfig(maximum_remote_calls=0)
    except ImportError:
        return

    try:
        from google.genai import models as genai_models
    except ImportError:
        return

    _original_generate = getattr(genai_models, "generate_content", None)
    if _original_generate is None or getattr(
        genai_models, "_genai_afc_patch_applied", False
    ):
        return

    def _patched_generate_content(*args: object, **kwargs: object) -> object:
        config = kwargs.get("config")
        if config is not None:
            if hasattr(config, "model_copy"):
                config = config.model_copy(
                    update={"automatic_function_calling": afc_zero},
                    deep=True,
                )
            elif isinstance(config, dict):
                config = {**config, "automatic_function_calling": afc_zero}
            kwargs = {**kwargs, "config": config}
        return _original_generate(*args, **kwargs)

    genai_models.generate_content = _patched_generate_content  # type: ignore[assignment]
    genai_models._genai_afc_patch_applied = True  # type: ignore[attr-defined]


def apply_genai_patches() -> None:
    """Apply thought_signature bypass and AFC-disable patches."""
    try:
        import google.genai._common as _common_mod
    except ImportError:
        pass
    else:
        _original_encode = getattr(_common_mod, "encode_unserializable_types", None)
        if _original_encode is not None and not getattr(
            _common_mod, "_genai_patch_applied", False
        ):
            def _patched_encode(data: dict) -> dict:
                result = _original_encode(data)
                if isinstance(result, dict):
                    result = _replace_thought_signatures(result)
                return result

            _common_mod.encode_unserializable_types = _patched_encode
            _common_mod._genai_patch_applied = True  # type: ignore[attr-defined]

    _apply_afc_disable_patch()
