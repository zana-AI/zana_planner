import json, re, textwrap, os, itertools, math, statistics
path = r"E:\workspace\ZanaAI\ChatExport_2026-01-20\full_chat_80k.json"
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

# Telegram exports are typically {"name":..., "type":..., "messages":[...]}
messages = data.get("messages", data if isinstance(data, list) else [])
len(messages), type(messages).__name__, list(data.keys())[:5] if isinstance(data, dict) else None

messages = data["messages"]

def normalize_text_field(t):
    if t is None:
        return ""
    if isinstance(t, str):
        return t
    if isinstance(t, list):
        parts = []
        for p in t:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict):
                # Telegram exports often store entities as dicts with a 'text' field
                if "text" in p and isinstance(p["text"], str):
                    parts.append(p["text"])
                elif "type" in p and p["type"] == "mention" and "user_id" in p:
                    # If mention text missing, keep a placeholder (optional)
                    parts.append("@user")
        return "".join(parts)
    return str(t)

# "Meaningful" = contains at least one letter or digit (Persian letters included)
# Using [^\W_] to match Unicode letters and digits (word chars except underscore)
_letter_or_digit = re.compile(r"[^\W_]", re.UNICODE)

# Persian/Arabic script characters (U+0600 to U+06FF)
_persian_char = re.compile(r"[\u0600-\u06FF]", re.UNICODE)

def has_meaningful_text(s: str) -> bool:
    if not s:
        return False
    return bool(_letter_or_digit.search(s))

def contains_persian_characters(s: str) -> bool:
    """Check if message contains at least one Persian/Arabic script character."""
    if not s:
        return False
    return bool(_persian_char.search(s))

# Simple PII patterns (only used for filtering, not redaction here)
_phone = re.compile(r"(\+?\d[\d \-().]{7,}\d)")
_email = re.compile(r"\b[\w.\-+]+@[\w.\-]+\.\w+\b", re.UNICODE)
_handle = re.compile(r"@\w{3,}", re.UNICODE)

def looks_like_pii(s: str) -> bool:
    return bool(_phone.search(s) or _email.search(s) or _handle.search(s))

# Political banned keywords - update this list as needed
POLITICAL_BANNED_KEYWORDS = [
    "اسراییل",
    "خامنه",
    "حماس",
    "خمینی",
    "ترامپ",
    "نتانیاهو",
    "اسلامی",
    "فلسطین",
    "عرب",
    "امریکا",
    "سلیمانی",
    "آمریکا",
    "داعش",

]

# Birthday/congratulatory keywords - update this list as needed
BIRTHDAY_CONGRA_KEYWORDS = [
    "تولد",
    "مبارک",
]

# Names to exclude - update this list as needed
EXCLUDED_NAMES = [
    "جواد",
    "میلاد",
    "کتاب",
    "سجاد",
    "سروش",
    "روح",
    "علی",
    "اسپریت",
    "رضا",
    "امین",
    "یاسر",
    "بهرام",
    "فتاحیان",
]

# Very minimal "targeted insult" heuristic:
# If it contains second-person pronouns and one of these strong insult tokens.
# (Add to these lists based on your own policy.)
SECOND_PERSON = ["تو", "شما", "تویی", "توئی", "تو رو", "تو را"]
STRONG_INSULT_TOKENS = [
    # NOTE: keep this list short and focused; expand carefully.
    "کثافت", "حرومزاده", "بی‌شرف", "بی شرف", "جاکش", "کونی", "کیر", "مادرجنده"
]

def looks_targeted_abuse(s: str) -> bool:
    s2 = s.replace("\u200c", " ")  # normalize ZWNJ a bit for matching
    if not any(sp in s2 for sp in SECOND_PERSON):
        return False
    return any(tok in s2 for tok in STRONG_INSULT_TOKENS)

def contains_political_keywords(s: str) -> bool:
    """Check if message contains any political banned keywords."""
    s2 = s.replace("\u200c", " ")  # normalize ZWNJ a bit for matching
    return any(keyword in s2 for keyword in POLITICAL_BANNED_KEYWORDS)

def contains_birthday_congra_keywords(s: str) -> bool:
    """Check if message contains any birthday/congratulatory keywords."""
    s2 = s.replace("\u200c", " ")  # normalize ZWNJ a bit for matching
    return any(keyword in s2 for keyword in BIRTHDAY_CONGRA_KEYWORDS)

def contains_excluded_names(s: str) -> bool:
    """Check if message contains any excluded names."""
    s2 = s.replace("\u200c", " ")  # normalize ZWNJ a bit for matching
    return any(name in s2 for name in EXCLUDED_NAMES)

def is_forwarded(msg: dict) -> bool:
    return "forwarded_from" in msg and msg["forwarded_from"] is not None

def is_message(msg: dict) -> bool:
    return msg.get("type") == "message"

def clean_text(msg: dict) -> str:
    return normalize_text_field(msg.get("text", "")) .strip()

# Build id->msg map for reply lookup
by_id = {}
for m in messages:
    if not isinstance(m, dict):
        continue
    mid = m.get("id")
    if mid is not None:
        by_id[mid] = m

