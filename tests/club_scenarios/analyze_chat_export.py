"""
Xaana club chat export analyzer.

Extracts bot response sequences from a Telegram JSON export and sends them to
a reasoning-capable LLM (Claude) for qualitative analysis.

Usage:
    python tests/club_scenarios/analyze_chat_export.py <path/to/result.json>
    python tests/club_scenarios/analyze_chat_export.py --export "C:/Users/.../ChatExport_xxx"
    python tests/club_scenarios/analyze_chat_export.py --export ... --model claude-opus-4-7
    python tests/club_scenarios/analyze_chat_export.py --export ... --chunk-size 40
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import textwrap
from pathlib import Path
from typing import Optional

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BOT_NAME = "Xaana"
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_CHUNK_SIZE = 60   # episodes per LLM call
CONTEXT_BEFORE = 4        # human messages to include before the first bot reply in an episode
CONTEXT_AFTER = 2         # messages after last bot reply (to see follow-up reactions)


# ── message parsing ────────────────────────────────────────────────────────────

def extract_text(raw) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return "".join(p if isinstance(p, str) else p.get("text", "") for p in raw)
    return ""


def load_messages(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    msgs = []
    for m in data.get("messages", []):
        if m.get("type") != "message":
            continue
        sender = m.get("from") or ""
        text = extract_text(m.get("text", "")).strip()
        msgs.append({
            "id": m["id"],
            "date": m.get("date", ""),
            "sender": sender,
            "is_bot": sender == BOT_NAME,
            "text": text,
            "reply_to": m.get("reply_to_message_id"),
        })
    return msgs


# ── episode extraction ─────────────────────────────────────────────────────────

def extract_episodes(msgs: list[dict]) -> list[dict]:
    """
    An episode is a bot response sequence — one or more consecutive/chained bot
    messages — together with surrounding context. Consecutive bot messages are
    merged into a single episode.
    """
    id_to_idx = {m["id"]: i for i, m in enumerate(msgs)}
    episodes = []
    i = 0
    while i < len(msgs):
        if not msgs[i]["is_bot"]:
            i += 1
            continue

        # Collect consecutive bot messages (a sequence)
        bot_seq = []
        j = i
        while j < len(msgs) and msgs[j]["is_bot"]:
            bot_seq.append(msgs[j])
            j += 1

        # Find the triggering context: up to CONTEXT_BEFORE human messages before i
        ctx_before = []
        k = i - 1
        while k >= 0 and len(ctx_before) < CONTEXT_BEFORE:
            ctx_before.insert(0, msgs[k])
            k -= 1

        # If the first bot message is replying to something specific, include that too
        reply_to_id = bot_seq[0].get("reply_to")
        trigger_msg = None
        if reply_to_id and reply_to_id in id_to_idx:
            trigger_msg = msgs[id_to_idx[reply_to_id]]

        # Context after: a few messages to see member reactions
        ctx_after = msgs[j: j + CONTEXT_AFTER]

        episodes.append({
            "idx": i,
            "date": bot_seq[0]["date"],
            "trigger": trigger_msg,
            "context_before": ctx_before,
            "bot_sequence": bot_seq,
            "context_after": ctx_after,
        })
        i = j

    return episodes


# ── transcript formatting ──────────────────────────────────────────────────────

def format_episode(ep: dict, ep_num: int) -> str:
    lines = [f"=== Episode {ep_num} [{ep['date'][:16]}] ==="]

    seen_ids = set()

    def add_msg(m: dict, label: str = "") -> None:
        if m["id"] in seen_ids:
            return
        seen_ids.add(m["id"])
        prefix = f"[{label}] " if label else ""
        sender = "🤖 BOT" if m["is_bot"] else f"👤 {m['sender']}"
        reply_tag = f" (reply to #{m['reply_to']})" if m.get("reply_to") else ""
        text = m["text"] or "(empty)"
        lines.append(f"  {prefix}{sender}{reply_tag}: {text}")

    if ep.get("trigger"):
        add_msg(ep["trigger"], "TRIGGER")

    for m in ep["context_before"]:
        add_msg(m)

    for m in ep["bot_sequence"]:
        add_msg(m)

    for m in ep["context_after"]:
        add_msg(m, "REACTION")

    return "\n".join(lines)


def format_chunk(episodes: list[dict], offset: int) -> str:
    parts = []
    for i, ep in enumerate(episodes):
        parts.append(format_episode(ep, offset + i + 1))
    return "\n\n".join(parts)


# ── LLM analysis ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = textwrap.dedent(f"""
    You are an expert product analyst reviewing a Telegram group-chat bot called Xaana.
    Xaana is an AI accountability coach for small clubs (groups of friends with a shared goal).

    Your job: analyze sequences of bot responses and identify patterns — both good and bad.
    Focus on:
    1. **Over-triggering** — bot responded when it clearly shouldn't have (emoji-only, side chatter,
       short acks, conversations not meant for the bot)
    2. **Under-triggering** — a member shared a result or asked something relevant and the bot stayed silent
    3. **Response quality** — was the response helpful, warm, appropriate in length and tone?
    4. **Language issues** — bot replied in wrong language, or was too stiff/formal
    5. **Repetition** — bot said nearly the same thing multiple times in a session
    6. **Sequence problems** — consecutive bot messages that feel redundant or contradictory
    7. **Positive patterns** — things the bot did well that should be preserved

    Be specific: quote the relevant lines. For each issue, suggest a concrete fix.
    Skip generic observations — only flag things that would change the product.
