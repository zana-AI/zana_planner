# cbdata.py
from urllib.parse import urlencode, parse_qsl


def encode_cb(action: str, pid: str | None = None, value: float | None = None) -> str:
    d = {"a": action}
    if pid is not None:
        d["p"] = str(pid)
    if value is not None:
        # 5 decimals keeps it short; Telegram limit is 64 bytes
        d["v"] = f"{float(value):.5f}"
    return urlencode(d)


def decode_cb(data: str) -> dict:
    # New format: a=...&p=...&v=...
    if "=" in data:
        q = dict(parse_qsl(data))
        out = {"a": q.get("a"), "p": q.get("p")}
        out["v"] = float(q["v"]) if "v" in q else None
        return out
    # Legacy format: action:pid:value
    parts = data.split(":")
    a = parts[0] if len(parts) > 0 else None
    p = parts[1] if len(parts) > 1 else None
    v = float(parts[2]) if len(parts) > 2 else None
    return {"a": a, "p": p, "v": v}
