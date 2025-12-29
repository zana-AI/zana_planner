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

    - Main response is shown under a bold "Zana:" header.
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

    zana_text = html.escape("" if llm_response is None else str(llm_response))
    log_text = html.escape("" if formatted_log is None else str(formatted_log))

    full_response = f"<b>Zana:</b>\n{zana_text}\n"
    if formatted_log:
        full_response += f"\n<b>Log:</b>\n<blockquote expandable>{log_text}</blockquote>"
    return full_response

