"""
Club group-chat scenario runner — Tier 1.

Runs YAML scenarios through the real LLM handler (get_response_group_safe)
without a real DB or Telegram connection. Prints responses for manual review.

Usage:
    cd zana_planner
    python tests/club_scenarios/run_scenarios.py
    python tests/club_scenarios/run_scenarios.py --scenario new_member_onboarding
    python tests/club_scenarios/run_scenarios.py --scenario informal_checkin --verbose
"""

import argparse
import asyncio
import io
import os
import sys
import textwrap
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

# Force UTF-8 output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import yaml

# ── path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
TM_BOT = ROOT / "tm_bot"
sys.path.insert(0, str(TM_BOT))
sys.path.insert(0, str(ROOT))

# Load .env if present (picks up ANTHROPIC_API_KEY etc.)
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    load_dotenv(TM_BOT / ".env", override=False)
except ImportError:
    pass

# ── local imports (after path setup) ─────────────────────────────────────────
from llms.llm_handler import LLMHandler  # noqa: E402
from router_types import InputContext     # noqa: E402

SCENARIOS_FILE = Path(__file__).parent / "scenarios.yaml"

# ANSI colours
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
GREY   = "\033[90m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


# ── mock bot / context helpers ────────────────────────────────────────────────

class _CapturingBot:
    """Minimal bot mock that captures send_message calls."""

    def __init__(self):
        self.sent: list[str] = []

    async def send_message(self, *, chat_id, text, **_kwargs):
        self.sent.append(text)
        return MagicMock(message_id=999)

    async def get_me(self):
        m = MagicMock()
        m.username = "xaana_bot"
        m.id = 9999
        return m


class _CapturingMessage:
    """Minimal message mock that captures reply_text calls."""

    def __init__(self, bot: _CapturingBot):
        self._bot = bot

    async def reply_text(self, text, **_kwargs):
        self._bot.sent.append(text)
        return MagicMock(message_id=998)

    async def edit_text(self, text, **_kwargs):
        # Replace last "Thinking..." with actual response
        if self._bot.sent and self._bot.sent[-1] in ("Thinking...", "…"):
            self._bot.sent[-1] = text
        else:
            self._bot.sent.append(text)
        return MagicMock()


def _make_ctx(
    user_id: int,
    first_name: str,
    text: str,
    chat_id: int,
    bot: _CapturingBot,
    recent_messages: list[dict],
) -> InputContext:
    msg = _CapturingMessage(bot)
    platform_update = MagicMock()
    platform_update.effective_message = msg
    platform_update.my_chat_member = None
    platform_update.chat_member = None

    platform_context = MagicMock()
    platform_context.bot = bot

    return InputContext(
        user_id=user_id,
        chat_id=chat_id,
        input_type="text",
        raw_text=text,
        platform_update=platform_update,
        platform_context=platform_context,
        metadata={
            "chat_type": "supergroup",
            "sender_name": first_name,
            "recent_messages": recent_messages,
        },
    )


# ── core runner ───────────────────────────────────────────────────────────────

async def run_turn(
    llm_handler: LLMHandler,
    club: dict,
    ctx: InputContext,
    recent_messages: list[dict],
) -> str:
    """Run one message through get_response_group_safe and return the response."""
    target_text = ""
    if club.get("target_count_per_week") is not None:
        t = float(club["target_count_per_week"])
        target_text = f"{int(t) if t.is_integer() else t} times/week"

    response = await asyncio.to_thread(
        llm_handler.get_response_group_safe,
        ctx.raw_text,
        {
            "chat_id": ctx.chat_id,
            "club_name": club.get("club_name"),
            "promise_text": club.get("promise_text"),
            "target_text": target_text,
            "recent_messages": recent_messages,
        },
        None,  # language — let LLM infer
    )
    return str(response or "").strip()


def _wrap(text: str, width: int = 90, indent: str = "    ") -> str:
    return textwrap.fill(text, width=width, initial_indent=indent, subsequent_indent=indent)


