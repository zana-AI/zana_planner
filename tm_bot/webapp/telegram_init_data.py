"""
Validate Telegram Mini App initData (HMAC-SHA256 per Telegram docs).
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hmac
import hashlib
from urllib.parse import parse_qs
from typing import Optional, Tuple
import json


def validate_init_data(init_data: str, bot_token: str, max_age_seconds: Optional[int] = 86400) -> Tuple[bool, Optional[int]]:
    """
    Validate raw initData string from Telegram.WebApp.initData.
    Returns (valid, user_id). user_id is None if validation fails or user not present.
    """
    if not init_data or not bot_token:
        return False, None
    try:
        # Parse query string; values are lists, we want first value
        parsed = parse_qs(init_data, keep_blank_values=False)
        received_hash = (parsed.get("hash") or [None])[0]
        if not received_hash:
            return False, None
        # Build data-check-string: all keys except hash, sorted, "key=value" per line
        data_pairs = []
        for k, v in parsed.items():
            if k == "hash":
                continue
            val = v[0] if v else ""
            data_pairs.append((k, val))
        data_pairs.sort(key=lambda x: x[0])
        data_check_string = "\n".join(f"{k}={v}" for k, v in data_pairs)
        # secret_key = HMAC_SHA256(bot_token, "WebAppData")
        secret_key = hmac.new(
            b"WebAppData",
            bot_token.encode() if isinstance(bot_token, str) else bot_token,
            hashlib.sha256,
        ).digest()
        # computed_hash = HMAC_SHA256(secret_key, data_check_string)
        computed_hash = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if computed_hash != received_hash:
            return False, None
        # Optional: reject old data
        if max_age_seconds is not None:
            auth_date_str = (parsed.get("auth_date") or [None])[0]
            if auth_date_str:
                try:
                    auth_date = int(auth_date_str)
                    import time
                    if int(time.time()) - auth_date > max_age_seconds:
                        return False, None
                except (ValueError, TypeError):
                    return False, None
        # Parse user.id from "user" JSON
        user_json = (parsed.get("user") or [None])[0]
        if not user_json:
            return True, None
        try:
            user_obj = json.loads(user_json)
            user_id = user_obj.get("id")
            return True, int(user_id) if user_id is not None else None
        except (json.JSONDecodeError, TypeError, ValueError):
            return True, None
    except Exception:
        return False, None
