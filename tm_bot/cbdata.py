# cbdata.py (optional enhancement)
from urllib.parse import urlencode, parse_qsl


SESSION_ACTION_ALIASES = {
    "session_pause": "sp",
    "session_resume": "sr",
    "session_plus": "spl",
    "session_snooze": "ss",
    "session_finish_open": "sfo",
    "session_finish_confirm": "sfc",
    "session_adjust_open": "sao",
    "session_adjust_set": "sas",
    "session_abort": "sab",
}
SESSION_ACTIONS = frozenset(SESSION_ACTION_ALIASES.keys())
SESSION_ACTION_NAMES_BY_ALIAS = {
    alias: action for action, alias in SESSION_ACTION_ALIASES.items()
}

def encode_cb(action: str, pid: str | None = None, value: float | None = None, **extra) -> str:
    """Encode callback data for use in Telegram inline keyboards."""
    d = {"a": action}
    if pid is not None:
        d["p"] = str(pid)
    if value is not None:
        d["v"] = f"{float(value):.5f}"
    for k, v in extra.items():
        d[str(k)] = str(v)
    return urlencode(d)


def normalize_cb_action(action: str | None) -> str | None:
    """Normalize compact callback aliases back to canonical action names."""
    if action is None:
        return None
    return SESSION_ACTION_NAMES_BY_ALIAS.get(action, action)


def is_session_callback_action(action: str | None) -> bool:
    """Return whether the action is one of the session callback actions."""
    normalized = normalize_cb_action(action)
    return normalized in SESSION_ACTIONS


def encode_session_cb(
    action: str,
    session_id: str,
    value: float | None = None,
    **extra,
) -> str:
    """Encode session callbacks using compact aliases to stay under Telegram's 64-byte limit."""
    normalized = normalize_cb_action(action) or action
    encoded_action = SESSION_ACTION_ALIASES.get(normalized, normalized)
    return encode_cb(encoded_action, pid=session_id, value=value, **extra)

def decode_cb(data: str) -> dict:
    """Decode callback data from Telegram inline keyboards."""
    if "=" in data:  # new format
        q = dict(parse_qsl(data))
        out = {"a": q.get("a"), "p": q.get("p")}
        out["v"] = float(q["v"]) if "v" in q else None
        # keep other keys (e.g., 't' for timestamp, 's' for session id) as strings
        for k, v in q.items():
            if k not in out:
                out[k] = v
        return out
    # legacy fallback: action:pid:value
    parts = data.split(":")
    a = parts[0] if parts else None
    p = parts[1] if len(parts) > 1 else None
    v = float(parts[2]) if len(parts) > 2 else None
    return {"a": a, "p": p, "v": v}
