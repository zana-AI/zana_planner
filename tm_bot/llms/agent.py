from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langgraph.graph import END, StateGraph

from utils.logger import get_logger

logger = get_logger(__name__)
_DEBUG_ENABLED = os.getenv("LLM_DEBUG", "0") == "1" or os.getenv("ENV", "").lower() == "staging"

# LLM call counter for rate limit debugging (per-request tracking)
_llm_call_count = 0

def _track_llm_call(call_type: str, model_name: str = "unknown") -> None:
    """Track an LLM call for debugging rate limits."""
    global _llm_call_count
    _llm_call_count += 1
    if _DEBUG_ENABLED:
        logger.info({
            "event": "llm_call",
            "call_type": call_type,
            "model": model_name,
            "call_number": _llm_call_count,
            "timestamp": time.time(),
        })

# ToolNode import path varies across langgraph versions.
try:
    from langgraph.prebuilt import ToolNode as _ToolNode  # type: ignore
except Exception:  # pragma: no cover
    _ToolNode = None

from llms.planning_schema import Plan, PlanStep, RouteDecision

# ---------------------------------------------------------------------------
# Placeholder helpers — tolerant of model variations in case / whitespace
# ---------------------------------------------------------------------------

_FROM_SEARCH_RE = re.compile(r"^from[_\s]?search", re.IGNORECASE)
_FROM_TOOL_RE = re.compile(r"^from[_\s]?tool\s*:\s*([^:]*?)\s*:\s*(.*)", re.IGNORECASE)


def _is_from_search(val: str) -> bool:
    """Return True if *val* is a FROM_SEARCH placeholder (case/whitespace-insensitive)."""
    return bool(_FROM_SEARCH_RE.match(val or ""))


def _parse_from_tool(val: str) -> Optional[tuple]:
    """
    Parse a FROM_TOOL placeholder into (tool_name, field).

    Accepts variants such as:
    - ``FROM_TOOL:resolve_datetime:``
    - ``from_tool: resolve_datetime :``
    - ``FROM_TOOL:search_promises:promise_id``

    Returns ``None`` if *val* does not match the FROM_TOOL pattern.
    """
    m = _FROM_TOOL_RE.match(val or "")
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