def keep_for_pair(msg: dict) -> bool:
    if not is_message(msg):
        return False
    if is_forwarded(msg):
        return False
    txt = clean_text(msg)
    if not has_meaningful_text(txt):
        return False
    # Skip messages that only contain Latin characters (no Persian)
    if not contains_persian_characters(txt):
        return False
    # Drop pure PII-like messages
    if looks_like_pii(txt):
        return False
    # Drop likely targeted abuse (but keep non-targeted profanity)
    if looks_targeted_abuse(txt):
        return False
    # Drop messages containing political keywords
    if contains_political_keywords(txt):
        return False
    # Drop messages containing birthday/congratulatory keywords
    if contains_birthday_congra_keywords(txt):
        return False
    # Drop messages containing excluded names
    if contains_excluded_names(txt):
        return False
    # Optional: drop very short messages (often "لول", "😂", etc.)
    if len(txt) < 4:
        return False
    return True

def format_one_line(s: str, width: int = 110) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= width:
        return s
    return s[:width-1] + "…"

def validate_example(example: dict) -> bool:
    """Validate that the example matches Gemini SFT format requirements."""
    try:
        # Check structure
        if "contents" not in example:
            return False
        contents = example["contents"]
        if not isinstance(contents, list):
            return False
        if len(contents) != 2:
            return False
        
        # Check roles
        if contents[0].get("role") != "user":
            return False
        if contents[1].get("role") != "model":
            return False
        
        # Check parts structure
        for item in contents:
            if "parts" not in item:
                return False
            parts = item["parts"]
            if not isinstance(parts, list) or len(parts) != 1:
                return False
            if "text" not in parts[0]:
                return False
        
        return True
    except Exception:
        return False

N = 500
count = 0
used_message_ids = set()  # Track message IDs that have already been used in a pair

# Output file for JSONL format
output_file = os.path.join(os.path.dirname(path), "gemini_sft_training_data.jsonl")

with open(output_file, "w", encoding="utf-8") as out_f:
    for reply in messages:
        if not isinstance(reply, dict):
            continue
        rid = reply.get("reply_to_message_id")
        if rid is None:
            continue
        parent = by_id.get(rid)
        if parent is None:
            continue

        # Get message IDs to check if they've been used
        parent_id = parent.get("id")
        reply_id = reply.get("id")
        
        # Skip if either message has already been used in a pair
        if parent_id in used_message_ids or reply_id in used_message_ids:
            continue

        if not (keep_for_pair(parent) and keep_for_pair(reply)):
            continue

        A = clean_text(parent)
        B = clean_text(reply)

        # Extra filter: avoid emoji-only replies
        if not has_meaningful_text(B):
            continue

        # Skip if prompt (A) or answer (B) is over 120 characters
        if len(A) > 120 or len(B) > 120:
            continue

        # Mark both messages as used
        if parent_id is not None:
            used_message_ids.add(parent_id)
        if reply_id is not None:
            used_message_ids.add(reply_id)

        # Format as Gemini SFT JSONL with style tags
        # Prepend style tags to the prompt for tone control
        prompt_with_style = f"STYLE=street_fa | SWEAR=light | TARGETED=false\n\nA: {A}"
        
        # Create the JSON structure for Gemini SFT - exactly as required
        example = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": prompt_with_style
                        }
                    ]
                },
                {
                    "role": "model",
                    "parts": [
                        {
                            "text": B
                        }
                    ]
                }
            ]
        }
        
        # Validate before writing
        if not validate_example(example):
            print(f"ERROR: Invalid example structure at count {count+1}, skipping...")
            continue
        
        # Serialize to JSON and write as JSONL (one JSON object per line)
        json_line = json.dumps(example, ensure_ascii=False, separators=(',', ':'))
        out_f.write(json_line + "\n")
        
        # Print progress
        print(f"{count+1:03d}) A: {format_one_line(A)}")
        print(f"     B: {format_one_line(B)}")
        print("-" * 120)
        
        count += 1
        if count >= N:
            break

print(f"\nProcessed {count} pairs from {os.path.basename(path)}")
print(f"Output saved to: {output_file}")

# Validate the output file
print("\nValidating output file...")
valid_lines = 0
invalid_lines = 0
with open(output_file, "r", encoding="utf-8") as f:
    for line_num, line in enumerate(f, 1):
        line = line.strip()
        if not line:
            continue
        try:
            example = json.loads(line)
            if validate_example(example):
                valid_lines += 1
            else:
                invalid_lines += 1
                print(f"  Line {line_num}: Invalid structure")
        except json.JSONDecodeError as e:
            invalid_lines += 1
            print(f"  Line {line_num}: JSON decode error - {e}")

print(f"Validation complete: {valid_lines} valid lines, {invalid_lines} invalid lines")
if invalid_lines == 0:
    print("✓ All lines are valid and ready for Vertex AI!")
else:
    print("⚠ WARNING: Some lines are invalid. Please review before uploading.")

