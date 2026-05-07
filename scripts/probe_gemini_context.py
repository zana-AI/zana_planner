#!/usr/bin/env python3
"""
Gemini context-length / rate-limit probe.

Sends requests with increasing context sizes and reports exactly where
errors start.  Reads GCP credentials from the same env vars the bot uses:

  GCP_PROJECT_ID       - required
  GCP_LOCATION         - region, default us-central1
  GCP_CREDENTIALS_B64  - base64-encoded service-account JSON
                         (if absent, falls back to GOOGLE_APPLICATION_CREDENTIALS / ADC)
  GCP_GEMINI_MODEL     - (optional) model override

By default the script loads /opt/zana-config/.env.prod (production).
Use --env staging to load /opt/zana-config/.env.staging instead.
You can also point at any file directly with --env-file /path/to/.env.

Usage (on the server, outside the container):
  python scripts/probe_gemini_context.py                        # prod
  python scripts/probe_gemini_context.py --env staging          # staging
  python scripts/probe_gemini_context.py --env-file /my/.env   # custom path
  python scripts/probe_gemini_context.py --model gemini-2.5-flash-lite
  python scripts/probe_gemini_context.py --delay 3 --stop-on-fail
"""

import argparse
import base64
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

_ZANA_CONFIG_DIR = Path("/opt/zana-config")
_ENV_FILE_MAP = {
    "prod": _ZANA_CONFIG_DIR / ".env.prod",
    "production": _ZANA_CONFIG_DIR / ".env.prod",
    "staging": _ZANA_CONFIG_DIR / ".env.staging",
    "stage": _ZANA_CONFIG_DIR / ".env.staging",
}


def _load_env_file(path: Path) -> None:
    try:
        from dotenv import load_dotenv
        if path.exists():
            load_dotenv(dotenv_path=path, override=False)
            print(f"[setup] Loaded env from {path}")
        else:
            print(f"[setup] WARNING: env file not found: {path}")
    except ImportError:
        # Fallback: parse key=value lines manually
        if not path.exists():
            print(f"[setup] WARNING: env file not found: {path}")
            return
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
        print(f"[setup] Loaded env from {path} (manual parse)")

try:
    from google import genai
except ImportError:
    print("ERROR: google-genai not installed. Run: pip install google-genai")
    sys.exit(1)


# Context sizes to probe (in characters; ~4 chars per token)
CHAR_TARGETS = [
    200,       # ~50 tokens
    800,       # ~200 tokens
    2_000,     # ~500 tokens
    4_000,     # ~1 K tokens
    8_000,     # ~2 K tokens
    20_000,    # ~5 K tokens
    40_000,    # ~10 K tokens
    80_000,    # ~20 K tokens
    160_000,   # ~40 K tokens
    320_000,   # ~80 K tokens
]

_FILLER = (
    "Alice and Bob were discussing the upcoming project deadline over coffee. "
    "They went through each task, estimated effort, and assigned owners carefully. "
    "The weather outside was grey and drizzly, but the office felt warm and focused. "
    "After two hours they had a clear action plan and felt confident about the sprint. "
)


