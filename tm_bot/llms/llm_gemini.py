from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Dict, List

from google import genai
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

# Allow running this file directly from repo root:
# `python tm_bot/llms/llm_gemini.py ...`
_TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _TM_BOT_DIR not in sys.path:
    sys.path.insert(0, _TM_BOT_DIR)

from llms.agent import _ensure_messages_have_content, _invoke_model, _parse_plan, _track_llm_call
from llms.llm_env_utils import load_llm_env
from llms.llm_handler import LLMHandler
from llms.tool_wrappers import _current_user_id, _current_user_language


def _payload_stats(messages: List[BaseMessage]) -> Dict[str, int]:
    total_chars = 0
    for msg in messages or []:
        content = getattr(msg, "content", "")
        total_chars += len(str(content or ""))
    return {
        "message_count": len(messages or []),
        "chars_total": total_chars,
    }


def run_simple(prompt: str, model_override: str | None, repeat: int) -> None:
    cfg = load_llm_env()
    model_name = model_override or cfg["GCP_GEMINI_MODEL"]
    client = genai.Client(
        vertexai=True,
        project=cfg["GCP_PROJECT_ID"],
        location=cfg["GCP_LLM_LOCATION"],
    )
    print(f"[simple] model={model_name} location={cfg['GCP_LLM_LOCATION']} repeat={repeat}")
    for i in range(repeat):
        t0 = time.perf_counter()
        resp = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        dt_ms = (time.perf_counter() - t0) * 1000.0
        text = getattr(resp, "text", "") or ""
        print(f"[simple] run={i + 1} duration_ms={dt_ms:.2f} chars={len(text)}")
        print(text[:600])


def run_isolated_planner(
    message: str,
    user_id: str,
    lang: str,
    mode: str,
    repeat: int,
) -> None:
    root_dir = os.getenv("ROOT_DIR") or os.getcwd()
    handler = LLMHandler(root_dir=root_dir)

    uid_token = _current_user_id.set(str(user_id))
    lang_token = _current_user_language.set(lang or "en")
    try:
        planner_prompt = handler._get_planner_prompt_for_mode(mode)
        full_system = handler._get_system_message_main(user_language=lang, user_id=str(user_id), mode=mode)
        combined_system = planner_prompt + "\n\n" + full_system.content

        messages: List[BaseMessage] = [
            SystemMessage(content=combined_system),
            HumanMessage(content=message),
        ]
        validated_messages = _ensure_messages_have_content(messages)
        stats = _payload_stats(validated_messages)
        print(
            f"[isolated-planner] mode={mode} user_id={user_id} lang={lang} "
            f"message_count={stats['message_count']} chars_total={stats['chars_total']} repeat={repeat}"
        )

        for i in range(repeat):
            _track_llm_call("isolated_planner", "planner_model")
            t0 = time.perf_counter()
            result = _invoke_model(handler.planner_model, validated_messages)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            content = getattr(result, "content", "") or ""
            text = str(content)
            print(f"[isolated-planner] run={i + 1} duration_ms={dt_ms:.2f} response_chars={len(text)}")
            try:
                plan = _parse_plan(content)
                steps = [s.model_dump() for s in plan.steps]
                print(
                    f"[isolated-planner] parsed_steps={len(steps)} "
                    f"intent={plan.detected_intent} confidence={plan.intent_confidence}"
                )
                for idx, step in enumerate(steps[:4], 1):
                    print(f"  step{idx}: kind={step.get('kind')} tool={step.get('tool_name')} purpose={step.get('purpose')}")
            except Exception as exc:
                print(f"[isolated-planner] parse_error={type(exc).__name__}: {str(exc)}")
                print(text[:1200])
    finally:
        _current_user_id.reset(uid_token)
        _current_user_language.reset(lang_token)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini quick test helper (simple + isolated planner).")
    parser.add_argument("--mode", dest="run_mode", choices=["simple", "isolated-planner"], default="simple")
    parser.add_argument("--prompt", default="Say hi from Gemini on GCP!")
    parser.add_argument("--model", default=None, help="Optional model override for --mode simple.")
    parser.add_argument("--repeat", type=int, default=1)

    parser.add_argument("--message", default="what are my tasks today")
    parser.add_argument("--user-id", default="108648163")
    parser.add_argument("--lang", default="en")
    parser.add_argument(
        "--planner-mode",
        choices=["operator", "strategist", "social", "engagement"],
        default="operator",
    )
    args = parser.parse_args()

    if args.run_mode == "isolated-planner":
        run_isolated_planner(
            message=args.message,
            user_id=str(args.user_id),
            lang=args.lang,
            mode=args.planner_mode,
            repeat=max(1, int(args.repeat)),
        )
        return

    run_simple(
        prompt=args.prompt,
        model_override=args.model,
        repeat=max(1, int(args.repeat)),
    )


if __name__ == "__main__":
    main()
