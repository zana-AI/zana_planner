from __future__ import annotations

import inspect
from contextvars import ContextVar
from typing import Callable, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

# Context var to carry the active user_id during tool execution
_current_user_id: ContextVar[Optional[str]] = ContextVar("current_user_id", default=None)


def _strip_user_id_from_signature(sig: inspect.Signature) -> inspect.Signature:
    """Return a signature with self/user_id removed (tool args are model-provided)."""
    params = []
    for name, param in sig.parameters.items():
        if name in {"self", "user_id"}:
            continue
        params.append(param)
    return sig.replace(parameters=params)


def _required_params(sig: inspect.Signature) -> List[str]:
    """List required (no-default) parameters for a tool signature."""
    required = []
    for name, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL):
            continue
        if param.default is inspect._empty:
            required.append(name)
    return required


def _sanitize_user_id(user_id: str) -> str:
    """Allow only digit-only user identifiers to avoid cross-user access or path abuse."""
    if user_id is None:
        raise ValueError("user_id is required")
    user_id_str = str(user_id).strip()
    if not user_id_str.isdigit():
        raise ValueError("Invalid user_id")
    return user_id_str


def _wrap_tool(fn: Callable, tool_name: str, debug_enabled: bool = False) -> Callable:
    """Wrap adapter methods to enforce the active user_id and ignore model-provided user_id."""

    def wrapped(**kwargs):
        safe_user_id = _current_user_id.get()
        if not safe_user_id:
            raise ValueError("No active user_id set")

        # Strip any user_id provided by the model/tool call
        kwargs.pop("user_id", None)

        # Remove 'kwargs' if it was incorrectly passed as a keyword argument
        if "kwargs" in kwargs:
            logger.warning(f"Tool {tool_name} received 'kwargs' as a keyword argument, removing it")
            kwargs.pop("kwargs", None)

        # Validate parameters against function signature
        try:
            sig = inspect.signature(fn)
            public_sig = _strip_user_id_from_signature(sig)
            valid_params = set(public_sig.parameters.keys())

            invalid_params = set(kwargs.keys()) - valid_params
            if invalid_params:
                logger.warning(
                    f"Tool {tool_name} received invalid parameters: {invalid_params}. "
                    f"Valid parameters are: {valid_params}. Removing invalid ones."
                )
                for param in invalid_params:
                    kwargs.pop(param, None)

            missing_required = [
                p for p in _required_params(public_sig) if p not in kwargs or kwargs.get(p) in (None, "")
            ]
            if missing_required:
                return (
                    f"Missing required arguments for {tool_name}: {', '.join(missing_required)}. "
                    f"Provided: {sorted(list(kwargs.keys()))}. "
                    f"Please provide those fields and try again."
                )
        except Exception as e:
            if debug_enabled:
                logger.warning(f"Could not inspect signature for {tool_name}: {e}")

        if debug_enabled:
            logger.info(
                {
                    "event": "tool_invoke",
                    "tool": tool_name,
                    "user_id": safe_user_id,
                    "args_keys": list(kwargs.keys()),
                }
            )

        try:
            return fn(user_id=safe_user_id, **kwargs)
        except TypeError as e:
            logger.error(f"Error calling {tool_name} with parameters {list(kwargs.keys())}: {e}")
            raise

    wrapped.__name__ = tool_name
    wrapped.__doc__ = getattr(fn, "__doc__", None)
    try:
        wrapped.__signature__ = _strip_user_id_from_signature(inspect.signature(fn))
        ann = dict(getattr(fn, "__annotations__", {}) or {})
        ann.pop("user_id", None)
        ann.pop("self", None)
        wrapped.__annotations__ = ann
    except Exception as e:
        if debug_enabled:
            logger.warning(f"Could not set tool signature for {tool_name}: {e}")
    return wrapped