def message_content_to_str(content: Any) -> str:
    """
    Normalize message content to a string.
    ChatGoogleGenerativeAI (and some other backends) may return content as a list
    of parts (e.g. [{"type": "text", "text": "..."}]) instead of a plain string.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text" and "text" in block:
                parts.append(str(block["text"]))
        return "\n".join(parts) if parts else ""
    return str(content)


class AgentState(TypedDict):
    """State passed between LangGraph nodes."""

    messages: List[BaseMessage]
    iteration: int
    plan: Optional[List[dict]]
    step_idx: int
    final_response: Optional[str]
    planner_error: Optional[str]
    # Optional metadata used to support stateful clarifications.
    pending_meta_by_idx: Optional[Dict[int, dict]]
    pending_clarification: Optional[dict]
    tool_retry_counts: Optional[Dict[str, int]]
    tool_call_history: Optional[List[dict]]
    tool_loop_warning_buckets: Optional[Dict[str, int]]
    # Intent detection and validation
    detected_intent: Optional[str]
    intent_confidence: Optional[str]
    safety: Optional[Dict[str, Any]]
    # Routing and mode information
    mode: Optional[str]  # "operator", "strategist", "social", "engagement"
    route_confidence: Optional[str]  # "high", "medium", "low"
    route_reason: Optional[str]  # Short label for telemetry
    # Explicit tracking of executed actions for response validation
    executed_actions: Optional[List[Dict[str, Any]]]  # List of {"tool_name": str, "args": dict, "result": str, "success": bool}


def _run_tool_calls(messages: List[BaseMessage], tools_by_name: Dict[str, object]) -> List[ToolMessage]:
    """
    Minimal ToolNode-compatible executor for langgraph installs lacking `langgraph.prebuilt`.
    Executes tool calls present on the last AIMessage and returns ToolMessage list.
    """
    last_msg = messages[-1] if messages else None
    tool_calls = getattr(last_msg, "tool_calls", None) if isinstance(last_msg, AIMessage) else None
    if not tool_calls:
        return []

    out: List[ToolMessage] = []
    for call in tool_calls:
        call = call or {}
        name = (call.get("name") or "").strip()
        args = call.get("args") or {}
        call_id = call.get("id") or "tool_call"
        tool = tools_by_name.get(name)
        if tool is None:
            payload = {"error": f"Unknown tool: {name}", "error_type": "unknown", "retryable": False}
            out.append(ToolMessage(content=json.dumps(payload), tool_call_id=call_id))
            continue

        try:
            # StructuredTool supports .invoke; fall back to .run if needed.
            if hasattr(tool, "invoke"):
                result = tool.invoke(args)
            elif hasattr(tool, "run"):
                result = tool.run(**args)  # type: ignore
            else:
                result = tool(**args)  # type: ignore

            if result is None:
                content = "{}"
            elif isinstance(result, (dict, list)):
                content = json.dumps(result)
            else:
                content = str(result)
            # Ensure content is never empty
            if not content or (isinstance(content, str) and not content.strip()):
                content = "{}"
            out.append(ToolMessage(content=content, tool_call_id=call_id))
        except Exception as e:
            payload = {"error": str(e), "error_type": "unknown", "retryable": False}
            out.append(ToolMessage(content=json.dumps(payload), tool_call_id=call_id))
    return out


def _emit(
    progress_getter: Optional[Callable[[], Optional[Callable[[str, dict], None]]]],
    event: str,
    payload: dict,
) -> None:
    """Call the current progress callback (if any) in a UI-agnostic way."""
    if not progress_getter:
        return

    cb = progress_getter()
    if cb:
        try:
            cb(event, payload)
        except Exception:
            # Progress is best-effort; never break the agent loop.
            pass


def _last_tool_output_for(messages: List[BaseMessage], tool_name: str) -> Optional[str]:
    """
    Return the most recent ToolMessage content associated with a tool call of `tool_name`.
    Matches AIMessage.tool_calls[*].id with ToolMessage.tool_call_id.
    """
    try:
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                for call in reversed(msg.tool_calls or []):
                    if (call or {}).get("name") != tool_name:
                        continue
                    call_id = (call or {}).get("id")
                    if not call_id:
                        continue
                    # Scan forward for the corresponding ToolMessage.
                    for j in range(i + 1, len(messages)):
                        m2 = messages[j]
                        if isinstance(m2, ToolMessage) and getattr(m2, "tool_call_id", None) == call_id:
                            content = getattr(m2, "content", None)
                            return content if isinstance(content, str) else None
    except Exception:
        return None
    return None


def _parse_json_obj(text: Optional[str]) -> Optional[dict]:
    if not text or not isinstance(text, str):
        return None
    try:
        parsed = json.loads(text)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _last_tool_error(messages: List[BaseMessage]) -> Optional[dict]:
    """
    If the last ToolMessage looks like an error payload, return it as a dict.
    Expected shapes:
    - {"error": "...", "error_type": "...", "retryable": bool, ...}
    """
    try:
        for m in reversed(messages or []):
            if not isinstance(m, ToolMessage):
                continue
            content = getattr(m, "content", None)
            if not content:
                continue
            parsed = None
            if isinstance(content, str):
                try:
                    parsed = json.loads(content)
                except Exception:
                    parsed = None
            if isinstance(parsed, dict) and parsed.get("error"):
                return parsed
    except Exception:
        return None
    return None


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    return max(minimum, value)


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except Exception:
        return default
    return max(minimum, value)


def _env_enabled(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _stable_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        return str(value)


def _hash_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8", errors="ignore")).hexdigest()


def _tool_signature(tool_name: str, tool_args: Any) -> str:
    return f"{tool_name}:{_hash_text(_stable_json(tool_args))}"


def _resolve_retry_policy() -> Dict[str, Any]:
    attempts = _env_int("LLM_TOOL_RETRY_ATTEMPTS", 3, minimum=1)
    return {
        "max_retries": max(0, attempts - 1),
        "min_delay_ms": _env_int("LLM_TOOL_RETRY_MIN_DELAY_MS", 400, minimum=0),
        "max_delay_ms": _env_int("LLM_TOOL_RETRY_MAX_DELAY_MS", 30_000, minimum=0),
        "jitter": _env_float("LLM_TOOL_RETRY_JITTER", 0.1, minimum=0.0),
    }


def _extract_retry_after_ms(err: Exception) -> Optional[int]:
    try:
        # Common direct attrs.
        for attr in ("retry_after_ms", "retry_after"):
            raw = getattr(err, attr, None)
            if isinstance(raw, (int, float)) and raw > 0:
                # Heuristic: small values are usually seconds.
                return int(raw * 1000 if raw <= 120 else raw)

        # Telegram-style payloads.
        params = getattr(err, "parameters", None)
        if isinstance(params, dict):
            raw = params.get("retry_after")
            if isinstance(raw, (int, float)) and raw > 0:
                return int(raw * 1000)

        response = getattr(err, "response", None)
        headers = None
        if isinstance(response, dict):
            headers = response.get("headers")
        else:
            headers = getattr(response, "headers", None)
        if headers:
            value = None
            if isinstance(headers, dict):
                value = headers.get("Retry-After") or headers.get("retry-after")
            else:
                value = headers.get("Retry-After") if hasattr(headers, "get") else None
            if isinstance(value, str):
                value = value.strip()
                if value.isdigit():
                    return int(value) * 1000
            if isinstance(value, (int, float)) and value > 0:
                return int(value * 1000)
    except Exception:
        return None
    return None


def _is_transient_error(err: Exception) -> bool:
    transient_types = (TimeoutError, ConnectionError, OSError)
    if isinstance(err, transient_types):
        return True
    text = str(err).lower()
    transient_hints = (
        "429",
        "rate limit",
        "resource exhausted",
        "timeout",
        "timed out",
        "temporarily unavailable",
        "connection reset",
        "connection aborted",
        "service unavailable",
        "try again",
    )
    return any(hint in text for hint in transient_hints)


def _compute_retry_delay_ms(retry_number: int, err: Exception, policy: Dict[str, Any]) -> int:
    retry_after_ms = _extract_retry_after_ms(err)
    if retry_after_ms is not None:
        delay = retry_after_ms
    else:
        base = int(policy["min_delay_ms"]) * (2 ** max(0, retry_number - 1))
        delay = base
    max_delay = int(policy["max_delay_ms"])
    if max_delay > 0:
        delay = min(delay, max_delay)
    jitter = float(policy["jitter"])
    if delay > 0 and jitter > 0:
        span = int(delay * jitter)
        if span > 0:
            delay = max(0, delay + random.randint(-span, span))
    return max(0, int(delay))


def _resolve_loop_policy() -> Dict[str, int | bool]:
    warning = _env_int("LLM_TOOL_LOOP_WARNING_THRESHOLD", 10, minimum=1)
    critical = _env_int("LLM_TOOL_LOOP_CRITICAL_THRESHOLD", 20, minimum=2)
    if critical <= warning:
        critical = warning + 1
    global_threshold = _env_int("LLM_TOOL_LOOP_GLOBAL_THRESHOLD", 30, minimum=3)
    if global_threshold <= critical:
        global_threshold = critical + 1
    return {
        "enabled": _env_enabled("LLM_TOOL_LOOP_DETECTION_ENABLED", default=True),
        "history_size": _env_int("LLM_TOOL_LOOP_HISTORY_SIZE", 30, minimum=5),
        "warning_threshold": warning,
        "critical_threshold": critical,
        "global_threshold": global_threshold,
        "warning_bucket_size": _env_int("LLM_TOOL_LOOP_WARNING_BUCKET_SIZE", 10, minimum=1),
    }


def _count_tail_same_signature(history: List[dict], signature: str) -> int:
    count = 0
    for entry in reversed(history):
        if entry.get("signature") != signature:
            break
        count += 1
    return count


def _count_tail_same_result(history: List[dict], signature: str) -> int:
    count = 0
    result_hash = None
    for entry in reversed(history):
        if entry.get("signature") != signature:
            break
        cur = entry.get("result_hash")
        if not cur:
            break
        if result_hash is None:
            result_hash = cur
        if cur != result_hash:
            break
        count += 1
    return count


def _count_ping_pong(history: List[dict], current_signature: str) -> int:
    signatures = [str(entry.get("signature") or "") for entry in history if entry.get("signature")]
    signatures.append(current_signature)
    if len(signatures) < 3:
        return 0

    a = signatures[-1]
    b = signatures[-2]
    if not a or not b or a == b:
        return 0

    streak = 2
    expected = a
    for sig in reversed(signatures[:-2]):
        if sig != expected:
            break
        streak += 1
        expected = b if expected == a else a
    return streak


def _should_emit_loop_warning(
    warning_buckets: Dict[str, int],
    warning_key: str,
    count: int,
    bucket_size: int,
) -> bool:
    bucket = max(1, count // max(1, bucket_size))
    last_bucket = warning_buckets.get(warning_key, 0)
    if bucket <= last_bucket:
        return False
    warning_buckets[warning_key] = bucket
    if len(warning_buckets) > 256:
        oldest_key = next(iter(warning_buckets))
        warning_buckets.pop(oldest_key, None)
    return True


def _maybe_detect_loop(
    tool_name: str,
    signature: str,
    history: List[dict],
    warning_buckets: Dict[str, int],
) -> Optional[dict]:
    policy = _resolve_loop_policy()
    if not bool(policy["enabled"]):
        return None

    same_count = _count_tail_same_signature(history, signature) + 1
    no_progress_count = _count_tail_same_result(history, signature) + 1
    ping_pong_count = _count_ping_pong(history, signature)

    if no_progress_count >= int(policy["global_threshold"]):
        return {
            "level": "critical",
            "detector": "global_circuit_breaker",
            "count": no_progress_count,
            "message": (
                f"CRITICAL: {tool_name} repeated identical no-progress outcomes "
                f"{no_progress_count} times. Execution blocked to prevent runaway loops."
            ),
        }

    if (
        no_progress_count >= int(policy["critical_threshold"])
        or same_count >= int(policy["critical_threshold"])
        or ping_pong_count >= int(policy["critical_threshold"])
    ):
        detector = "ping_pong" if ping_pong_count >= int(policy["critical_threshold"]) else "generic_repeat"
        count = max(no_progress_count, same_count, ping_pong_count)
        return {
            "level": "critical",
            "detector": detector,
            "count": count,
            "message": (
                f"CRITICAL: detected repeated tool-call loop for {tool_name} "
                f"({count} consecutive patterns). Execution blocked."
            ),
        }

    if (
        no_progress_count >= int(policy["warning_threshold"])
        or same_count >= int(policy["warning_threshold"])
        or ping_pong_count >= int(policy["warning_threshold"])
    ):
        detector = "ping_pong" if ping_pong_count >= int(policy["warning_threshold"]) else "generic_repeat"
        count = max(no_progress_count, same_count, ping_pong_count)
        warning_key = f"{detector}:{tool_name}:{signature}"
        if _should_emit_loop_warning(
            warning_buckets,
            warning_key,
            count,
            int(policy["warning_bucket_size"]),
        ):
            return {
                "level": "warning",
                "detector": detector,
                "count": count,
                "message": (
                    f"WARNING: potential tool-call loop for {tool_name} "
                    f"({count} consecutive patterns)."
                ),
            }
    return None


def _invoke_tool(tool: object, args: dict):
    if hasattr(tool, "invoke"):
        return tool.invoke(args)
    if hasattr(tool, "run"):
        return tool.run(**args)  # type: ignore
    return tool(**args)  # type: ignore


def _result_to_content(result: Any) -> str:
    if result is None:
        return "{}"
    if isinstance(result, (dict, list)):
        content = json.dumps(result)
    else:
        content = str(result)
    return content if (content and content.strip()) else "{}"


def _execute_tool_calls_with_policies(
    tool_calls: List[dict],
    tools_by_name: Dict[str, object],
    retry_counts: Dict[str, int],
    call_history: List[dict],
    warning_buckets: Dict[str, int],
    progress_getter: Optional[Callable[[], Optional[Callable[[str, dict], None]]]],
    iteration: int,
) -> tuple[List[ToolMessage], Dict[str, int], List[dict], Dict[str, int]]:
    results: List[ToolMessage] = []
    retry_policy = _resolve_retry_policy()
    loop_policy = _resolve_loop_policy()

    for call in tool_calls or []:
        call = call or {}
        tool_name = (call.get("name") or "").strip()
        tool_args = call.get("args") or {}
        call_id = call.get("id") or "tool_call"
        signature = _tool_signature(tool_name, tool_args)

        loop_signal = _maybe_detect_loop(tool_name, signature, call_history, warning_buckets)
        if loop_signal and loop_signal.get("level") == "critical":
            payload = {
                "error": loop_signal.get("message"),
                "error_type": "loop_detected",
                "retryable": False,
                "retried": False,
                "detector": loop_signal.get("detector"),
                "count": loop_signal.get("count"),
            }
            content = json.dumps(payload)
            results.append(ToolMessage(content=content, tool_call_id=call_id))
            call_history.append(
                {
                    "signature": signature,
                    "result_hash": _hash_text(content),
                    "tool_name": tool_name,
                }
            )
            continue
        if loop_signal and loop_signal.get("level") == "warning":
            logger.warning(
                f"Potential tool loop: {loop_signal.get('message')} "
                f"(tool={tool_name}, count={loop_signal.get('count')})"
            )

        tool_obj = tools_by_name.get(tool_name)
        if tool_obj is None:
            payload = {"error": f"Unknown tool: {tool_name}", "error_type": "unknown", "retryable": False}
            content = json.dumps(payload)
            results.append(ToolMessage(content=content, tool_call_id=call_id))
            call_history.append(
                {
                    "signature": signature,
                    "result_hash": _hash_text(content),
                    "tool_name": tool_name,
                }
            )
            continue

        retries_used = int(retry_counts.get(call_id, 0))
        while True:
            try:
                result = _invoke_tool(tool_obj, tool_args)
                content = _result_to_content(result)
                results.append(ToolMessage(content=content, tool_call_id=call_id))
                call_history.append(
                    {
                        "signature": signature,
                        "result_hash": _hash_text(content),
                        "tool_name": tool_name,
                    }
                )
                break
            except Exception as e:
                transient = _is_transient_error(e)
                can_retry = transient and retries_used < int(retry_policy["max_retries"])
                if can_retry:
                    retries_used += 1
                    retry_counts[call_id] = retries_used
                    delay_ms = _compute_retry_delay_ms(retries_used, e, retry_policy)
                    _emit(
                        progress_getter,
                        "tool_retry",
                        {
                            "iteration": iteration,
                            "tool_call_id": call_id,
                            "attempt": retries_used,
                            "delay_ms": delay_ms,
                        },
                    )
                    if delay_ms > 0:
                        time.sleep(delay_ms / 1000.0)
                    continue

                retryable = transient and retries_used < int(retry_policy["max_retries"])
                payload = {
                    "error": str(e),
                    "error_type": "transient" if transient else "unknown",
                    "retryable": retryable,
                    "retried": retries_used > 0,
                }
                retry_after_ms = _extract_retry_after_ms(e)
                if retry_after_ms is not None:
                    payload["retry_after_ms"] = retry_after_ms
                content = json.dumps(payload)
                results.append(ToolMessage(content=content, tool_call_id=call_id))
                call_history.append(
                    {
                        "signature": signature,
                        "result_hash": _hash_text(content),
                        "tool_name": tool_name,
                    }
                )
                break

    history_size = int(loop_policy["history_size"])
    if history_size > 0 and len(call_history) > history_size:
        call_history = call_history[-history_size:]
    return results, retry_counts, call_history, warning_buckets


def _parse_plan(text: str) -> Plan:
    # Be forgiving: allow fenced JSON or extra text.
    cleaned = (text or "").strip()
    if "```" in cleaned:
        # take first fenced block
        parts = cleaned.split("```")
        if len(parts) >= 2:
            cleaned = parts[1].strip()
            # strip possible language tag line
            if "\n" in cleaned and cleaned.split("\n", 1)[0].lower() in {"json"}:
                cleaned = cleaned.split("\n", 1)[1].strip()
    return Plan.model_validate_json(cleaned)


def _strip_thought_signatures(content: Any) -> Any:
    """
    Remove thought-signature metadata from AIMessage content before sending to the API.

    Gemini 3 models embed a cryptographic `thought_signature` in the response parts
    (stored by langchain-google-genai as `extras: {signature: ...}`).  When those
    parts are passed back in a subsequent turn, the signature may be rejected as
    invalid by the API ("Thought signature is not valid").  Stripping `extras` from
    all content parts avoids this while keeping the visible text intact.

    For content parts that contain ONLY a signature and no text (pure thought blocks),
    the entire part is dropped so the messages list stays API-compatible.
    """
    if not isinstance(content, list):
        return content
    cleaned = []
    for part in content:
        if not isinstance(part, dict):
            cleaned.append(part)
            continue
        part_copy = {k: v for k, v in part.items() if k != "extras"}
        # Drop parts that had ONLY extras and no meaningful text/data
        if not part_copy or (len(part_copy) == 1 and part_copy.get("type") == "text" and not part_copy.get("text", "").strip()):
            continue
        cleaned.append(part_copy)
    return cleaned if cleaned else content


def _ensure_messages_have_content(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Ensure all messages have non-empty content to prevent Gemini API errors.

    Also strips Gemini 3 thought-signature metadata (`extras`) from AIMessage
    content parts to prevent "Thought signature is not valid" errors on multi-turn
    calls where prior thinking blocks are passed back to the model.

    Gemini API requires each message to have at least one "parts" field (non-empty content).
    This function ensures SystemMessage and AIMessage have at least minimal content.
    """
    validated = []
    for msg in messages:
        content = getattr(msg, "content", None)

        # Strip thought signatures from AIMessage list content before API submission.
        if isinstance(msg, AIMessage) and isinstance(content, list):
            clean_content = _strip_thought_signatures(content)
            tool_calls = getattr(msg, "tool_calls", None)
            if not clean_content or (isinstance(clean_content, list) and not clean_content):
                # All parts were stripped — keep a placeholder
                if tool_calls:
                    validated.append(AIMessage(content="(calling tool)", tool_calls=tool_calls))
                else:
                    validated.append(AIMessage(content=" "))
            else:
                validated.append(AIMessage(content=clean_content, tool_calls=tool_calls or []))
            continue

        # Check if content is empty or None (only for SystemMessage and AIMessage)
        if isinstance(msg, (SystemMessage, AIMessage)) and (not content or (isinstance(content, str) and not content.strip())):
            if isinstance(msg, SystemMessage):
                validated.append(SystemMessage(content=" "))
            elif isinstance(msg, AIMessage):
                tool_calls = getattr(msg, "tool_calls", None)
                if tool_calls:
                    validated.append(AIMessage(content="(calling tool)", tool_calls=tool_calls))
                else:
                    validated.append(AIMessage(content=" "))
        else:
            validated.append(msg)
    return validated


def _is_google_genai_runnable(runnable: object) -> bool:
    """
    Best-effort detection for ChatGoogleGenerativeAI and wrapped/bound variants.
    """
    current = runnable
    for _ in range(6):
        module_name = getattr(getattr(current, "__class__", object), "__module__", "")
        if "langchain_google_genai" in module_name:
            return True
        bound = getattr(current, "bound", None)
        if bound is None:
            break
        current = bound
    return False


def _invoke_model(model: Runnable, messages: List[BaseMessage]):
    """
    Invoke model with provider-specific safeguards.

    For Gemini/Google GenAI, disable SDK Automatic Function Calling (AFC) because
    this agent already manages tool loops itself.
    """
    kwargs: Dict[str, Any] = {}
    if _is_google_genai_runnable(model) and _env_enabled("GEMINI_DISABLE_AFC", True):
        kwargs["automatic_function_calling"] = {"disable": True}
        kwargs["include_thoughts"] = False
    try:
        return model.invoke(messages, **kwargs)
    except TypeError:
        # If a backend rejects extra kwargs, fall back to plain invoke.
        return model.invoke(messages)


