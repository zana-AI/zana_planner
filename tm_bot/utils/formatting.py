import html
from typing import Any


def format_response_html(llm_response: str, func_call_response: Any) -> str:
    """
    Format a response for Telegram using HTML, escaping content safely.

    - Main response is shown under a bold "Zana:" header.
    - Optional tool output/log is shown inside an expandable blockquote.
    """
    if func_call_response is None:
        return llm_response

    if isinstance(func_call_response, list):
        formatted_log = "• " + "\n• ".join(str(item) for item in func_call_response)
    elif isinstance(func_call_response, dict):
        formatted_log = "\n".join(f"{key}: {value}" for key, value in func_call_response.items())
    else:
        formatted_log = str(func_call_response)

    zana_text = html.escape("" if llm_response is None else str(llm_response))
    log_text = html.escape("" if formatted_log is None else str(formatted_log))

    full_response = f"<b>Zana:</b>\n{zana_text}\n"
    if formatted_log:
        full_response += f"\n<b>Log:</b>\n<blockquote expandable>{log_text}</blockquote>"
    return full_response

