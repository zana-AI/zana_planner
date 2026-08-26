"""
Display names safe to show to people outside the app.

The Mini App already pseudonymises unnamed users client-side
(`webapp_frontend/src/utils/usernameGenerator.ts`). The public club page is
rendered for anonymous visitors, so the same decision has to happen on the
server — a stranger must never receive a real first name we then only hide in
the UI. This module is the server-side counterpart and deliberately mirrors the
frontend's hash so the *same* user gets the *same* pseudonym on both surfaces.
"""
from __future__ import annotations

from typing import Optional

# Copied verbatim (order matters — these are index tables) from
# usernameGenerator.ts. The duplicates it contains are preserved on purpose:
# dropping them would shift every later index and give the same user a
# different alias on the two surfaces.
_ADJECTIVES = [
    "Swift", "Bold", "Clever", "Bright", "Noble", "Wise", "Calm", "Brave",
    "Fierce", "Gentle", "Radiant", "Serene", "Vivid", "Eager", "Loyal", "Proud",
    "Daring", "Humble", "Vibrant", "Steady", "Quick", "Silent", "Mighty", "Graceful",
    "Bold", "Kind", "Sharp", "Wild", "Pure", "Fresh", "Solid", "Rapid",
    "Smooth", "Crisp", "Warm", "Cool", "Bright", "Deep", "High", "Low",
    "Strong", "Light", "Dark", "Clear", "Firm", "Soft", "Hard", "Smooth",
    "Rough", "Fine", "Coarse", "Thick", "Thin", "Wide", "Narrow", "Tall",
    "Short", "Long", "Big", "Small", "Huge", "Tiny", "Giant", "Mini",
    "Fast", "Slow", "Quick", "Lazy", "Active", "Quiet", "Loud", "Silent",
    "Happy", "Joyful", "Cheerful", "Merry", "Gleeful", "Jolly", "Blissful", "Ecstatic",
]

_NOUNS = [
    "Eagle", "Phoenix", "Star", "Wave", "Mountain", "River", "Forest", "Light",
    "Thunder", "Storm", "Ocean", "Sky", "Moon", "Sun", "Wind", "Fire",
    "Stone", "Crystal", "Diamond", "Pearl", "Gold", "Silver", "Steel", "Iron",
    "Tiger", "Lion", "Wolf", "Bear", "Hawk", "Falcon", "Raven", "Owl",
    "Dragon", "Unicorn", "Griffin", "Phoenix", "Sphinx", "Basilisk", "Hydra", "Kraken",
    "Sword", "Shield", "Arrow", "Bow", "Spear", "Axe", "Hammer", "Blade",
    "Crown", "Throne", "Castle", "Tower", "Temple", "Shrine", "Altar", "Sanctuary",
    "Path", "Road", "Trail", "Journey", "Quest", "Adventure", "Voyage", "Expedition",
    "Dream", "Vision", "Hope", "Faith", "Courage", "Honor", "Glory", "Victory",
    "Wisdom", "Knowledge", "Truth", "Justice", "Freedom", "Peace", "Harmony", "Balance",
]


def _hash_user_id(user_id: str) -> int:
    """Java-style 32-bit string hash — the same one usernameGenerator.ts uses."""
    hash_value = 0
    for char in str(user_id):
        hash_value = ((hash_value << 5) - hash_value) + ord(char)
        # Emulate JS `hash & hash` on a 32-bit signed int.
        hash_value &= 0xFFFFFFFF
        if hash_value >= 0x80000000:
            hash_value -= 0x100000000
    return abs(hash_value)


def pseudonym(user_id: str) -> str:
    """A stable two-word alias for a user we may not name (e.g. 'SwiftEagle')."""
    hash_value = _hash_user_id(user_id)
    adjective = _ADJECTIVES[hash_value % len(_ADJECTIVES)]
    noun = _NOUNS[(hash_value // len(_ADJECTIVES)) % len(_NOUNS)]
    return f"{adjective}{noun}"


def public_display_name(
    user_id: str,
    first_name: Optional[str] = None,
    username: Optional[str] = None,
    is_private: bool = False,
) -> str:
    """The name to show a stranger: the real one unless the user opted out."""
    if is_private:
        return pseudonym(user_id)
    if first_name and first_name.strip():
        return first_name.strip()
    if username and username.strip():
        return f"@{username.strip()}"
    return pseudonym(user_id)


def initials(name: str) -> str:
    """One or two letters for an avatar fallback circle."""
    parts = [part for part in str(name).replace("@", "").split() if part]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][0].upper()
    return f"{parts[0][0]}{parts[-1][0]}".upper()
