"""
Telegram Mini App authentication utilities.
Validates initData according to Telegram's WebApp authentication specification.
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import time
from typing import Optional, Dict, Any
from urllib.parse import parse_qs, unquote


def validate_telegram_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 86400  # 24 hours default
) -> Optional[Dict[str, Any]]:
    """
    Validate Telegram Mini App initData string.
    
    Args:
        init_data: The initData string from Telegram WebApp
        bot_token: The bot token for HMAC validation
        max_age_seconds: Maximum age of the auth_date (default 24 hours)
    
    Returns:
        Parsed user data dict if valid, None if invalid
    """
    if not init_data or not bot_token:
        return None
    
    try:
        # Parse the query string
        parsed = parse_qs(init_data, keep_blank_values=True)
        
        # Extract hash
        received_hash = parsed.get("hash", [None])[0]
        if not received_hash:
            return None
        
        # Build data-check-string: alphabetically sorted key=value pairs, excluding hash
        data_pairs = []
        for key, values in parsed.items():
            if key != "hash":
                # Use first value, unquote it
                value = unquote(values[0]) if values else ""
                data_pairs.append(f"{key}={value}")
        
        data_pairs.sort()
        data_check_string = "\n".join(data_pairs)
        
        # Create secret key: HMAC-SHA256 of bot_token with "WebAppData" as key
        secret_key = hmac.new(
            b"WebAppData",
            bot_token.encode("utf-8"),
            hashlib.sha256
        ).digest()
        
        # Calculate expected hash
        expected_hash = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        # Compare hashes
        if not hmac.compare_digest(received_hash, expected_hash):
            return None
        
        # Check auth_date freshness
        auth_date_str = parsed.get("auth_date", [None])[0]
        if auth_date_str:
            try:
                auth_date = int(auth_date_str)
                current_time = int(time.time())
                if current_time - auth_date > max_age_seconds:
                    return None
            except ValueError:
                return None
        
        # Parse user data
        user_str = parsed.get("user", [None])[0]
        if user_str:
            user_data = json.loads(unquote(user_str))
            return {
                "user": user_data,
                "auth_date": int(auth_date_str) if auth_date_str else None,
                "query_id": parsed.get("query_id", [None])[0],
                "chat_type": parsed.get("chat_type", [None])[0],
                "chat_instance": parsed.get("chat_instance", [None])[0],
            }
        
        return None
        
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def extract_user_id(validated_data: Dict[str, Any]) -> Optional[int]:
    """
    Extract user ID from validated Telegram data.
    
    Args:
        validated_data: The validated data dict from validate_telegram_init_data
    
    Returns:
        User ID as integer, or None if not found
    """
    if not validated_data:
        return None
    
    user = validated_data.get("user", {})
    user_id = user.get("id")
    
    if user_id is not None:
        return int(user_id)
    
    return None