def _make_context(target_chars: int) -> str:
    reps = (target_chars // len(_FILLER)) + 2
    return (_FILLER * reps)[:target_chars]


@dataclass
class ProbeResult:
    target_chars: int
    approx_tokens: int
    ok: bool
    latency_ms: float
    error: Optional[str]
    error_type: Optional[str]
    response_chars: int


def probe_one(client, model: str, target_chars: int) -> ProbeResult:
    context = _make_context(target_chars)
    prompt = (
        f"The following is a passage of {target_chars} characters. "
        "Summarize it in exactly one sentence.\n\n"
        + context
    )
    approx_tokens = len(prompt) // 4

    t0 = time.perf_counter()
    try:
        resp = client.models.generate_content(model=model, contents=prompt)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        text = getattr(resp, "text", "") or ""
        return ProbeResult(
            target_chars=target_chars,
            approx_tokens=approx_tokens,
            ok=True,
            latency_ms=latency_ms,
            error=None,
            error_type=None,
            response_chars=len(text),
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return ProbeResult(
            target_chars=target_chars,
            approx_tokens=approx_tokens,
            ok=False,
            latency_ms=latency_ms,
            error=str(exc)[:600],
            error_type=type(exc).__name__,
            response_chars=0,
        )


def _setup_credentials() -> None:
    creds_b64 = os.getenv("GCP_CREDENTIALS_B64")
    if not creds_b64:
        print("[setup] GCP_CREDENTIALS_B64 not set — using GOOGLE_APPLICATION_CREDENTIALS or ADC.")
        return
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        print(f"[setup] Using existing GOOGLE_APPLICATION_CREDENTIALS={os.environ['GOOGLE_APPLICATION_CREDENTIALS']}")
        return
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    tmp.write(base64.b64decode(creds_b64))
    tmp.close()
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name
    print(f"[setup] Credentials written to {tmp.name}")


def main(argv: List[str] = None) -> None:
    parser = argparse.ArgumentParser(description="Probe Gemini for context-length / rate-limit failures")
    parser.add_argument("--env", default="prod", metavar="ENV",
                        help="Which env file to load: prod (default) or staging")
    parser.add_argument("--env-file", default=None, metavar="PATH",
                        help="Explicit path to an env file (overrides --env)")
    parser.add_argument("--model", default=None,
                        help="Model to test (default: GCP_GEMINI_MODEL env var or gemini-2.5-flash)")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Seconds to wait between calls (default: 2.0)")
    parser.add_argument("--stop-on-fail", action="store_true",
                        help="Stop probing after the first failure")
    args = parser.parse_args(argv)

    # Load env file before reading any os.getenv values
    if args.env_file:
        _load_env_file(Path(args.env_file))
    else:
        env_path = _ENV_FILE_MAP.get(args.env.lower())
        if env_path is None:
            print(f"ERROR: Unknown --env value '{args.env}'. Use 'prod' or 'staging'.")
            sys.exit(1)
        _load_env_file(env_path)

    project_id = os.getenv("GCP_PROJECT_ID")
    base_location = os.getenv("GCP_LOCATION", "us-central1")
    model = args.model or os.getenv("GCP_GEMINI_MODEL", "gemini-2.5-flash")

    if not project_id:
        print("ERROR: GCP_PROJECT_ID env var is required.")
        sys.exit(1)

    _setup_credentials()

    # gemini-3-* models are only available in the "global" endpoint on Vertex AI.
    # Match the same logic used by llm_model_config.needs_global_location().
    GLOBAL_ONLY_PREFIXES = ("gemini-3-",)
    location = (
        "global"
        if any(model.startswith(p) for p in GLOBAL_ONLY_PREFIXES)
        else os.getenv("GCP_LLM_LOCATION") or base_location
    )

    client = genai.Client(vertexai=True, project=project_id, location=location)

    print(f"\n{'=' * 64}")
    print(f"  Gemini context-length probe")
    print(f"  model    : {model}")
    print(f"  project  : {project_id}")
    print(f"  location : {location}")
    if location == "global":
        print(f"  (global forced — gemini-3-* requires it)")
    print(f"  delay    : {args.delay}s between calls")
    print(f"{'=' * 64}\n")

    header = f"{'chars':>10}  {'~tokens':>8}  {'status':>6}  {'ms':>8}  {'resp_ch':>8}  error"
    print(header)
    print("-" * 80)

    results: List[ProbeResult] = []
    for i, target in enumerate(CHAR_TARGETS):
        if i > 0:
            time.sleep(args.delay)
        r = probe_one(client, model, target)
        results.append(r)
        status = "OK" if r.ok else "FAIL"
        err_snippet = (r.error or "")[:55].replace("\n", " ")
        print(
            f"{r.target_chars:>10,}  {r.approx_tokens:>8,}  {status:>6}  "
            f"{r.latency_ms:>8.0f}  {r.response_chars:>8,}  {err_snippet}"
        )
        if not r.ok and args.stop_on_fail:
            # Print the full error so nothing is hidden
            print(f"\n  Full error:\n{r.error}\n")
            print("[stop-on-fail] Stopping.")
            break

    # Summary
    ok_results = [r for r in results if r.ok]
    fail_results = [r for r in results if not r.ok]
    print(f"\n{'=' * 64}")
    if ok_results:
        best = max(ok_results, key=lambda r: r.target_chars)
        print(f"  Largest OK   : {best.target_chars:>10,} chars  (~{best.approx_tokens:,} tokens)  {best.latency_ms:.0f} ms")
    if fail_results:
        worst = min(fail_results, key=lambda r: r.target_chars)
        print(f"  First FAIL   : {worst.target_chars:>10,} chars  (~{worst.approx_tokens:,} tokens)  {worst.latency_ms:.0f} ms")
        print(f"\n  Distinct error types seen:")
        seen: dict = {}
        for r in fail_results:
            key = r.error_type or "Unknown"
            if key not in seen:
                seen[key] = r.error or ""
        for etype, emsg in seen.items():
            print(f"    [{etype}]")
            for line in emsg.splitlines()[:6]:
                print(f"      {line}")
    else:
        print("  All probes succeeded — no failures detected.")
    print(f"{'=' * 64}\n")


if __name__ == "__main__":
    main()
