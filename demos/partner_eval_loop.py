"""
Partner eval loop: an LLM acts as the "user" in conversation with Zana.

Runs a configurable number of turns, captures the transcript, and optionally
produces a short report (memory, capability awareness, usefulness). Output is
for observation and examples of Zana's behavior—no pass/fail assertions.

Usage (from project root):
    python demos/partner_eval_loop.py --max-turns 10 --output demos/out/eval
    python demos/partner_eval_loop.py --max-turns 5 --seed "Focus on memory"

Requires: .env with GCP_PROJECT_ID, GCP_CREDENTIALS_B64, GCP_LOCATION (and optionally
OPENAI_API_KEY). Same env as Zana's LLM; partner uses the same model by default.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add tm_bot to path so that planner_bot, platforms, llms, utils resolve (same as tests/conftest)
ROOT = Path(__file__).resolve().parent.parent
TM_BOT_DIR = ROOT / "tm_bot"
if str(TM_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(TM_BOT_DIR))

# Load .env for LLM config
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from llms.llm_env_utils import load_llm_env
from planner_bot import PlannerBot
from platforms.testing import MockPlatformAdapter, TestResponseService
from platforms.testing.cli_handler_wrapper import CLIHandlerWrapper
from utils.logger import get_logger

logger = get_logger(__name__)

PARTNER_SYSTEM_PROMPT = """You are a user in a conversation with Zana, a task and promise planner (e.g. create promises, log time, list promises, weekly reports). Your goal is to have a natural multi-turn dialogue and to probe:
1. **Memory** – e.g. ask what you just added, or what was decided earlier.
2. **Capabilities** – e.g. ask what Zana can do, or try commands like /promises or /me.
3. **Usefulness** – create a promise, log time, list promises, and see if Zana helps.