""").strip()

ANALYSIS_PROMPT = textwrap.dedent("""
    Below are {n} bot response episodes extracted from the club chat.
    Each episode shows the context (human messages), the bot's response(s), and member reactions.

    Analyze these episodes and produce a structured report with:
    - A numbered list of issues found (with episode reference, quoted text, and fix suggestion)
    - A short list of things the bot did well in these episodes
    - 2-3 highest-priority action items

    Episodes:
    {transcript}
""").strip()


def call_llm(transcript: str, n_episodes: int, model: str, api_key: str) -> str:
    try:
        import anthropic
    except ImportError:
        return "[ERROR] anthropic package not installed. Run: pip install anthropic"

    client = anthropic.Anthropic(api_key=api_key)
    prompt = ANALYSIS_PROMPT.format(n=n_episodes, transcript=transcript)

    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def call_llm_summary(chunk_analyses: list[str], model: str, api_key: str) -> str:
    try:
        import anthropic
    except ImportError:
        return ""

    client = anthropic.Anthropic(api_key=api_key)
    combined = "\n\n---\n\n".join(
        f"### Analysis {i+1}\n{a}" for i, a in enumerate(chunk_analyses)
    )
    prompt = textwrap.dedent(f"""
        Below are analyses of {len(chunk_analyses)} chunks of bot response episodes from the same chat.
        Synthesize these into a final executive summary:
        - Top 5 most important issues (ranked by frequency and severity)
        - Top 3 things the bot did well
        - Final priority action list (max 5 items)

        Chunk analyses:
        {combined}
    """).strip()

    message = client.messages.create(
        model=model,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


# ── stats (fast, no LLM) ───────────────────────────────────────────────────────

def quick_stats(msgs: list[dict], episodes: list[dict]) -> str:
    human = [m for m in msgs if not m["is_bot"]]
    bot = [m for m in msgs if m["is_bot"]]
    senders = sorted({m["sender"] for m in human if m["sender"]})
    bot_ratio = round(len(bot) / max(len(msgs), 1) * 100, 1)
    seq_lengths = [len(ep["bot_sequence"]) for ep in episodes]
    multi = [l for l in seq_lengths if l > 1]
    lines = [
        f"Total messages : {len(msgs)} ({len(human)} human, {len(bot)} bot = {bot_ratio}%)",
        f"Participants   : {', '.join(senders)}",
        f"Bot episodes   : {len(episodes)} ({len(multi)} with 2+ consecutive bot messages)",
    ]
    if multi:
        lines.append(f"Longest sequence: {max(seq_lengths)} consecutive bot messages")
    return "\n".join(lines)


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Xaana club chat export with LLM")
    parser.add_argument("json_path", nargs="?", help="Path to result.json")
    parser.add_argument("--export", help="Path to ChatExport directory")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude model (default: {DEFAULT_MODEL})")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE,
                        help=f"Episodes per LLM call (default: {DEFAULT_CHUNK_SIZE})")
    parser.add_argument("--no-llm", action="store_true", help="Only print stats and episodes, skip LLM")
    parser.add_argument("--api-key", help="Anthropic API key (or set ANTHROPIC_API_KEY env var)")
    args = parser.parse_args()

    # Resolve path
    if args.export:
        path = Path(args.export) / "result.json"
    elif args.json_path:
        path = Path(args.json_path)
    else:
        path = Path("C:/Users/Jqvqd/Downloads/ChatExport_2026-04-23 (1)/result.json")

    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not args.no_llm and not api_key:
        print("No API key found. Set ANTHROPIC_API_KEY or pass --api-key. Use --no-llm to skip.", file=sys.stderr)
        sys.exit(1)

    # Parse
    msgs = load_messages(path)
    episodes = extract_episodes(msgs)

    print("\n" + "=" * 70)
    print(f"  Chat export: {path.name}  |  model: {args.model}")
    print("=" * 70)
    print(quick_stats(msgs, episodes))

    if args.no_llm:
        print(f"\n--- Episodes (--no-llm mode) ---\n")
        for i, ep in enumerate(episodes):
            print(format_episode(ep, i + 1))
            print()
        return

    # Chunk and analyze
    chunks = [episodes[i:i + args.chunk_size] for i in range(0, len(episodes), args.chunk_size)]
    print(f"\nSending {len(episodes)} episodes in {len(chunks)} chunk(s) to {args.model}...\n")

    chunk_analyses = []
    for c_idx, chunk in enumerate(chunks):
        offset = c_idx * args.chunk_size
        transcript = format_chunk(chunk, offset)
        print(f"--- Chunk {c_idx + 1}/{len(chunks)} ({len(chunk)} episodes) ---")
        analysis = call_llm(transcript, len(chunk), args.model, api_key)
        chunk_analyses.append(analysis)
        print(analysis)
        print()

    # Summary if more than one chunk
    if len(chunks) > 1:
        print("\n" + "=" * 70)
        print("  FINAL SUMMARY (across all chunks)")
        print("=" * 70 + "\n")
        summary = call_llm_summary(chunk_analyses, args.model, api_key)
        print(summary)

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