def create_agent_graph(
    tools: Sequence,
    model: Runnable,
    max_iterations: int = 6,
    progress_getter: Optional[Callable[[], Optional[Callable[[str, dict], None]]]] = None,
):
    """
    Build a LangGraph app that can iterate between the LLM and tools.

    Args:
        tools: LangChain tools to expose.
        model: Chat model (will be bound to tools before invocation).
        max_iterations: Hard cap to prevent runaway loops.
        progress_getter: Optional callable returning a per-invoke progress callback.

    Returns:
        A compiled LangGraph app.
    """
    tool_node = _ToolNode(tools) if _ToolNode else None
    tools_by_name = {getattr(t, "name", ""): t for t in tools if getattr(t, "name", "")}
    model_with_tools = model.bind_tools(tools)

    graph = StateGraph(AgentState)

    def call_agent(state: AgentState) -> AgentState:
        validated_messages = _ensure_messages_have_content(state["messages"])
        _track_llm_call("agent", "model_with_tools")
        result = _invoke_model(model_with_tools, validated_messages)
        new_iteration = state["iteration"] + 1
        _emit(
            progress_getter,
            "agent_step",
            {"iteration": new_iteration, "content": getattr(result, "content", None)},
        )
        return {"messages": state["messages"] + [result], "iteration": new_iteration}

    def call_tools(state: AgentState) -> AgentState:
        if tool_node:
            tool_results = tool_node.invoke({"messages": state["messages"]})
            result_messages = tool_results.get("messages", [])
        else:
            result_messages = _run_tool_calls(state["messages"], tools_by_name)
        _emit(
            progress_getter,
            "tool_step",
            {
                "iteration": state["iteration"],
                "tool_results": [
                    getattr(m, "content", None) for m in result_messages if isinstance(m, ToolMessage)
                ],
            },
        )
        return {"messages": state["messages"] + result_messages, "iteration": state["iteration"]}

    def should_continue(state: AgentState):
        if state["iteration"] >= max_iterations:
            return END

        last_msg = state["messages"][-1] if state["messages"] else None
        has_tool_calls = isinstance(last_msg, AIMessage) and getattr(last_msg, "tool_calls", None)
        return "tools" if has_tool_calls else END

    graph.add_node("agent", call_agent)
    graph.add_node("tools", call_tools)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()