Reply with ONLY your next message as the user (plain text). No preamble.
To end the conversation and give a short report, reply with exactly:
END_REPORT
Then on the next lines write 1–2 sentences each on: memory (did Zana remember earlier turns?), capability awareness (did Zana know what it can do?), and usefulness (did Zana complete tasks helpfully?)."""

END_MARKER = "END_REPORT"


def _build_partner_model():
    """Build partner LLM from env (same as Zana: Vertex or OpenAI)."""
    cfg = load_llm_env()
    if cfg.get("GCP_PROJECT_ID"):
        return ChatGoogleGenerativeAI(
            model=cfg.get("GCP_GEMINI_MODEL", "gemini-2.5-flash"),
            project=cfg["GCP_PROJECT_ID"],
            location=cfg.get("GCP_LLM_LOCATION", cfg.get("GCP_LOCATION", "us-central1")),
            temperature=0.7,
        )
    if cfg.get("OPENAI_API_KEY"):
        return ChatOpenAI(
            model=os.getenv("OPENAI_PARTNER_MODEL", "gpt-4o-mini"),
            openai_api_key=cfg["OPENAI_API_KEY"],
            temperature=0.7,
        )
    raise ValueError("Set GCP_PROJECT_ID + GCP_CREDENTIALS_B64 or OPENAI_API_KEY in .env")


def partner_next_message(
    transcript: List[Dict[str, Any]],
    seed: Optional[str],
    model: Any,
) -> Tuple[str, Optional[str], bool]:
    """
    Call partner LLM with transcript (and optional seed). Returns (next_message, report_text, ended).
    If the model outputs END_REPORT, the rest is parsed as report and ended=True.
    """
    lines = []
    for entry in transcript:
        role = entry.get("role", "")
        content = entry.get("content", "")
        if role == "user":
            lines.append(f"User: {content}")
        else:
            lines.append(f"Zana: {content}")
    conv_text = "\n".join(lines) if lines else "(No messages yet. Start the conversation as the user.)"
    if seed:
        user_content = f"Scenario or focus: {seed}\n\n---\nConversation so far:\n{conv_text}"
    else:
        user_content = f"Conversation so far:\n{conv_text}"

    messages = [
        SystemMessage(content=PARTNER_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]
    response = model.invoke(messages)
    content = (response.content or "").strip()

    if END_MARKER in content:
        parts = content.split(END_MARKER, 1)
        report = parts[1].strip() if len(parts) > 1 else ""
        return "", report or None, True
    return content, None, False


async def run_loop(
    max_turns: int,
    seed: Optional[str],
    output_path: Path,
    user_id: int = 1,
    root_dir: Optional[Path] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Run the partner–Zana loop. Returns (transcript, report).
    """
    root_dir = root_dir or Path(tempfile.mkdtemp(prefix="zana_partner_eval_"))
    root_dir.mkdir(parents=True, exist_ok=True)

    adapter = MockPlatformAdapter()
    bot = PlannerBot(adapter, root_dir=str(root_dir))
    if not (bot.message_handlers and bot.callback_handlers):
        raise RuntimeError("PlannerBot did not get message/callback handlers")
    handler_wrapper = CLIHandlerWrapper(bot.message_handlers, bot.callback_handlers)
    adapter.response_service.clear()

    partner_model = _build_partner_model()
    transcript: List[Dict[str, Any]] = []
    report: Optional[str] = None
    turn = 0

    while turn < max_turns:
        turn += 1
        next_msg, report_text, ended = partner_next_message(transcript, seed, partner_model)
        if ended:
            report = report_text
            break
        if not next_msg.strip():
            next_msg = "(User said nothing; ending.)"
            break

        transcript.append({"turn": turn, "role": "user", "content": next_msg, "timestamp": datetime.now(timezone.utc).isoformat()})
        logger.info("Partner (turn %s): %s", turn, next_msg[:80])

        try:
            await handler_wrapper.handle_message(next_msg, user_id=user_id)
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.exception("Zana handle_message failed: %s", e)
            transcript.append({
                "turn": turn,
                "role": "assistant",
                "content": f"[Error: {e}]",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            continue

        messages = adapter.response_service.get_messages_for_user(user_id)
        new_reply = (messages[-1].get("text") or "").strip() if messages else ""
        transcript.append({
            "turn": turn,
            "role": "assistant",
            "content": new_reply,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("Zana (turn %s): %s", turn, (new_reply[:80] + "..." if len(new_reply) > 80 else new_reply))

    return transcript, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Partner eval loop: LLM user vs Zana")
    parser.add_argument("--max-turns", type=int, default=10, help="Max conversation turns (default 10)")
    parser.add_argument("--seed", type=str, default=None, help="Optional scenario/theme for the partner")
    parser.add_argument("--output", type=str, default=None, help="Output path (directory or base name); default stdout + demos/out/partner_eval")
    parser.add_argument("--user-id", type=int, default=1, help="User ID for the simulated user (default 1)")
    args = parser.parse_args()

    out_path = Path(args.output) if args.output else ROOT / "demos" / "out" / "partner_eval"
    out_path = out_path.resolve()
    if out_path.suffix:
        base = out_path.stem
        out_dir = out_path.parent
    else:
        out_dir = out_path
        base = "partner_eval"
    out_dir.mkdir(parents=True, exist_ok=True)

    transcript, report = asyncio.run(run_loop(
        max_turns=args.max_turns,
        seed=args.seed,
        output_path=out_dir,
        user_id=args.user_id,
    ))

    # Write transcript (JSON)
    transcript_path = out_dir / f"{base}.json"
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump({"transcript": transcript, "report": report}, f, indent=2, ensure_ascii=False)
    print(f"Transcript written to {transcript_path}")

    # Write report (markdown) if present
    if report:
        report_path = out_dir / f"{base}.report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# Partner Eval Report\n\n")
            f.write(report)
        print(f"Report written to {report_path}")

    # Summary to stdout
    print(f"\nTurns: {len([t for t in transcript if t.get('role') == 'user'])}")
    if report:
        print("\n--- Report ---\n")
        print(report)


if __name__ == "__main__":
    main()
