"""Recall eval of the NEW LLM promise resolver vs the substring baseline.

Reuses the exact 92-query battery from eval_search_promises.py, but routes each query
through resolve_promise_with_llm using the real router model. Prints the same metrics so
the before/after is directly comparable.
"""
import os
import sys
import json
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tm_bot"))
sys.path.insert(0, HERE)

from eval_search_promises import Q, PROMISES, expect_set  # noqa: E402
from llms.resolvers import resolve_promise_with_llm  # noqa: E402
from llms.llm_handler import LLMHandler  # noqa: E402


def main():
    handler = LLMHandler()
    model = handler.router_model
    promises = [{"id": i, "text": t} for i, t in PROMISES]

    rows = []
    for query, expect, cat in Q:
        out = json.loads(resolve_promise_with_llm(model, query, promises))
        conf = out.get("confidence")
        resolved = out.get("resolved")
        ids = set(out.get("candidates") or [])
        if resolved:
            ids.add(str(resolved))
        rows.append({"q": query, "cat": cat, "expect": expect_set(expect), "conf": conf, "ids": ids})

    targeted = [r for r in rows if r["expect"] is not None]
    novel = [r for r in rows if r["expect"] is None]

    def recall(r):
        return bool(r["expect"] & r["ids"])

    def clean(r):
        return r["conf"] == "high" and bool(r["ids"] & r["expect"])

    n_recall = sum(recall(r) for r in targeted)
    n_clean = sum(clean(r) for r in targeted)
    n_miss = sum(1 for r in targeted if not recall(r))
    novel_ok = sum(1 for r in novel if r["conf"] == "none")
    novel_false = len(novel) - novel_ok

    def pct(a, b):
        return f"{(100.0 * a / b):5.1f}%" if b else "  n/a"

    print(f"\n{'='*60}")
    print(f"LLM promise-resolver eval — {len(rows)} queries vs {len(PROMISES)} promises")
    print(f"{'='*60}")
    print(f"--- TARGETED (n={len(targeted)}) — a real promise exists ---")
    print(f"  recall@any:            {pct(n_recall, len(targeted))}  ({n_recall}/{len(targeted)})   [substring baseline: 46.2%]")
    print(f"  clean auto-resolve:    {pct(n_clean, len(targeted))}  ({n_clean}/{len(targeted)})   [baseline: 41.0%]")
    print(f"  MISS:                  {pct(n_miss, len(targeted))}  ({n_miss}/{len(targeted)})   [baseline: 53.8%]")
    print(f"\n--- NOVEL (n={len(novel)}) — want 'none' -> one-time promise ---")
    print(f"  correct none:          {pct(novel_ok, len(novel))}  ({novel_ok}/{len(novel)})")
    print(f"  WRONG match:           {pct(novel_false, len(novel))}  ({novel_false}/{len(novel)})")

    cats = defaultdict(lambda: [0, 0])
    for r in rows:
        c = cats[r["cat"]]
        c[0] += 1
        c[1] += (r["conf"] == "none") if r["expect"] is None else recall(r)
    print(f"\n--- by category (recall, or no-match for novel) ---")
    for cat in ["exact", "ambiguous", "synonym", "typo", "phrase", "novel"]:
        n, good = cats[cat]
        print(f"  {cat:<11} {n:>3} {good:>3}  {pct(good, n)}")

    print(f"\n--- remaining MISSES ---")
    for r in targeted:
        if not recall(r):
            print(f"  [{r['cat']:<8}] {r['q']!r:<26} -> conf={r['conf']} {sorted(r['ids']) or ''} (wanted {sorted(r['expect'])})")
    if novel_false:
        print(f"\n--- NOVEL false-matches (would NOT create one-time promise) ---")
        for r in novel:
            if r["conf"] != "none":
                print(f"  {r['q']!r:<26} -> conf={r['conf']} {sorted(r['ids'])}")
    print()


if __name__ == "__main__":
    main()