def create_plan_execute_graph(
    tools: Sequence,
    planner_model: Runnable,
    responder_model: Runnable,
    planner_prompt: str,
    emit_plan: bool = False,
    max_iterations: int = 6,
    progress_getter: Optional[Callable[[], Optional[Callable[[str, dict], None]]]] = None,
):
    """
    Build a LangGraph app that runs a planner phase first, then executes steps.

    - Planner: produces a structured Plan JSON (no tool calls).
    - Executor: runs one step at a time (tool calls via ToolNode), then responds.
    """
    tool_by_name = {getattr(t, "name", ""): t for t in tools if getattr(t, "name", "")}

    def _required_args_for_tool(tool_obj) -> List[str]:
        """
        Best-effort extraction of required args from a StructuredTool schema.
        Supports both Pydantic v1/v2 styles depending on LangChain version.
        """
        try:
            schema = getattr(tool_obj, "args_schema", None)
            if schema is None:
                return []
            # Pydantic v2
            fields = getattr(schema, "model_fields", None)
            if isinstance(fields, dict):
                required = []
                for name, field in fields.items():
                    try:
                        if getattr(field, "is_required", lambda: False)():
                            required.append(name)
                    except Exception:
                        # Fallback: required if default missing
                        if getattr(field, "default", None) is None and getattr(field, "default_factory", None) is None:
                            required.append(name)
                return required
            # Pydantic v1
            v1_fields = getattr(schema, "__fields__", None)
            if isinstance(v1_fields, dict):
                return [n for n, f in v1_fields.items() if getattr(f, "required", False)]
        except Exception:
            return []
        return []

    required_args_by_tool = {name: _required_args_for_tool(t) for name, t in tool_by_name.items()}

    MUTATION_PREFIXES = ("add_", "create_", "update_", "delete_", "log_")
    
    # Tools that ALWAYS require user confirmation before execution
    ALWAYS_CONFIRM_TOOLS = {"add_promise", "create_promise", "subscribe_template"}
    
    # Tools that require confirmation when intent confidence is NOT high
    # This catches the "کتاب ؟" case where add_action shouldn't fire on ambiguous input
    CONFIRM_ON_LOW_CONFIDENCE_TOOLS = {"add_action", "delete_promise", "delete_action"}

    # Helper functions moved to module level - use the module-level versions

    def _verification_step_for(tool_name: str, tool_args: dict) -> Optional[dict]:
        """
        Heuristic: after a mutation tool, add a lightweight read step to confirm.
        Only returns steps for tools that exist in this app's tool set.
        """
        tool_args = tool_args or {}
        # Skip verification for delete operations (expected to not find the item)
        if tool_name == "delete_promise":
            return None
        if tool_name == "update_setting":
            setting_key = tool_args.get("setting_key")
            if setting_key and "get_setting" in tool_by_name:
                return {
                    "kind": "tool",
                    "purpose": "Verify the updated setting.",
                    "tool_name": "get_setting",
                    "tool_args": {"setting_key": setting_key},
                }
            if "get_settings" in tool_by_name:
                return {
                    "kind": "tool",
                    "purpose": "Verify updated settings.",
                    "tool_name": "get_settings",
                    "tool_args": {},
                }
        if "promise" in (tool_name or ""):
            # Prefer listing promises (stable display) unless we have a dedicated get_promise_report.
            pid = tool_args.get("promise_id")
            if pid and "get_promise_report" in tool_by_name:
                return {
                    "kind": "tool",
                    "purpose": "Verify promise state after the change.",
                    "tool_name": "get_promise_report",
                    "tool_args": {"promise_id": pid},
                }
            if "get_promises" in tool_by_name:
                return {
                    "kind": "tool",
                    "purpose": "Verify the updated promises list.",
                    "tool_name": "get_promises",
                    "tool_args": {},
                }
        if tool_name == "add_action":
            pid = tool_args.get("promise_id")
            if pid and "get_last_action_on_promise" in tool_by_name:
                return {
                    "kind": "tool",
                    "purpose": "Verify the last logged action for the promise.",
                    "tool_name": "get_last_action_on_promise",
                    "tool_args": {"promise_id": pid},
                }
        return None

    # Args that can be inferred or have smart defaults (don't ask user for these)
    INFERABLE_ARGS = {
        "time_spent": 1.0,  # Default to 1 hour when user says "worked on X"
    }
    
    # Args that can be resolved via search (prepend a search step instead of asking)
    SEARCHABLE_ARGS = {"promise_id"}
    
    def _can_infer_missing_args(tool_name: str, missing: List[str], tool_args: dict) -> tuple[bool, dict]:
        """
        Check if missing args can be inferred via defaults or search.
        Returns (can_infer, updated_args_or_prepend_steps).
        """
        updated_args = dict(tool_args)
        still_missing = []
        
        for arg in missing:
            if arg in INFERABLE_ARGS:
                # Apply default value
                updated_args[arg] = INFERABLE_ARGS[arg]
            elif arg in SEARCHABLE_ARGS:
                # This needs a search step prepended - handled separately
                still_missing.append(arg)
            else:
                still_missing.append(arg)
        
        return (len(still_missing) == 0, updated_args, still_missing)
    
    def _create_search_step_for_promise(tool_args: dict) -> Optional[dict]:
        """
        If promise_id is marked as FROM_SEARCH or missing, try to create a search step
        based on any query hints in the args.
        """
        # Check if there's a query hint embedded (planner might put "FROM_SEARCH" as placeholder)
        promise_id = tool_args.get("promise_id", "")
        if promise_id and not _is_from_search(str(promise_id)) and not _parse_from_tool(str(promise_id)):
            return None  # Already has a real promise_id
        
        # Look for any text hint that could be used as search query
        # The planner might include a "query" or similar hint
        query = tool_args.get("_search_query") or tool_args.get("query")
        if not query:
            return None
        
        return {
            "kind": "tool",
            "purpose": f"Find promise matching '{query}'",
            "tool_name": "search_promises",
            "tool_args": {"query": query},
        }

    def _validate_and_repair_plan_steps(plan_steps: List[dict]) -> tuple[List[dict], Dict[int, dict]]:
        """
        Validate planner-provided steps and repair common issues:
        - Unknown tool -> ask_user (only as last resort)
        - Missing required args -> try to infer/default first, then ask_user
        - Mutation tool -> auto-add verify-by-reading step (best-effort)
        
        Philosophy: Prefer action over asking. Use smart defaults when possible.
        """
        pending_meta_by_idx: Dict[int, dict] = {}
        repaired: List[dict] = []

        for i, raw in enumerate(plan_steps or []):
            step = dict(raw or {})
            kind = step.get("kind")

            if kind == "tool":
                tool_name = (step.get("tool_name") or "").strip()
                tool_args = step.get("tool_args") or {}

                if not tool_name or tool_name not in tool_by_name:
                    pending_meta_by_idx[i] = {
                        "reason": "unknown_tool",
                        "tool_name": tool_name,
                        "provided_args": tool_args,
                    }
                    repaired.append(
                        {
                            "kind": "ask_user",
                            "purpose": "Clarify the requested action (unknown tool).",
                            "question": "I'm not sure which action you want me to take. Can you rephrase what you want to do?",
                        }
                    )
                    continue

                required_args = required_args_by_tool.get(tool_name, [])
                missing = [a for a in required_args if a not in tool_args or tool_args.get(a) in (None, "", [])]

                # Special case: promise_id placeholders.
                # We allow promise_id="FROM_SEARCH" iff a prior search step exists in the plan.
                # Otherwise, treat it as missing so we can prepend search or ask the user.
                if (
                    "promise_id" in required_args
                    and _is_from_search(tool_args.get("promise_id", "") or "")
                    and not any(
                        (s or {}).get("kind") == "tool" and (s or {}).get("tool_name") == "search_promises"
                        for s in repaired
                    )
                ):
                    missing.append("promise_id")
                
                if missing:
                    # Try to infer missing args using defaults
                    can_infer, updated_args, still_missing = _can_infer_missing_args(
                        tool_name, missing, tool_args
                    )
                    
                    if can_infer:
                        # All missing args were inferred - update step and continue
                        step["tool_args"] = updated_args
                        repaired.append(step)
                        
                        # Auto verify-by-reading after mutations
                        if tool_name.startswith(MUTATION_PREFIXES):
                            verify = _verification_step_for(tool_name, updated_args)
                            if verify:
                                repaired.append(verify)
                        continue
                    
                    # Check if the only missing arg is promise_id and can be searched
                    if still_missing == ["promise_id"] and "search_promises" in tool_by_name:
                        # Check if there's context that suggests what to search for
                        search_step = _create_search_step_for_promise(tool_args)
                        if search_step:
                            # Prepend search step - the executor will handle chaining
                            repaired.append(search_step)
                            # Update the tool step with inferred args and keep it
                            step["tool_args"] = updated_args
                            step["tool_args"]["promise_id"] = "FROM_SEARCH"  # Placeholder
                            repaired.append(step)
                            continue
                    
                    # Still have unresolvable missing args - must ask user
                    # But be more helpful in the question
                    pending_meta_by_idx[i] = {
                        "reason": "missing_required_args",
                        "tool_name": tool_name,
                        "missing_fields": still_missing,
                        "partial_args": updated_args,
                    }
                    
                    # Create a friendlier question
                    if still_missing == ["promise_id"]:
                        question = (
                            "Which promise/goal should I use for this? "
                            "You can say the name (like 'sport' or 'reading') or the ID (like 'P01')."
                        )
                    elif still_missing == ["time_spent"]:
                        question = "How much time did you spend? (e.g., '2 hours' or '30 minutes')"
                    elif "promise_id" in still_missing and "time_spent" in still_missing:
                        question = (
                            "I need a bit more info:\n"
                            "• Which promise/goal? (name or ID like 'P01')\n"
                            "• How much time did you spend?"
                        )
                    else:
                        fields = ", ".join(still_missing)
                        question = f"To do that, I need: {fields}. Can you provide these?"
                    
                    repaired.append(
                        {
                            "kind": "ask_user",
                            "purpose": f"Get missing info for {tool_name}.",
                            "question": question,
                        }
                    )
                    continue

                # Keep tool step (all args present)
                repaired.append(step)

                # Auto verify-by-reading after mutations (best-effort, capped later)
                if tool_name.startswith(MUTATION_PREFIXES):
                    verify = _verification_step_for(tool_name, tool_args)
                    if verify:
                        repaired.append(verify)

            elif kind in ("respond", "ask_user"):
                repaired.append(step)
            else:
                # Unknown step kind: respond directly
                repaired.append(
                    {
                        "kind": "respond",
                        "purpose": "Respond directly (unknown plan step kind).",
                        "response_hint": "Respond concisely and ask one clarifying question if needed.",
                    }
                )

        # Ensure a respond step exists if the plan doesn't already ask the user.
        if repaired and not any((s.get("kind") == "ask_user") for s in repaired):
            if repaired[-1].get("kind") != "respond":
                repaired.append(
                    {
                        "kind": "respond",
                        "purpose": "Respond to the user after completing tool steps.",
                        "response_hint": "Summarize results briefly and encouragingly. Use emojis for status (✅ done, 🔥 streak).",
                    }
                )

        # Cap to 6 steps to avoid runaway plans.
        if len(repaired) > 6:
            repaired = repaired[:6]

        return repaired, pending_meta_by_idx

    graph = StateGraph(AgentState)

    def planner(state: AgentState) -> AgentState:
        # If the caller already supplied a plan (e.g., tests or resumed execution),
        # don't overwrite it by re-invoking the planner model.
        existing_plan = state.get("plan") or []
        if existing_plan:
            try:
                plan_dicts = [dict(s) for s in existing_plan]
            except Exception:
                plan_dicts = existing_plan  # best effort
            plan_dicts, pending_meta_by_idx = _validate_and_repair_plan_steps(plan_dicts)
            return {
                **state,
                "plan": plan_dicts,
                "pending_meta_by_idx": pending_meta_by_idx,
                "pending_clarification": state.get("pending_clarification"),
                "step_idx": int(state.get("step_idx", 0) or 0),
            }

        messages = list(state.get("messages") or [])
        messages = [SystemMessage(content=planner_prompt)] + messages
        validated_messages = _ensure_messages_have_content(messages)

        _track_llm_call("planner", "planner_model")
        result = _invoke_model(planner_model, validated_messages)
        content = getattr(result, "content", "") or ""

        plan: Optional[Plan] = None
        planner_error: Optional[str] = None
        try:
            plan = _parse_plan(content)
        except Exception as e:
            planner_error = str(e)
            # fallback: always respond
            plan = Plan(
                steps=[
                    PlanStep(
                        kind="respond",
                        purpose="Answer the user directly (planner parsing failed).",
                        response_hint="Be concise and ask one clarifying question if needed.",
                    )
                ]
            )

        plan_dicts = [s.model_dump() for s in plan.steps]
        plan_dicts, pending_meta_by_idx = _validate_and_repair_plan_steps(plan_dicts)

        if emit_plan:
            _emit(
                progress_getter,
                "plan",
                {
                    "steps": [
                        {
                            "kind": s.get("kind"),
                            "purpose": s.get("purpose"),
                            "tool_name": s.get("tool_name"),
                            "tool_args_keys": sorted(list((s.get("tool_args") or {}).keys())),
                        }
                        for s in plan_dicts
                    ],
                    "planner_error": planner_error,
                },
            )

        return {
            "messages": state["messages"],
            "iteration": state.get("iteration", 0),
            "plan": plan_dicts,
            "step_idx": 0,
            "final_response": plan.final_response_if_no_tools,
            "planner_error": planner_error,
            "pending_meta_by_idx": pending_meta_by_idx,
            "pending_clarification": None,
            "detected_intent": plan.detected_intent,
            "intent_confidence": plan.intent_confidence,
            "safety": plan.safety,
        }

    def executor(state: AgentState) -> AgentState:
        # If planner already provided final response and there are no steps, finish.
        if state.get("final_response") and not (state.get("plan") or []):
            return state

        plan = state.get("plan") or []
        idx = int(state.get("step_idx", 0) or 0)

        # If we already have a final response, finish.
        if state.get("final_response"):
            return state

        # If no more steps, use responder model to craft an answer from messages.
        if idx >= len(plan):
            tool_err = _last_tool_error(state["messages"])
            if tool_err:
                hint = (
                    "A tool call failed. Respond with a user-safe, action-oriented message:\n"
                    "1) What I tried (one short sentence)\n"
                    "2) What failed (plain language; no internal traces)\n"
                    "3) Next step (one concrete action): ask for missing info, suggest retry, or provide an alternative\n"
                    "If retryable is true, suggest the user try again.\n"
                    "Keep it friendly and helpful - don't make the user feel bad about the error."
                )
                messages_to_send = _ensure_messages_have_content(state["messages"] + [SystemMessage(content=hint)])
                _track_llm_call("responder_error", "responder_model")
                result = _invoke_model(responder_model, messages_to_send)
            else:
                # Default responder hint for good UX
                default_hint = (
                    "RESPONSE GUIDELINES:\n"
                    "- Be friendly, encouraging, and concise (2-4 sentences max)\n"
                    "- Summarize what was done using natural language\n"
                    "- Use emojis sparingly: ✅ for success, 🔥 for streaks, 📊 for reports\n"
                    "- If showing progress, highlight achievements and encourage continued effort\n"
                    "- End with a subtle prompt for next action if relevant (e.g., 'Keep up the great work!')\n"
                    "- Format lists with bullet points (•) for readability\n"
                    "- Do NOT include raw tool outputs or JSON - summarize in human terms\n"
                    "- Output only the final answer. Never include internal analysis, step-by-step thinking, or a 'thinking process'."
                )
                # Add intent validation if intent was detected
                detected_intent = state.get("detected_intent")
                if detected_intent:
                    default_hint += (
                        f"\n\nVALIDATION: The user's detected intent was '{detected_intent}'. "
                        "Verify that your response aligns with this intent. If the actions taken don't match the intent, "
                        "acknowledge the mismatch and ask one clarifying question instead of asserting success."
                    )
                executed_actions = state.get("executed_actions") or []
                mutation_actions = [a for a in executed_actions if a.get("tool_name", "").startswith(MUTATION_PREFIXES)]
                if mutation_actions:
                    actions_summary = "; ".join([
                        f"{a['tool_name']}({', '.join(f'{k}={v}' for k, v in (a.get('args') or {}).items() if k != 'user_id')}) -> {'success' if a.get('success') else 'failed'}"
                        for a in mutation_actions
                    ])
                    default_hint += (
                        f"\n\nACTIONS EXECUTED: {actions_summary}\n"
                        "CRITICAL: Your response MUST accurately reflect ONLY what was actually executed above. "
                        "Do NOT claim actions were performed if they are not in this list. "
                        "If an action failed, explain what went wrong instead of claiming success."
                    )
                else:
                    default_hint += (
                        "\n\nNOTE: No mutation actions (add/create/update/delete/log) were executed in this turn. "
                        "Do NOT claim any actions were performed. If the user expected an action, "
                        "ask for clarification about what they want to do."
                    )
                messages_to_send = _ensure_messages_have_content(state["messages"] + [SystemMessage(content=default_hint)])
                _track_llm_call("responder_default", "responder_model")
                result = _invoke_model(responder_model, messages_to_send)
            return {
                **state,
                "messages": state["messages"] + [result],
                "final_response": getattr(result, "content", None),
            }

        step = PlanStep.model_validate(plan[idx])
        new_iteration = int(state.get("iteration", 0) or 0) + 1

        if new_iteration > max_iterations:
            # hard stop: respond with best effort
            validated_messages = _ensure_messages_have_content(state["messages"])
            _track_llm_call("responder_max_iter", "responder_model")
            result = _invoke_model(responder_model, validated_messages)
            return {
                **state,
                "messages": state["messages"] + [result],
                "iteration": new_iteration,
                "final_response": getattr(result, "content", None),
            }

        if step.kind == "ask_user":
            pending = (state.get("pending_meta_by_idx") or {}).get(idx)
            return {
                **state,
                "iteration": new_iteration,
                "final_response": step.question or "Could you clarify what you mean?",
                "pending_clarification": pending,
                "step_idx": idx + 1,
            }

        if step.kind == "respond":
            # Add a lightweight instruction message (no tools).
            base_hint = step.response_hint or "Respond to the user based on tool results above."
            
            # Build comprehensive response guidelines
            ux_guidelines = (
                "\n\nRESPONSE STYLE:\n"
                "- Be friendly and encouraging (you're Xaana, a helpful assistant)\n"
                "- Keep it concise: 2-4 sentences for simple actions, up to 6 for reports\n"
                "- Use natural language, not technical jargon\n"
                "- Emojis: ✅ success, 🔥 streaks, 📊 reports, 💪 encouragement (use sparingly)\n"
                "- Format lists with bullet points (•) for readability\n"
                "- Highlight achievements and progress positively\n"
                "- Do NOT output raw JSON or tool responses - summarize them\n"
                "- Output only the final answer. Never include internal analysis, step-by-step thinking, or a 'thinking process'.\n"
                "- Do NOT call any tools in your response\n"
                "- Do NOT include headers like 'Zana:' or 'Xaana:' in your response - the system will add the header automatically"
            )
            
            hint = base_hint + ux_guidelines
            
            # Add intent validation if intent was detected
            detected_intent = state.get("detected_intent")
            if detected_intent:
                hint += (
                    f"\n\nVALIDATION: The user's detected intent was '{detected_intent}'. "
                    "Verify that your response aligns with this intent. If the actions taken don't match the intent, "
                    "acknowledge the mismatch and ask one clarifying question instead of asserting success."
                )
            
            # CRITICAL: Add executed actions validation
            # This ensures the response reflects ONLY what was actually executed
            executed_actions = state.get("executed_actions") or []
            mutation_actions = [a for a in executed_actions if a.get("tool_name", "").startswith(MUTATION_PREFIXES)]
            if mutation_actions:
                actions_summary = "; ".join([
                    f"{a['tool_name']}({', '.join(f'{k}={v}' for k, v in (a.get('args') or {}).items() if k != 'user_id')}) -> {'success' if a.get('success') else 'failed'}"
                    for a in mutation_actions
                ])
                hint += (
                    f"\n\nACTIONS EXECUTED: {actions_summary}\n"
                    "CRITICAL: Your response MUST accurately reflect ONLY what was actually executed above. "
                    "Do NOT claim actions were performed if they are not in this list. "
                    "If an action failed, explain what went wrong instead of claiming success."
                )
            else:
                # No mutation actions were executed (even if read-only tools were called)
                hint += (
                    "\n\nNOTE: No mutation actions (add/create/update/delete/log) were executed in this turn. "
                    "Do NOT claim any actions were performed. If the user expected an action, "
                    "ask for clarification about what they want to do."
                )

            tool_err = _last_tool_error(state["messages"])
            if tool_err:
                err_type = tool_err.get("error_type", "unknown")
                retryable = bool(tool_err.get("retryable"))
                failure_hint = (
                    "\n\nNOTE: A tool call failed. Handle gracefully:\n"
                    "1) Briefly explain what you tried\n"
                    "2) What went wrong (no technical details)\n"
                    "3) Suggest a next step\n"
                    f"Context: error_type={err_type}, retryable={retryable}.\n"
                    "Be reassuring - errors happen!"
                )
                hint = hint + failure_hint
            messages_to_send = _ensure_messages_have_content(state["messages"] + [SystemMessage(content=hint)])
            _track_llm_call("responder_respond_step", "responder_model")
            result = _invoke_model(responder_model, messages_to_send)
            return {
                **state,
                "messages": state["messages"] + [result],
                "iteration": new_iteration,
                "final_response": getattr(result, "content", None),
                "step_idx": idx + 1,
            }

        if step.kind == "tool":
            tool_name = step.tool_name or ""
            tool_args = step.tool_args or {}

            # CRITICAL: Resolve placeholders FIRST before confirmation check
            # This ensures that if a promise creation depends on earlier tool outputs
            # (e.g., resolve_datetime -> add_promise), the stored pending args are resolved.
            
            # Generic placeholder resolution (agent-centric, avoids brittle handler logic):
            # - "FROM_TOOL:<tool_name>:<json_field>" pulls a field from the last tool's JSON output.
            # - "FROM_SEARCH" remains supported as a shorthand for promise selection via search_promises.
            for arg_name, arg_val in list((tool_args or {}).items()):
                if not isinstance(arg_val, str):
                    continue
                _from_tool_parts = _parse_from_tool(arg_val)
                if not _from_tool_parts:
                    continue

                # Parse case-/whitespace-tolerant FROM_TOOL:<tool_name>:<field>
                src_tool, src_field = _from_tool_parts

                src_text = _last_tool_output_for(state.get("messages", []), src_tool)
                if not src_text:
                    continue
                
                obj = _parse_json_obj(src_text)
                resolved = (obj or {}).get(src_field) if obj else None
                
                # If JSON parsing succeeded and field found, use it
                if resolved not in (None, "", [], {}):
                    tool_args[arg_name] = resolved
                # If field is empty or JSON parsing failed, use the string output directly
                # This handles tools like resolve_datetime that return plain strings (e.g., "2026-01-14T00:00:00")
                elif not src_field or not obj:
                    # Tool returned a string (not JSON), use it directly
                    # Strip any error messages that might start with "Could not" or "Error"
                    if src_text.strip() and not src_text.strip().startswith(("Could not", "Error")):
                        tool_args[arg_name] = src_text.strip()
                    else:
                        # Error in tool output, ask user
                        pending = {
                            "reason": "unresolved_placeholder",
                            "tool_name": tool_name,
                            "missing_fields": [arg_name],
                            "partial_args": {k: v for k, v in (tool_args or {}).items() if k != arg_name},
                            "placeholder": arg_val,
                        }
                        question = (
                            f"I couldn't auto-fill `{arg_name}` from the previous `{src_tool}` result.\n"
                            f"Please reply with `{arg_name}: <value>` (or just the value)."
                        )
                        return {
                            **state,
                            "iteration": new_iteration,
                            "final_response": question,
                            "pending_clarification": pending,
                            "step_idx": idx + 1,
                        }
                else:
                    pending = {
                        "reason": "unresolved_placeholder",
                        "tool_name": tool_name,
                        "missing_fields": [arg_name],
                        "partial_args": {k: v for k, v in (tool_args or {}).items() if k != arg_name},
                        "placeholder": arg_val,
                    }
                    question = (
                        f"I couldn't auto-fill `{arg_name}` from the previous `{src_tool}` result.\n"
                        f"Please reply with `{arg_name}: <value>` (or just the value)."
                    )
                    return {
                        **state,
                        "iteration": new_iteration,
                        "final_response": question,
                        "pending_clarification": pending,
                        "step_idx": idx + 1,
                    }

            # Check if previous tool was search_promises with single match, and current step needs promise_id
            if _is_from_search(tool_args.get("promise_id", "") or ""):
                logger.debug(f"Auto-fill: Looking for search_promises result to fill promise_id for {tool_name}")
                # Look for the last search_promises result in messages
                # Check messages in reverse to find the most recent search_promises result
                found_single_match = False
                last_search_output_text: Optional[str] = None
                last_search_output_text = _last_tool_output_for(state.get("messages", []), "search_promises")
                parsed = _parse_json_obj(last_search_output_text)
                if parsed and parsed.get("single_match"):
                    promise_id = parsed.get("promise_id")
                    if promise_id:
                        tool_args["promise_id"] = promise_id
                        found_single_match = True
                        logger.info(f"Auto-fill: Successfully filled promise_id={promise_id} from single_match")

                if not found_single_match:
                    # Dynamic replanning: instead of calling the tool with an unresolved placeholder,
                    # ask the user to pick the intended promise_id (works with existing slot-fill flow).
                    logger.warning(
                        f"Auto-fill: FROM_SEARCH placeholder found but no single_match result located for {tool_name}"
                    )
                    options: List[dict] = []
                    if last_search_output_text:
                        # Extract IDs and (best-effort) titles from the formatted multi-match string.
                        # Example line: "• #P10 **Do sport**"
                        for pid, title in re.findall(r"#([PT]\d+)\s+\*\*(.+?)\*\*", last_search_output_text):
                            options.append({"promise_id": pid, "title": title})
                        if not options:
                            # Fallback: just collect IDs.
                            for pid in re.findall(r"#([PT]\d+)", last_search_output_text):
                                options.append({"promise_id": pid})

                    if options:
                        preview = "\n".join(
                            [f"- {o['promise_id']}: {o.get('title', '').strip() or '(no title)'}" for o in options[:6]]
                        )
                        question = (
                            "I found multiple matching promises. Which one do you mean?\n\n"
                            f"{preview}\n\n"
                            "Reply with the promise ID (e.g., P10)."
                        )
                    else:
                        question = "Which promise should I use? Reply with the promise ID (e.g., P10)."

                    pending = {
                        "reason": "ambiguous_promise_id",
                        "tool_name": tool_name,
                        "missing_fields": ["promise_id"],
                        "partial_args": {k: v for k, v in (tool_args or {}).items() if k != "promise_id"},
                        "options": options,
                    }
                    return {
                        **state,
                        "iteration": new_iteration,
                        "final_response": question,
                        "pending_clarification": pending,
                        "step_idx": idx + 1,
                    }

            # NOW check if confirmation is required (after placeholders are resolved)
            # This ensures stored pending_clarification has resolved tool_args
            is_mutation_tool = tool_name.startswith(MUTATION_PREFIXES)
            # Default to "medium" when planner didn't provide confidence (safer approach).
            # This catches ambiguous inputs like "کتاب ؟" where confidence should not be assumed high.
            intent_confidence = (state.get("intent_confidence") or "medium").lower()
            safety = state.get("safety") or {}
            requires_confirmation = safety.get("requires_confirmation", False)
            
            # Check if this is a tool that needs confirmation on low/medium confidence
            needs_low_confidence_confirm = (
                tool_name in CONFIRM_ON_LOW_CONFIDENCE_TOOLS and 
                intent_confidence in ("low", "medium")
            )
            
            # Always confirm for promise creation tools, OR if existing mutation rule applies,
            # OR if it's a sensitive tool with low/medium confidence
            needs_confirmation = (
                tool_name in ALWAYS_CONFIRM_TOOLS or
                needs_low_confidence_confirm or
                (is_mutation_tool and (intent_confidence == "low" or requires_confirmation))
            )
            
            if needs_confirmation:
                # Build a confirmation question that describes what will happen
                detected_intent = state.get("detected_intent") or "this action"
                action_description = f"perform {str(detected_intent).lower()}"
                if tool_name == "add_action":
                    promise_id = tool_args.get("promise_id", "a promise")
                    time_spent = tool_args.get("time_spent", "some time")
                    action_description = f"log {time_spent} hour(s) on {promise_id}"
                elif tool_name == "create_promise" or tool_name == "add_promise":
                    promise_text = tool_args.get("text", tool_args.get("promise_text", "a promise"))
                    action_description = f"create a new promise: '{promise_text}'"
                elif tool_name == "subscribe_template":
                    template_id = tool_args.get("template_id", "a template")
                    action_description = f"subscribe to template: '{template_id}'"
                elif tool_name == "delete_promise":
                    promise_id = tool_args.get("promise_id", "a promise")
                    action_description = f"delete promise {promise_id}"
                elif tool_name == "update_setting":
                    setting_key = tool_args.get("setting_key", "a setting")
                    setting_value = tool_args.get("setting_value", "")
                    action_description = f"change {setting_key} to {setting_value}"
                else:
                    action_description = f"call {tool_name} with {tool_args}"
                
                question = (
                    f"Just to confirm: you want me to {action_description}, right?\n\n"
                    f"Reply 'yes' or 'confirm' to proceed, or clarify what you actually want."
                )
                
                pending = {
                    "reason": "pre_mutation_confirmation",
                    "tool_name": tool_name,
                    "tool_args": tool_args,  # These are now resolved (placeholders filled)
                    "detected_intent": detected_intent,
                    "intent_confidence": intent_confidence,
                }
                
                return {
                    **state,
                    "iteration": new_iteration,
                    "final_response": question,
                    "pending_clarification": pending,
                    "step_idx": idx,  # Don't advance - we'll retry this step after confirmation
                }

            call_id = f"plan_{idx}_iter_{new_iteration}"
            tool_call = {"name": tool_name, "args": tool_args, "id": call_id, "type": "tool_call"}

            # IMPORTANT:
            # Vertex/Gemini requires each "content" item to include at least one "parts" entry.
            # Some LangChain serializers will drop tool_calls when the model isn't bound to tools,
            # and an empty assistant message (content="") can become a request with missing parts,
            # yielding: "400 Unable to submit request ... must include at least one parts field".
            #
            # We keep a minimal, non-empty content to ensure request validity.
            ai = AIMessage(content="(calling tool)", tool_calls=[tool_call])
            _emit(
                progress_getter,
                "executor_step",
                {"iteration": new_iteration, "step_idx": idx, "kind": "tool", "tool": tool_name},
            )
            return {
                **state,
                "messages": state["messages"] + [ai],
                "iteration": new_iteration,
            }

        # Unknown step kind: skip
        return {**state, "iteration": new_iteration, "step_idx": idx + 1}

    def tools_node(state: AgentState) -> AgentState:
        # Execute last tool calls with retry/backoff and loop safeguards.
        last_msg = state["messages"][-1] if state.get("messages") else None
        last_tool_calls = getattr(last_msg, "tool_calls", None) if last_msg else None
        tool_calls = list(last_tool_calls or []) if isinstance(last_tool_calls, list) else []

        executed_action: Optional[Dict[str, Any]] = None
        if tool_calls:
            last_call = tool_calls[-1] or {}
            executed_action = {
                "tool_name": (last_call.get("name") or "").strip(),
                "args": last_call.get("args") or {},
                "result": None,
                "success": False,
            }

        retry_counts = dict(state.get("tool_retry_counts") or {})
        call_history = list(state.get("tool_call_history") or [])
        warning_buckets = dict(state.get("tool_loop_warning_buckets") or {})

        result_messages, retry_counts, call_history, warning_buckets = _execute_tool_calls_with_policies(
            tool_calls=tool_calls,
            tools_by_name=tool_by_name,
            retry_counts=retry_counts,
            call_history=call_history,
            warning_buckets=warning_buckets,
            progress_getter=progress_getter,
            iteration=int(state.get("iteration", 0) or 0),
        )

        if executed_action and result_messages:
            first_content = getattr(result_messages[0], "content", "") if result_messages else ""
            is_error = False
            if first_content:
                parsed = _parse_json_obj(first_content)
                is_error = bool(isinstance(parsed, dict) and parsed.get("error"))
            executed_action["result"] = first_content[:500] if first_content else ""
            executed_action["success"] = not is_error

        _emit(
            progress_getter,
            "tool_step",
            {
                "iteration": state.get("iteration", 0),
                "tool_results": [
                    getattr(m, "content", None) for m in result_messages if isinstance(m, ToolMessage)
                ],
            },
        )

        existing_actions = list(state.get("executed_actions") or [])
        if executed_action:
            existing_actions.append(executed_action)

        return {
            **state,
            "messages": state["messages"] + result_messages,
            "step_idx": int(state.get("step_idx", 0) or 0) + 1,
            "tool_retry_counts": retry_counts,
            "tool_call_history": call_history,
            "tool_loop_warning_buckets": warning_buckets,
            "executed_actions": existing_actions,
        }

    def should_continue(state: AgentState):
        if state.get("final_response"):
            return END
        last_msg = state["messages"][-1] if state.get("messages") else None
        has_tool_calls = isinstance(last_msg, AIMessage) and getattr(last_msg, "tool_calls", None)
        # Always execute pending tool calls, even if we're at the iteration cap,
        # otherwise we can stop with "(calling tool)" as the last message.
        if has_tool_calls:
            return "tools"
        if int(state.get("iteration", 0) or 0) >= max_iterations:
            return END
        return "executor"

    graph.add_node("planner", planner)
    graph.add_node("executor", executor)
    graph.add_node("tools", tools_node)
    graph.set_entry_point("planner")
    graph.add_edge("planner", "executor")
    graph.add_conditional_edges("executor", should_continue, {"tools": "tools", "executor": "executor", END: END})
    graph.add_edge("tools", "executor")

    return graph.compile()


