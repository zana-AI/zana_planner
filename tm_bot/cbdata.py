# cbdata.py (optional enhancement)
from urllib.parse import urlencode, parse_qsl

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
