from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Sequence

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


def _percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    rank = max(0.0, min(1.0, p)) * (len(sorted_vals) - 1)
    lower = int(rank)
    upper = min(len(sorted_vals) - 1, lower + 1)
    frac = rank - lower
    return float(sorted_vals[lower] * (1.0 - frac) + sorted_vals[upper] * frac)


def _is_mutation_intent(intent: str | None) -> bool:
    text = str(intent or "").upper()
    if not text:
        return False
    mutation_hints = ("CREATE", "ADD", "UPDATE", "DELETE", "REMOVE", "LOG", "SET", "EDIT")
    return any(h in text for h in mutation_hints)


def _load_scenarios(scenario_name: str, scenario_file: str | None) -> List[str]:
    if scenario_file:
        with open(scenario_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            scenarios = [str(item).strip() for item in data if str(item).strip()]
            if scenarios:
                return scenarios
        raise ValueError(f"Scenario file must be a JSON array of strings: {scenario_file}")

    builtin: Dict[str, List[str]] = {
        "default": [
            "what's your name",
            "what are my tasks next week",
            "have I done anything on P22 recently",
            "what's p08",
            "do you know what's my latest activity ?",
            "can you log my p02 for 3 hours",
        ],
        "read-heavy": [
            "what are my tasks next week",
            "what's p08",
            "have I done anything on P22 recently",
            "what's my latest activity, simply",
            "how many tasks can I do in one day out of them?",
        ],
        "mutation-heavy": [
            "add a promise to drink water 10 minutes a day",
            "can you log my p02 for 3 hours",
            "log 45 minutes for p08 today",
            "delete promise p25",
            "update p08 to 3 hours weekly",
        ],
        "clarification-heavy": [
            "maybe we can find an activity for me next week about music?",
            "how many hours per day should I spend time on it?",
            "wait wait",
            "do you know what's my latest activity ?",
        ],
    }
    scenarios = builtin.get(scenario_name, [])
    if not scenarios:
        known = ", ".join(sorted(builtin.keys()))
        raise ValueError(f"Unknown scenario set '{scenario_name}'. Available: {known}")
    return scenarios


@dataclass
class _StressCall:
    duration_s: float
    ok: bool
    stop_reason: str
    error_code: str
    fallback_used: bool
    tool_outputs: int
    mutation_guarded: bool


class _FallbackEventTap(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self._events = 0

    @property
    def events(self) -> int:
        return self._events

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.msg
        if isinstance(msg, dict) and msg.get("event") == "primary_model_fallback":
            self._events += 1


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


def run_routed_stress(
    user_id: str,
    lang: str,
    scenario_name: str,
    scenario_file: str | None,
    cycles: int,
    sleep_ms: int,
    reset_each_call: bool,
) -> None:
    scenarios = _load_scenarios(scenario_name=scenario_name, scenario_file=scenario_file)
    total_calls = max(1, cycles) * len(scenarios)
    print(
        f"[routed-stress] user_id={user_id} lang={lang} scenarios={len(scenarios)} "
        f"cycles={cycles} total_calls={total_calls} sleep_ms={max(0, sleep_ms)}"
    )

    llm_logger = logging.getLogger("llms.llm_handler")
    fallback_tap = _FallbackEventTap()
    llm_logger.addHandler(fallback_tap)

    records: List[_StressCall] = []
    run_idx = 0
    handler: LLMHandler | None = None
    try:
        for cycle in range(max(1, cycles)):
            if not reset_each_call:
                handler = LLMHandler(root_dir=os.getenv("ROOT_DIR") or os.getcwd())
            for message in scenarios:
                run_idx += 1
                if reset_each_call or handler is None:
                    handler = LLMHandler(root_dir=os.getenv("ROOT_DIR") or os.getcwd())

                before_fallback_events = fallback_tap.events
                t0 = time.perf_counter()
                try:
                    result = handler.get_response_api(
                        user_message=message,
                        user_id=str(user_id),
                        user_language=lang or "en",
                    )
                    dt_s = time.perf_counter() - t0
                    error_code = str(result.get("error") or "")
                    stop_reason = str(result.get("stop_reason") or "unknown")
                    tool_outputs = len(result.get("tool_outputs") or [])
                    detected_intent = str(result.get("detected_intent") or "")
                    truth = result.get("execution_truth") or {}
                    mutation_actions = int(truth.get("mutation_actions_count") or 0)
                    mutation_ok = int(truth.get("successful_mutation_actions_count") or 0)
                    guarded = _is_mutation_intent(detected_intent) and mutation_actions > 0 and mutation_ok == 0
                    after_fallback_events = fallback_tap.events
                    fallback_used = after_fallback_events > before_fallback_events
                    ok = not bool(error_code)
                    records.append(
                        _StressCall(
                            duration_s=dt_s,
                            ok=ok,
                            stop_reason=stop_reason,
                            error_code=error_code,
                            fallback_used=fallback_used,
                            tool_outputs=tool_outputs,
                            mutation_guarded=guarded,
                        )
                    )
                    print(
                        f"[routed-stress] run={run_idx}/{total_calls} cycle={cycle + 1} "
                        f"duration_s={dt_s:.2f} ok={ok} stop_reason={stop_reason} "
                        f"error={error_code or '-'} tool_outputs={tool_outputs} fallback={fallback_used} "
                        f"prompt={message[:70]!r}"
                    )
                except Exception as exc:
                    dt_s = time.perf_counter() - t0
                    after_fallback_events = fallback_tap.events
                    fallback_used = after_fallback_events > before_fallback_events
                    records.append(
                        _StressCall(
                            duration_s=dt_s,
                            ok=False,
                            stop_reason="exception",
                            error_code=type(exc).__name__,
                            fallback_used=fallback_used,
                            tool_outputs=0,
                            mutation_guarded=False,
                        )
                    )
                    print(
                        f"[routed-stress] run={run_idx}/{total_calls} cycle={cycle + 1} "
                        f"duration_s={dt_s:.2f} ok=False stop_reason=exception "
                        f"error={type(exc).__name__} fallback={fallback_used} prompt={message[:70]!r}"
                    )
                if sleep_ms > 0:
                    time.sleep(max(0, sleep_ms) / 1000.0)
    finally:
        llm_logger.removeHandler(fallback_tap)

    durations = [r.duration_s for r in records]
    ok_count = sum(1 for r in records if r.ok)
    fallback_count = sum(1 for r in records if r.fallback_used)
    guarded_count = sum(1 for r in records if r.mutation_guarded)
    total_tool_outputs = sum(r.tool_outputs for r in records)
    stop_reason_counts: Dict[str, int] = {}
    error_counts: Dict[str, int] = {}
    for r in records:
        stop_reason_counts[r.stop_reason] = stop_reason_counts.get(r.stop_reason, 0) + 1
        if r.error_code:
            error_counts[r.error_code] = error_counts.get(r.error_code, 0) + 1

    print("\n[routed-stress] SUMMARY")
    print(f"[routed-stress] calls={len(records)} ok={ok_count} failed={len(records) - ok_count}")
    print(
        f"[routed-stress] latency_s avg={sum(durations) / max(1, len(durations)):.2f} "
        f"p50={_percentile(durations, 0.50):.2f} p95={_percentile(durations, 0.95):.2f} "
        f"max={max(durations) if durations else 0.0:.2f}"
    )
    print(
        f"[routed-stress] fallback_used={fallback_count} total_tool_outputs={total_tool_outputs} "
        f"mutation_guarded={guarded_count}"
    )
    print(f"[routed-stress] stop_reasons={json.dumps(stop_reason_counts, ensure_ascii=False)}")
    if error_counts:
        print(f"[routed-stress] errors={json.dumps(error_counts, ensure_ascii=False)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gemini quick test helper (simple + isolated planner + routed stress)."
    )
    parser.add_argument(
        "--mode",
        dest="run_mode",
        choices=["simple", "isolated-planner", "routed-stress"],
        default="simple",
    )
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
    parser.add_argument(
        "--scenario-set",
        choices=["default", "read-heavy", "mutation-heavy", "clarification-heavy"],
        default="default",
        help="Built-in scenario set for --mode routed-stress.",
    )
    parser.add_argument(
        "--scenario-file",
        default=None,
        help="Optional JSON file with array of prompts for --mode routed-stress.",
    )
    parser.add_argument("--cycles", type=int, default=1, help="Scenario cycles for --mode routed-stress.")
    parser.add_argument("--sleep-ms", type=int, default=0, help="Sleep between calls for --mode routed-stress.")
    parser.add_argument(
        "--reset-each-call",
        action="store_true",
        help="Re-create LLMHandler for each call (disables chat-history accumulation).",
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

    if args.run_mode == "routed-stress":
        run_routed_stress(
            user_id=str(args.user_id),
            lang=args.lang,
            scenario_name=args.scenario_set,
            scenario_file=args.scenario_file,
            cycles=max(1, int(args.cycles)),
            sleep_ms=max(0, int(args.sleep_ms)),
            reset_each_call=bool(args.reset_each_call),
        )
        return

    run_simple(
        prompt=args.prompt,
        model_override=args.model,
        repeat=max(1, int(args.repeat)),
    )


if __name__ == "__main__":
    main()
