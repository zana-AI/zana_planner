import html
import json
from typing import Any


def _format_log_item(item) -> str:
    """Format a single log item for human display."""
    if isinstance(item, str):
        # Try to parse as JSON
        try:
            parsed = json.loads(item)
            if isinstance(parsed, dict) and parsed.get("single_match"):
                return f"Found: #{parsed['promise_id']} {parsed['promise_text']}"
            if isinstance(parsed, list):
                return f"({len(parsed)} items)"  # Don't dump raw arrays
        except (json.JSONDecodeError, ValueError):
            pass
        return item
    if isinstance(item, dict):
        # Format key fields only
        if 'id' in item and 'text' in item:
            return f"#{item['id']} {item.get('text', '')}"
        # Format dict as key: value pairs, skipping None values
        return ", ".join(f"{k}: {v}" for k, v in item.items() if v is not None)
    # For other types, use string representation but truncate if too long
    item_str = str(item)
    if len(item_str) > 200:
        return item_str[:197] + "..."
    return item_str


def format_response_html(llm_response: str, func_call_response: Any) -> str:
    """
    Format a response for Telegram using HTML, escaping content safely.

    - Main response text is escaped for safe HTML display.
    - Optional tool output/log is shown inside an expandable blockquote.
    """
    if func_call_response is None:
        return llm_response

    if isinstance(func_call_response, list):
        formatted_log = "• " + "\n• ".join(_format_log_item(item) for item in func_call_response)
    elif isinstance(func_call_response, dict):
        formatted_log = "\n".join(f"{key}: {value}" for key, value in func_call_response.items())
    else:
        formatted_log = _format_log_item(func_call_response)

    # Clean the LLM response: remove any existing "Zana:" or "Xaana:" headers that the LLM might have included
    response_text = "" if llm_response is None else str(llm_response)
    # Remove common header patterns (case-insensitive, with or without HTML tags)
    import re
    response_text = re.sub(r'^(<b>)?(Zana|Xaana):\s*(</b>)?\s*\n?', '', response_text, flags=re.IGNORECASE | re.MULTILINE)
    response_text = re.sub(r'^\*\*(Zana|Xaana):\*\*\s*\n?', '', response_text, flags=re.IGNORECASE | re.MULTILINE)
    response_text = re.sub(r'^(Zana|Xaana):\s*\n?', '', response_text, flags=re.IGNORECASE | re.MULTILINE)

    zana_text = html.escape(response_text.strip())
    log_text = html.escape("" if formatted_log is None else str(formatted_log))

    full_response = zana_text
    if formatted_log:
        full_response += f"\n\n<b>Log:</b>\n<blockquote expandable>{log_text}</blockquote>"
    return full_response


def prepend_xaana_to_message(message: Any) -> str:
    """
    Prepend the Xaana header to a message.

    This is intentionally simple and is meant to run at the very end
    of the response pipeline (after translation, etc.).
    """
    base = "" if message is None else str(message)
    stripped = base.lstrip()

    # Heuristic: if the body already contains HTML markers, use an HTML header;
    # otherwise, use a Markdown-style header.
    looks_like_html = any(tag in stripped for tag in ("<blockquote", "<b>", "<i>", "<pre>", "<code>"))
    header = "<b>Xaana:</b>\n" if looks_like_html else "*Xaana:*\n"
    return f"{header}{stripped}"