def create_routed_plan_execute_graph(
    tools: Sequence,
    router_model: Runnable,
    planner_model: Runnable,
    responder_model: Runnable,
    router_prompt: str,
    get_planner_prompt_for_mode: Callable[[str], str],
    get_system_message_for_mode: Optional[Callable[[Optional[str], Optional[str], Optional[str]], SystemMessage]] = None,
    emit_plan: bool = False,
    max_iterations: int = 6,
    progress_getter: Optional[Callable[[], Optional[Callable[[str, dict], None]]]] = None,
):
    """
    Build a LangGraph app with routing: router → mode-specific planner → executor.
    
    - Router: classifies user message into mode (operator/strategist/social/engagement)
    - Planner: mode-aware planning (uses mode-specific prompt)
    - Executor: executes plan with mode guardrails
    """
    tool_by_name = {getattr(t, "name", ""): t for t in tools if getattr(t, "name", "")}
    
    MUTATION_PREFIXES = ("add_", "create_", "update_", "delete_", "log_")
    ALWAYS_CONFIRM_TOOLS = {"add_promise", "create_promise", "subscribe_template"}
    
    # Tools that require confirmation when intent confidence is NOT high
    CONFIRM_ON_LOW_CONFIDENCE_TOOLS = {"add_action", "delete_promise", "delete_action"}
    
    # Allowed mutation tools per mode
    ALLOWED_MUTATIONS_BY_MODE = {
        "operator": set(),  # Empty set means all mutations allowed
        "strategist": set(),  # Empty set but executor will block all mutations
        "social": {"follow", "unfollow"},  # Only social mutations
        "engagement": set(),  # No mutations allowed
    }
    
    from langchain_core.output_parsers import JsonOutputParser
    router_parser = JsonOutputParser(pydantic_object=RouteDecision)
    
    graph = StateGraph(AgentState)
    
    def router(state: AgentState) -> AgentState:
        """Route user message to appropriate agent mode."""
        messages = list(state.get("messages") or [])
        # Get user message (last HumanMessage)
        user_msg = None
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                user_msg = msg
                break
        
        if not user_msg:
            # Fallback to operator if no user message found
            return {
                **state,
                "mode": "operator",
                "route_confidence": "low",
                "route_reason": "no_user_message",
            }
        
        # Build router context (minimal: just user message + recent conversation summary if available)
        router_messages = [
            SystemMessage(content=router_prompt),
            user_msg,
        ]
        
        validated_messages = _ensure_messages_have_content(router_messages)
        _track_llm_call("router", "router_model")
        result = _invoke_model(router_model, validated_messages)
        content = message_content_to_str(getattr(result, "content", "") or "")
        
        route_decision: Optional[RouteDecision] = None
        try:
            parsed = router_parser.parse(content)
            # JsonOutputParser may return a dict, convert to RouteDecision if needed
            if isinstance(parsed, dict):
                route_decision = RouteDecision(**parsed)
            elif isinstance(parsed, RouteDecision):
                route_decision = parsed
            else:
                raise ValueError(f"Unexpected parser output type: {type(parsed)}")
        except Exception as e:
            logger.warning(f"Router parsing failed: {e}, defaulting to operator")
            route_decision = RouteDecision(mode="operator", confidence="low", reason="parsing_failed")
        
        mode = route_decision.mode if route_decision else "operator"
        confidence = route_decision.confidence if route_decision else "low"
        reason = route_decision.reason if route_decision else "fallback"
        
        _emit(
            progress_getter,
            "route",
            {
                "mode": mode,
                "confidence": confidence,
                "reason": reason,
            },
        )
        
        return {
            **state,
            "mode": mode,
            "route_confidence": confidence,
            "route_reason": reason,
        }
    
    # Reuse planner and executor logic, but make them mode-aware
    # Helper functions are at module level - use them directly
    
    # Need to define validation functions here since they depend on tool_by_name
    def _required_args_for_tool_local(tool_obj) -> List[str]:
        """Best-effort extraction of required args from a StructuredTool schema."""
        try:
            schema = getattr(tool_obj, "args_schema", None)
            if schema is None:
                return []
            fields = getattr(schema, "model_fields", None)
            if isinstance(fields, dict):
                required = []
                for name, field in fields.items():
                    try:
                        if getattr(field, "is_required", lambda: False)():
                            required.append(name)
                    except Exception:
                        if getattr(field, "default", None) is None and getattr(field, "default_factory", None) is None:
                            required.append(name)
                return required
            v1_fields = getattr(schema, "__fields__", None)
            if isinstance(v1_fields, dict):
                return [n for n, f in v1_fields.items() if getattr(f, "required", False)]
        except Exception:
            return []
        return []

    required_args_by_tool = {name: _required_args_for_tool_local(t) for name, t in tool_by_name.items()}
    
    def _verification_step_for(tool_name: str, tool_args: dict) -> Optional[dict]:
        """Heuristic: after a mutation tool, add a lightweight read step to confirm."""
        tool_args = tool_args or {}
        if tool_name == "delete_promise":
            return None
        if tool_name == "update_setting":
            setting_key = tool_args.get("setting_key")
            if setting_key and "get_setting" in tool_by_name:
                return {
                    "kind": "tool",
                    "purpose": "Verify the updated setting.",
                    "tool_name": "get_setting",
                    "tool_args": {"setting_key": setting_key},
                }
            if "get_settings" in tool_by_name:
                return {
                    "kind": "tool",
                    "purpose": "Verify updated settings.",
                    "tool_name": "get_settings",
                    "tool_args": {},
                }
        if "promise" in (tool_name or ""):
            pid = tool_args.get("promise_id")
            if pid and "get_promise_report" in tool_by_name:
                return {
                    "kind": "tool",
                    "purpose": "Verify promise state after the change.",
                    "tool_name": "get_promise_report",
                    "tool_args": {"promise_id": pid},
                }
            if "get_promises" in tool_by_name:
                return {
                    "kind": "tool",
                    "purpose": "Verify the updated promises list.",
                    "tool_name": "get_promises",
                    "tool_args": {},
                }
        if tool_name == "add_action":
            pid = tool_args.get("promise_id")
            if pid and "get_last_action_on_promise" in tool_by_name:
                return {
                    "kind": "tool",
                    "purpose": "Verify the last logged action for the promise.",
                    "tool_name": "get_last_action_on_promise",
                    "tool_args": {"promise_id": pid},
                }
        return None
    
    INFERABLE_ARGS = {"time_spent": 1.0}
    SEARCHABLE_ARGS = {"promise_id"}
    
    def _can_infer_missing_args(tool_name: str, missing: List[str], tool_args: dict) -> tuple[bool, dict, List[str]]:
        """Check if missing args can be inferred via defaults or search."""
        updated_args = dict(tool_args)
        still_missing = []
        for arg in missing:
            if arg in INFERABLE_ARGS:
                updated_args[arg] = INFERABLE_ARGS[arg]
            elif arg in SEARCHABLE_ARGS:
                still_missing.append(arg)
            else:
                still_missing.append(arg)
        return (len(still_missing) == 0, updated_args, still_missing)
    
    def _create_search_step_for_promise(tool_args: dict) -> Optional[dict]:
        """If promise_id is marked as FROM_SEARCH or missing, try to create a search step."""
        promise_id = tool_args.get("promise_id", "")
        if promise_id and not _is_from_search(str(promise_id)) and not _parse_from_tool(str(promise_id)):
            return None
        query = tool_args.get("_search_query") or tool_args.get("query")
        if not query:
            return None
        return {
            "kind": "tool",
            "purpose": f"Find promise matching '{query}'",
            "tool_name": "search_promises",
            "tool_args": {"query": query},
        }
    
    def _validate_and_repair_plan_steps(plan_steps: List[dict]) -> tuple[List[dict], Dict[int, dict]]:
        """Validate planner-provided steps and repair common issues."""
        pending_meta_by_idx: Dict[int, dict] = {}
        repaired: List[dict] = []
        for i, raw in enumerate(plan_steps or []):
            step = dict(raw or {})
            kind = step.get("kind")
            if kind == "tool":
                tool_name = (step.get("tool_name") or "").strip()
                tool_args = step.get("tool_args") or {}
                if not tool_name or tool_name not in tool_by_name:
                    pending_meta_by_idx[i] = {
                        "reason": "unknown_tool",
                        "tool_name": tool_name,
                        "provided_args": tool_args,
                    }
                    repaired.append({
                        "kind": "ask_user",
                        "purpose": "Clarify the requested action (unknown tool).",
                        "question": "I'm not sure which action you want me to take. Can you rephrase what you want to do?",
                    })
                    continue
                required_args = required_args_by_tool.get(tool_name, [])
                missing = [a for a in required_args if a not in tool_args or tool_args.get(a) in (None, "", [])]
                if (
                    "promise_id" in required_args
                    and _is_from_search(tool_args.get("promise_id", "") or "")
                    and not any(
                        (s or {}).get("kind") == "tool" and (s or {}).get("tool_name") == "search_promises"
                        for s in repaired
                    )
                ):
                    missing.append("promise_id")
                if missing:
                    can_infer, updated_args, still_missing = _can_infer_missing_args(tool_name, missing, tool_args)
                    if can_infer:
                        step["tool_args"] = updated_args
                        repaired.append(step)
                        if tool_name.startswith(MUTATION_PREFIXES):
                            verify = _verification_step_for(tool_name, updated_args)
                            if verify:
                                repaired.append(verify)
                        continue
                    if still_missing == ["promise_id"] and "search_promises" in tool_by_name:
                        search_step = _create_search_step_for_promise(tool_args)
                        if search_step:
                            repaired.append(search_step)
                            step["tool_args"] = updated_args
                            step["tool_args"]["promise_id"] = "FROM_SEARCH"
                            repaired.append(step)
                            continue
                    pending_meta_by_idx[i] = {
                        "reason": "missing_required_args",
                        "tool_name": tool_name,
                        "missing_fields": still_missing,
                        "partial_args": updated_args,
                    }
                    if still_missing == ["promise_id"]:
                        question = "Which promise/goal should I use for this? You can say the name (like 'sport' or 'reading') or the ID (like 'P01')."
                    elif still_missing == ["time_spent"]:
                        question = "How much time did you spend? (e.g., '2 hours' or '30 minutes')"
                    else:
                        fields = ", ".join(still_missing)
                        question = f"To do that, I need: {fields}. Can you provide these?"
                    repaired.append({
                        "kind": "ask_user",
                        "purpose": f"Get missing info for {tool_name}.",
                        "question": question,
                    })
                    continue
                repaired.append(step)
                if tool_name.startswith(MUTATION_PREFIXES):
                    verify = _verification_step_for(tool_name, tool_args)
                    if verify:
                        repaired.append(verify)
            elif kind in ("respond", "ask_user"):
                repaired.append(step)
            else:
                repaired.append({
                    "kind": "respond",
                    "purpose": "Respond directly (unknown plan step kind).",
                    "response_hint": "Respond concisely and ask one clarifying question if needed.",
                })
        if repaired and not any((s.get("kind") == "ask_user") for s in repaired):
            if repaired[-1].get("kind") != "respond":
                repaired.append({
                    "kind": "respond",
                    "purpose": "Respond to the user after completing tool steps.",
                    "response_hint": "Summarize results briefly and encouragingly. Use emojis for status (✅ done, 🔥 streak).",
                })
        if len(repaired) > 6:
            repaired = repaired[:6]
        return repaired, pending_meta_by_idx
    
    def _get_system_message_for_response(mode: str) -> Optional[SystemMessage]:
        if not get_system_message_for_mode:
            return None
        from llms.tool_wrappers import _current_user_id, _current_user_language
        user_id = _current_user_id.get()
        user_language = _current_user_language.get()
        return get_system_message_for_mode(user_id, mode, user_language)

    def _last_user_text(messages: List[BaseMessage]) -> str:
        """Return the latest human message text (best effort)."""
        for msg in reversed(messages or []):
            if isinstance(msg, HumanMessage):
                content = getattr(msg, "content", "")
                return "" if content is None else str(content)
        return ""

    def _strategy_read_only_recovery_step_for_mismatch(user_text: str) -> Optional[dict]:
        """
        Recover when strategist mode receives a mutation step for a query-style message.
        This avoids mode-switch prompts for questions like "how many promises do I have?".
        """
        text = (user_text or "").strip().lower()
        if not text:
            return None

        asks_count = bool(
            re.search(r"\bhow many\b.*\bpromises?\b", text)
            or re.search(r"\bnumber of\b.*\bpromises?\b", text)
            or re.search(r"\bcount\b.*\bpromises?\b", text)
            or re.search(r"\bpromises?\b.*\bdo i have\b", text)
        )
        if asks_count:
            if "count_promises" in tool_by_name:
                return {
                    "kind": "tool",
                    "purpose": "Count current promises for the user.",
                    "tool_name": "count_promises",
                    "tool_args": {},
                }
            if "get_promises" in tool_by_name:
                return {
                    "kind": "tool",
                    "purpose": "Get current promises for counting.",
                    "tool_name": "get_promises",
                    "tool_args": {},
                }

        asks_list = bool(
            re.search(r"\b(my|show|list|what are)\b.*\bpromises?\b", text)
            or re.search(r"\bpromises?\b.*\b(list|show)\b", text)
        )
        if asks_list and "get_promises" in tool_by_name:
            return {
                "kind": "tool",
                "purpose": "Fetch current promises for the user.",
                "tool_name": "get_promises",
                "tool_args": {},
            }

        return None

    def planner(state: AgentState) -> AgentState:
        mode = state.get("mode") or "operator"
        mode_prompt = get_planner_prompt_for_mode(mode)

        # If the caller already supplied a plan (e.g., resumed execution),
        # don't overwrite it by re-invoking the planner model.
        existing_plan = state.get("plan") or []
        if existing_plan:
            try:
                plan_dicts = [dict(s) for s in existing_plan]
            except Exception:
                plan_dicts = existing_plan  # best effort
            plan_dicts, pending_meta_by_idx = _validate_and_repair_plan_steps(plan_dicts)
            return {
                **state,
                "plan": plan_dicts,
                "pending_meta_by_idx": pending_meta_by_idx,
                "pending_clarification": state.get("pending_clarification"),
                "step_idx": int(state.get("step_idx", 0) or 0),
            }
        
        messages = list(state.get("messages") or [])
        
        # Build combined system message: mode-specific planner prompt + full user context
        system_parts = [mode_prompt]
        
        if get_system_message_for_mode:
            # Extract user_id from context var (set by llm_handler before invoke)
            from llms.tool_wrappers import _current_user_id, _current_user_language
            user_id = _current_user_id.get()
            user_language = _current_user_language.get()
            full_system_msg = get_system_message_for_mode(user_id, mode, user_language)
            # Combine: mode prompt first, then full system context (which includes tools overview)
            # The full system message already has the base personality, so we prepend mode directive
            system_parts.append(full_system_msg.content)
        else:
            # Fallback: just use mode-specific prompt
            pass
        
        combined_system_content = "\n\n".join(system_parts)
        messages = [SystemMessage(content=combined_system_content)] + messages
        
        validated_messages = _ensure_messages_have_content(messages)
        _track_llm_call("routed_planner", "planner_model")
        result = _invoke_model(planner_model, validated_messages)
        content = getattr(result, "content", "") or ""

        plan: Optional[Plan] = None
        planner_error: Optional[str] = None
        try:
            plan = _parse_plan(content)
        except Exception as e:
            planner_error = str(e)
            plan = Plan(
                steps=[
                    PlanStep(
                        kind="respond",
                        purpose="Answer the user directly (planner parsing failed).",
                        response_hint="Be concise and ask one clarifying question if needed.",
                    )
                ]
            )

        plan_dicts = [s.model_dump() for s in plan.steps]
        plan_dicts, pending_meta_by_idx = _validate_and_repair_plan_steps(plan_dicts)

        if emit_plan:
            _emit(
                progress_getter,
                "plan",
                {
                    "steps": [
                        {
                            "kind": s.get("kind"),
                            "purpose": s.get("purpose"),
                            "tool_name": s.get("tool_name"),
                            "tool_args_keys": sorted(list((s.get("tool_args") or {}).keys())),
                        }
                        for s in plan_dicts
                    ],
                    "planner_error": planner_error,
                    "mode": mode,
                },
            )

        return {
            "messages": state["messages"],
            "iteration": state.get("iteration", 0),
            "plan": plan_dicts,
            "step_idx": 0,
            "final_response": plan.final_response_if_no_tools,
            "planner_error": planner_error,
            "pending_meta_by_idx": pending_meta_by_idx,
            "pending_clarification": None,
            "detected_intent": plan.detected_intent,
            "intent_confidence": plan.intent_confidence,
            "safety": plan.safety,
        }
    
    def executor(state: AgentState) -> AgentState:
        mode = state.get("mode") or "operator"
        
        # Engagement mode: respond conversationally but allow memory tools
        if mode == "engagement":
            memory_tool_names = {"memory_search", "memory_get", "memory_write", "web_search", "web_fetch"}
            memory_tools = [t for t in tools if getattr(t, "name", "") in memory_tool_names]
            system_msg = _get_system_message_for_response(mode)
            base_messages = state["messages"]
            if system_msg:
                base_messages = [system_msg] + base_messages
            messages_to_send = _ensure_messages_have_content(base_messages)
            engagement_hint = (
                "You are Xaana, a friendly assistant. The user is just chatting. "
                "Respond warmly, with humor if appropriate, and keep them engaged. "
                "Keep it short (1-3 sentences). "
                "Never reveal internal analysis or thinking steps; give only the final user-facing text. "
                "If the user shares personal facts worth remembering (pets, hobbies, preferences, "
                "life events, recurring patterns), call memory_write to save them."
            )
            if memory_tools:
                _track_llm_call("responder_engagement", "responder_model")
                bound_model = responder_model.bind_tools(memory_tools)
                result = _invoke_model(bound_model, messages_to_send + [SystemMessage(content=engagement_hint)])
                tool_calls = getattr(result, "tool_calls", None) or []
                new_messages = list(state["messages"]) + [result]
                if tool_calls:
                    from langchain_core.messages import ToolMessage as TM
                    for tc in tool_calls:
                        t_name = tc.get("name", "")
                        t_args = tc.get("args", {})
                        tool_obj = tool_by_name.get(t_name)
                        if tool_obj:
                            try:
                                t_result = tool_obj.invoke(t_args)
                            except Exception as e:
                                t_result = f"Error: {e}"
                            new_messages.append(TM(content=str(t_result), tool_call_id=tc.get("id", "")))
                    _track_llm_call("responder_engagement_final", "responder_model")
                    final = _invoke_model(responder_model, _ensure_messages_have_content(
                        [system_msg] + new_messages + [SystemMessage(content=engagement_hint)] if system_msg
                        else new_messages + [SystemMessage(content=engagement_hint)]
                    ))
                    new_messages.append(final)
                    return {
                        **state,
                        "messages": new_messages,
                        "final_response": getattr(final, "content", None),
                    }
                return {
                    **state,
                    "messages": new_messages,
                    "final_response": getattr(result, "content", None),
                }
            else:
                _track_llm_call("responder_engagement", "responder_model")
                result = _invoke_model(responder_model, messages_to_send + [SystemMessage(content=engagement_hint)])
                return {
                    **state,
                    "messages": state["messages"] + [result],
                    "final_response": getattr(result, "content", None),
                }
        
        # If planner already provided final response and there are no steps, finish.
        if state.get("final_response") and not (state.get("plan") or []):
            return state

        plan = state.get("plan") or []
        idx = int(state.get("step_idx", 0) or 0)

        # If we already have a final response, finish.
        if state.get("final_response"):
            return state

        # If no more steps, use responder model to craft an answer from messages.
        if idx >= len(plan):
            tool_err = _last_tool_error(state["messages"])
            if tool_err:
                hint = (
                    "A tool call failed. Respond with a user-safe, action-oriented message:\n"
                    "1) What I tried (one short sentence)\n"
                    "2) What failed (plain language; no internal traces)\n"
                    "3) Next step (one concrete action): ask for missing info, suggest retry, or provide an alternative\n"
                    "If retryable is true, suggest the user try again.\n"
                    "Keep it friendly and helpful - don't make the user feel bad about the error."
                )
                base_messages = state["messages"]
                system_msg = _get_system_message_for_response(mode)
                if system_msg:
                    base_messages = [system_msg] + base_messages
                messages_to_send = _ensure_messages_have_content(base_messages + [SystemMessage(content=hint)])
                _track_llm_call("routed_responder_error", "responder_model")
                result = _invoke_model(responder_model, messages_to_send)
            else:
                default_hint = (
                    "RESPONSE GUIDELINES:\n"
                    "- Be friendly, encouraging, and concise (2-4 sentences max)\n"
                    "- Summarize what was done using natural language\n"
                    "- Use emojis sparingly: ✅ for success, 🔥 for streaks, 📊 for reports\n"
                    "- If showing progress, highlight achievements and encourage continued effort\n"
                    "- End with a subtle prompt for next action if relevant (e.g., 'Keep up the great work!')\n"
                    "- Format lists with bullet points (•) for readability\n"
                    "- Do NOT include raw tool outputs or JSON - summarize in human terms\n"
                    "- Output only the final answer. Never include internal analysis, step-by-step thinking, or a 'thinking process'."
                )
                detected_intent = state.get("detected_intent")
                if detected_intent:
                    default_hint += (
                        f"\n\nVALIDATION: The user's detected intent was '{detected_intent}'. "
                        "Verify that your response aligns with this intent. If the actions taken don't match the intent, "
                        "acknowledge the mismatch and ask one clarifying question instead of asserting success."
                    )
                executed_actions = state.get("executed_actions") or []
                mutation_actions = [a for a in executed_actions if a.get("tool_name", "").startswith(MUTATION_PREFIXES)]
                if mutation_actions:
                    actions_summary = "; ".join([
                        f"{a['tool_name']}({', '.join(f'{k}={v}' for k, v in (a.get('args') or {}).items() if k != 'user_id')}) -> {'success' if a.get('success') else 'failed'}"
                        for a in mutation_actions
                    ])
                    default_hint += (
                        f"\n\nACTIONS EXECUTED: {actions_summary}\n"
                        "CRITICAL: Your response MUST accurately reflect ONLY what was actually executed above. "
                        "Do NOT claim actions were performed if they are not in this list. "
                        "If an action failed, explain what went wrong instead of claiming success."
                    )
                else:
                    default_hint += (
                        "\n\nNOTE: No mutation actions (add/create/update/delete/log) were executed in this turn. "
                        "Do NOT claim any actions were performed. If the user expected an action, "
                        "ask for clarification about what they want to do."
                    )
                base_messages = state["messages"]
                system_msg = _get_system_message_for_response(mode)
                if system_msg:
                    base_messages = [system_msg] + base_messages
                messages_to_send = _ensure_messages_have_content(base_messages + [SystemMessage(content=default_hint)])
                _track_llm_call("routed_responder_default", "responder_model")
                result = _invoke_model(responder_model, messages_to_send)
            return {
                **state,
                "messages": state["messages"] + [result],
                "final_response": getattr(result, "content", None),
            }

        step = PlanStep.model_validate(plan[idx])
        new_iteration = int(state.get("iteration", 0) or 0) + 1

        if new_iteration > max_iterations:
            validated_messages = _ensure_messages_have_content(state["messages"])
            _track_llm_call("routed_responder_max_iter", "responder_model")
            result = _invoke_model(responder_model, validated_messages)
            return {
                **state,
                "messages": state["messages"] + [result],
                "iteration": new_iteration,
                "final_response": getattr(result, "content", None),
            }

        if step.kind == "ask_user":
            pending = (state.get("pending_meta_by_idx") or {}).get(idx)
            return {
                **state,
                "iteration": new_iteration,
                "final_response": step.question or "Could you clarify what you mean?",
                "pending_clarification": pending,
                "step_idx": idx + 1,
            }

        if step.kind == "respond":
            base_hint = step.response_hint or "Respond to the user based on tool results above."
            ux_guidelines = (
                "\n\nRESPONSE STYLE:\n"
                "- Be friendly and encouraging (you're Xaana, a helpful assistant)\n"
                "- Keep it concise: 2-4 sentences for simple actions, up to 6 for reports\n"
                "- Use natural language, not technical jargon\n"
                "- Emojis: ✅ success, 🔥 streaks, 📊 reports, 💪 encouragement (use sparingly)\n"
                "- Format lists with bullet points (•) for readability\n"
                "- Highlight achievements and progress positively\n"
                "- Do NOT output raw JSON or tool responses - summarize them\n"
                "- Output only the final answer. Never include internal analysis, step-by-step thinking, or a 'thinking process'.\n"
                "- Do NOT call any tools in your response\n"
                "- Do NOT include headers like 'Zana:' or 'Xaana:' in your response - the system will add the header automatically"
            )
            hint = base_hint + ux_guidelines
            detected_intent = state.get("detected_intent")
            if detected_intent:
                hint += (
                    f"\n\nVALIDATION: The user's detected intent was '{detected_intent}'. "
                    "Verify that your response aligns with this intent. If the actions taken don't match the intent, "
                    "acknowledge the mismatch and ask one clarifying question instead of asserting success."
                )
            
            # CRITICAL: Add executed actions validation for routed graph
            executed_actions = state.get("executed_actions") or []
            mutation_actions = [a for a in executed_actions if a.get("tool_name", "").startswith(MUTATION_PREFIXES)]
            if mutation_actions:
                actions_summary = "; ".join([
                    f"{a['tool_name']}({', '.join(f'{k}={v}' for k, v in (a.get('args') or {}).items() if k != 'user_id')}) -> {'success' if a.get('success') else 'failed'}"
                    for a in mutation_actions
                ])
                hint += (
                    f"\n\nACTIONS EXECUTED: {actions_summary}\n"
                    "CRITICAL: Your response MUST accurately reflect ONLY what was actually executed above. "
                    "Do NOT claim actions were performed if they are not in this list. "
                    "If an action failed, explain what went wrong instead of claiming success."
                )
            else:
                hint += (
                    "\n\nNOTE: No mutation actions (add/create/update/delete/log) were executed in this turn. "
                    "Do NOT claim any actions were performed. If the user expected an action, "
                    "ask for clarification about what they want to do."
                )

            tool_err = _last_tool_error(state["messages"])
            if tool_err:
                err_type = tool_err.get("error_type", "unknown")
                retryable = bool(tool_err.get("retryable"))
                failure_hint = (
                    "\n\nNOTE: A tool call failed. Handle gracefully:\n"
                    "1) Briefly explain what you tried\n"
                    "2) What went wrong (no technical details)\n"
                    "3) Suggest a next step\n"
                    f"Context: error_type={err_type}, retryable={retryable}.\n"
                    "Be reassuring - errors happen!"
                )
                hint = hint + failure_hint
            base_messages = state["messages"]
            system_msg = _get_system_message_for_response(mode)
            if system_msg:
                base_messages = [system_msg] + base_messages
            messages_to_send = _ensure_messages_have_content(base_messages + [SystemMessage(content=hint)])
            _track_llm_call("routed_responder_respond_step", "responder_model")
            result = _invoke_model(responder_model, messages_to_send)
            return {
                **state,
                "messages": state["messages"] + [result],
                "iteration": new_iteration,
                "final_response": getattr(result, "content", None),
                "step_idx": idx + 1,
            }

        if step.kind == "tool":
            tool_name = step.tool_name or ""
            tool_args = step.tool_args or {}
            
            # MODE GUARDRAIL: Block mutations in non-operator modes (except allowed ones)
            is_mutation_tool = tool_name.startswith(MUTATION_PREFIXES)
            allowed_mutations = ALLOWED_MUTATIONS_BY_MODE.get(mode, set())
            
            if is_mutation_tool and mode != "operator":
                # Check if this mutation is allowed for this mode
                tool_allowed = False
                if allowed_mutations:
                    # Check if tool name contains any allowed mutation keyword
                    tool_allowed = any(allowed in tool_name for allowed in allowed_mutations)
                
                if not tool_allowed:
                    user_text = _last_user_text(state.get("messages") or [])
                    recovery_step = _strategy_read_only_recovery_step_for_mismatch(user_text)
                    if recovery_step:
                        repaired_plan = [dict(s or {}) for s in plan]
                        repaired_plan[idx] = recovery_step
                        respond_step = {
                            "kind": "respond",
                            "purpose": "Answer the user's query with read-only data.",
                            "response_hint": "Answer the question directly using the latest read-only tool output. Do not suggest creating or updating anything unless the user asks.",
                        }
                        if idx + 1 < len(repaired_plan):
                            next_step = dict(repaired_plan[idx + 1] or {})
                            if next_step.get("kind") == "respond":
                                next_step["response_hint"] = respond_step["response_hint"]
                                repaired_plan[idx + 1] = next_step
                            else:
                                repaired_plan.insert(idx + 1, respond_step)
                        else:
                            repaired_plan.append(respond_step)
                        return {
                            **state,
                            "plan": repaired_plan,
                            "iteration": new_iteration,
                            "step_idx": idx,
                        }
                    # Block mutation and suggest switching to operator
                    blocked_msg = (
                        f"I'm in {mode} mode, which focuses on {mode}-related tasks. "
                        f"To {tool_name.replace('_', ' ')}, I'd need to switch to operator mode. "
                        f"Would you like me to proceed with that action? (Reply 'yes' to proceed, or clarify what you actually want.)"
                    )
                    return {
                        **state,
                        "iteration": new_iteration,
                        "final_response": blocked_msg,
                        "step_idx": idx + 1,
                    }
            
            # Placeholder resolution (same as existing executor)
            for arg_name, arg_val in list((tool_args or {}).items()):
                if not isinstance(arg_val, str):
                    continue
                _from_tool_parts = _parse_from_tool(arg_val)
                if not _from_tool_parts:
                    continue
                src_tool, src_field = _from_tool_parts
                src_text = _last_tool_output_for(state.get("messages", []), src_tool)
                if not src_text:
                    continue
                obj = _parse_json_obj(src_text)
                resolved = (obj or {}).get(src_field) if obj else None
                if resolved not in (None, "", [], {}):
                    tool_args[arg_name] = resolved
                elif not src_field or not obj:
                    if src_text.strip() and not src_text.strip().startswith(("Could not", "Error")):
                        tool_args[arg_name] = src_text.strip()
            
            # FROM_SEARCH handling
            if _is_from_search(tool_args.get("promise_id", "") or ""):
                last_search_output_text = _last_tool_output_for(state.get("messages", []), "search_promises")
                parsed = _parse_json_obj(last_search_output_text)
                if parsed and parsed.get("single_match"):
                    promise_id = parsed.get("promise_id")
                    if promise_id:
                        tool_args["promise_id"] = promise_id
            
            # Confirmation check (same as existing executor)
            # Default to "medium" when planner didn't provide confidence (safer approach).
            intent_confidence = (state.get("intent_confidence") or "medium").lower()
            safety = state.get("safety") or {}
            requires_confirmation = safety.get("requires_confirmation", False)
            
            # Check if this is a tool that needs confirmation on low/medium confidence
            needs_low_confidence_confirm = (
                tool_name in CONFIRM_ON_LOW_CONFIDENCE_TOOLS and 
                intent_confidence in ("low", "medium")
            )
            
            needs_confirmation = (
                tool_name in ALWAYS_CONFIRM_TOOLS or
                needs_low_confidence_confirm or
                (is_mutation_tool and (intent_confidence == "low" or requires_confirmation))
            )
            
            if needs_confirmation:
                detected_intent = state.get("detected_intent") or "this action"
                action_description = f"perform {str(detected_intent).lower()}"
                if tool_name == "add_action":
                    promise_id = tool_args.get("promise_id", "a promise")
                    time_spent = tool_args.get("time_spent", "some time")
                    action_description = f"log {time_spent} hour(s) on {promise_id}"
                elif tool_name == "create_promise" or tool_name == "add_promise":
                    promise_text = tool_args.get("text", tool_args.get("promise_text", "a promise"))
                    action_description = f"create a new promise: '{promise_text}'"
                elif tool_name == "subscribe_template":
                    template_id = tool_args.get("template_id", "a template")
                    action_description = f"subscribe to template: '{template_id}'"
                elif tool_name == "delete_promise":
                    promise_id = tool_args.get("promise_id", "a promise")
                    action_description = f"delete promise {promise_id}"
                elif tool_name == "update_setting":
                    setting_key = tool_args.get("setting_key", "a setting")
                    setting_value = tool_args.get("setting_value", "")
                    action_description = f"change {setting_key} to {setting_value}"
                else:
                    action_description = f"call {tool_name} with {tool_args}"
                
                question = (
                    f"Just to confirm: you want me to {action_description}, right?\n\n"
                    f"Reply 'yes' or 'confirm' to proceed, or clarify what you actually want."
                )
                pending = {
                    "reason": "pre_mutation_confirmation",
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "detected_intent": detected_intent,
                    "intent_confidence": intent_confidence,
                }
                return {
                    **state,
                    "iteration": new_iteration,
                    "final_response": question,
                    "pending_clarification": pending,
                    "step_idx": idx,
                }
            
            # Execute tool
            call_id = f"plan_{idx}_iter_{new_iteration}"
            tool_call = {"name": tool_name, "args": tool_args, "id": call_id, "type": "tool_call"}
            ai = AIMessage(content="(calling tool)", tool_calls=[tool_call])
            _emit(
                progress_getter,
                "executor_step",
                {"iteration": new_iteration, "step_idx": idx, "kind": "tool", "tool": tool_name, "mode": mode},
            )
            return {
                **state,
                "messages": state["messages"] + [ai],
                "iteration": new_iteration,
            }
        
        return {**state, "iteration": new_iteration, "step_idx": idx + 1}
    
    def tools_node(state: AgentState) -> AgentState:
        # Track executed action for validation
        last_msg = state["messages"][-1] if state.get("messages") else None
        last_tool_calls = getattr(last_msg, "tool_calls", None) if last_msg else None
        tool_calls = list(last_tool_calls or []) if isinstance(last_tool_calls, list) else []
        executed_action: Optional[Dict[str, Any]] = None

        if tool_calls:
            last_call = tool_calls[-1] or {}
            executed_action = {
                "tool_name": (last_call.get("name") or "").strip(),
                "args": last_call.get("args") or {},
                "result": None,
                "success": False,
            }

        retry_counts = dict(state.get("tool_retry_counts") or {})
        call_history = list(state.get("tool_call_history") or [])
        warning_buckets = dict(state.get("tool_loop_warning_buckets") or {})

        result_messages, retry_counts, call_history, warning_buckets = _execute_tool_calls_with_policies(
            tool_calls=tool_calls,
            tools_by_name=tool_by_name,
            retry_counts=retry_counts,
            call_history=call_history,
            warning_buckets=warning_buckets,
            progress_getter=progress_getter,
            iteration=int(state.get("iteration", 0) or 0),
        )

        # Track execution result
        if executed_action and result_messages:
            content = getattr(result_messages[0], "content", "") if result_messages else ""
            # Check if result indicates an error
            is_error = False
            if content:
                try:
                    parsed = json.loads(content)
                    is_error = isinstance(parsed, dict) and "error" in parsed
                except (json.JSONDecodeError, TypeError):
                    pass
            executed_action["result"] = content[:500] if content else ""
            executed_action["success"] = not is_error
        
        _emit(
            progress_getter,
            "tool_step",
            {
                "iteration": state["iteration"],
                "tool_results": [
                    getattr(m, "content", None) for m in result_messages if isinstance(m, ToolMessage)
                ],
            },
        )
        
        # Update executed_actions list
        existing_actions = list(state.get("executed_actions") or [])
        if executed_action:
            existing_actions.append(executed_action)
        
        # After executing a tool call, advance to the next plan step.
        return {
            **state,
            "messages": state["messages"] + result_messages,
            "iteration": state["iteration"],
            "step_idx": int(state.get("step_idx", 0) or 0) + 1,
            "tool_retry_counts": retry_counts,
            "tool_call_history": call_history,
            "tool_loop_warning_buckets": warning_buckets,
            "executed_actions": existing_actions,
        }
    
    def should_continue(state: AgentState):
        if state.get("final_response"):
            return END
        last_msg = state["messages"][-1] if state.get("messages") else None
        has_tool_calls = isinstance(last_msg, AIMessage) and getattr(last_msg, "tool_calls", None)
        # Always execute pending tool calls, even if we're at the iteration cap,
        # otherwise we can stop with "(calling tool)" as the last message.
        if has_tool_calls:
            return "tools"
        if int(state.get("iteration", 0) or 0) >= max_iterations:
            return END
        return "executor"
    
    graph.add_node("router", router)
    graph.add_node("planner", planner)
    graph.add_node("executor", executor)
    graph.add_node("tools", tools_node)
    graph.set_entry_point("router")
    graph.add_edge("router", "planner")
    graph.add_edge("planner", "executor")
    graph.add_conditional_edges("executor", should_continue, {"tools": "tools", "executor": "executor", END: END})
    graph.add_edge("tools", "executor")
    return graph.compile()