def _print_separator(title: str = "") -> None:
    line = "-" * 80
    if title:
        pad = max(0, (80 - len(title) - 2) // 2)
        print(f"\n{BOLD}{'-'*pad} {title} {'-'*(80-pad-len(title)-2)}{RESET}")
    else:
        print(f"\n{GREY}{line}{RESET}")


async def run_scenario(
    scenario: dict,
    club: dict,
    llm_handler: LLMHandler,
    verbose: bool = False,
    addressed_bot_name: str = "xaana_bot",
) -> dict:
    """Run all turns in a scenario. Returns a result dict."""
    # Allow per-scenario club override
    club = {**club, **scenario.get("club_override", {})}
    sid = scenario["id"]
    desc = scenario.get("description", "")
    turns = scenario.get("turns", [])
    chat_id = -100_000_001

    _print_separator(sid)
    print(f"{CYAN}{BOLD}{desc}{RESET}")
    print(f"{GREY}Club: {club['club_name']} · Promise: {club.get('promise_text')} · Target: {club.get('target_count_per_week')}×/week{RESET}")

    bot = _CapturingBot()
    recent_messages: list[dict] = []
    results = []

    for i, turn in enumerate(turns):
        user_id = turn["user_id"]
        first_name = turn.get("first_name", f"User{user_id}")
        text = turn["text"]
        expect = turn.get("expect", "")
        addressed = turn.get("addressed_to_bot", "@" + addressed_bot_name in text or i > 0)

        # Record in transcript
        recent_messages.append({"sender_name": first_name, "text": text})

        print(f"\n  {YELLOW}[Turn {i+1}] {first_name}:{RESET} {text}")

        if not addressed:
            print(f"  {GREY}→ (not addressed to bot — expecting silence){RESET}")
            results.append({"turn": i+1, "addressed": False, "response": None, "expect": expect})
            continue

        ctx = _make_ctx(user_id, first_name, text, chat_id, bot, list(recent_messages))
        bot.sent.clear()

        response = await run_turn(llm_handler, club, ctx, list(recent_messages[:-1]))
        recent_messages.append({"sender_name": "Xaana", "text": response})

        print(f"\n  {GREEN}[Bot response]{RESET}")
        print(_wrap(response))

        if verbose and expect:
            print(f"\n  {GREY}[Expected behaviour]{RESET}")
            print(_wrap(expect.strip(), indent="    "))

        results.append({"turn": i+1, "addressed": True, "response": response, "expect": expect})

    return {"id": sid, "description": desc, "turns": results}


async def main(filter_id: Optional[str], verbose: bool) -> None:
    data = yaml.safe_load(SCENARIOS_FILE.read_text(encoding="utf-8"))
    club = data["club"]
    scenarios = data["scenarios"]

    if filter_id:
        scenarios = [s for s in scenarios if s["id"] == filter_id]
        if not scenarios:
            print(f"No scenario with id '{filter_id}'. Available:")
            for s in data["scenarios"]:
                print(f"  {s['id']}")
            sys.exit(1)

    print(f"\n{BOLD}{'='*80}{RESET}")
    print(f"{BOLD}  Xaana club group-chat scenario runner{RESET}")
    print(f"  Club: {club['club_name']}  |  Scenarios: {len(scenarios)}")
    print(f"{BOLD}{'='*80}{RESET}")

    # Build LLM handler (uses env vars for API keys)
    llm_handler = LLMHandler(root_dir=str(ROOT / "tm_bot"))

    all_results = []
    for scenario in scenarios:
        result = await run_scenario(scenario, club, llm_handler, verbose=verbose)
        all_results.append(result)

    _print_separator()
    print(f"\n{BOLD}Done. {len(all_results)} scenario(s) run.{RESET}")
    if not verbose:
        print(f"{GREY}Run with --verbose to see expected behaviour alongside each response.{RESET}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run club group-chat scenarios")
    parser.add_argument("--scenario", metavar="ID", help="Run a single scenario by id")
    parser.add_argument("--verbose", action="store_true", help="Show expected behaviour for each turn")
    args = parser.parse_args()
    asyncio.run(main(filter_id=args.scenario, verbose=args.verbose))
