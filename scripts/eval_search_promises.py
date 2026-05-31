"""Quantitative eval of search_promises against a realistic promise set.

Drives the REAL adapter method (PlannerAPIAdapter.search_promises) offline via an
in-memory fake repo, so there are no DB calls and no prod side effects. Queries are
labeled by *human intent*; a synonym/typo that the substring matcher misses counts as
a recall failure. Novel queries (no relevant promise) are scored as the DESIRED
one-time-promise fallback path, not as failures.
"""
import os
import re
import sys
import json
import types
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tm_bot"))
from services.planner_api_adapter import PlannerAPIAdapter  # noqa: E402

# --- Real promise set (user 108648163), texts exactly as stored ---
PROMISES = [
    ("C01", "Play_Cheenva"), ("C02", "Crossfit_and_Gym"), ("P01", "Deep_work_(Stage11)"),
    ("P06", "Call_my_family"), ("P07", "Home_chores_/_Cooking"),
    ("P08", "Practice_French/English_(Comprehension_Oral)"), ("P09", "Play_piano"),
    ("P10", "Do_sport"), ("P11", "Exercise_back_and_neck_correction"),
    ("P12", "Hair_&_skin_care"), ("P13", "Reading_books"), ("P16", "Next_One"),
    ("P17", "Building_robots"), ("P18", "Work_on_Zana"), ("P19", "Forcapil_(for_hair)"),
    ("P20", "Study_English"), ("P21", "buy_volleyball_tickets_for_Iran_vs_France_match"),
    ("T02", "Talk_to_a_Mentor"),
]

def _mk(id_, text):
    return types.SimpleNamespace(id=id_, text=text, hours_per_week=1.0, start_date=None, end_date=None)

FAKE = types.SimpleNamespace(
    promises_repo=types.SimpleNamespace(list_promises=lambda u: [_mk(i, t) for i, t in PROMISES]),
    actions_repo=types.SimpleNamespace(list_actions=lambda u: []),
)

# --- Labeled query battery. expect: id | tuple(ids) | None(novel -> one-time) ---
# cat: exact | ambiguous | synonym | typo | phrase | novel
Q = [
    # exact / substring (should resolve cleanly)
    ("cooking", "P07", "exact"), ("cook", "P07", "exact"), ("chores", "P07", "exact"),
    ("piano", "P09", "exact"), ("reading", "P13", "exact"), ("read", "P13", "exact"),
    ("books", "P13", "exact"), ("family", "P06", "exact"), ("crossfit", "C02", "exact"),
    ("gym", "C02", "exact"), ("zana", "P18", "exact"), ("mentor", "T02", "exact"),
    ("volleyball", "P21", "exact"), ("tickets", "P21", "exact"), ("forcapil", "P19", "exact"),
    ("cheenva", "C01", "exact"), ("robots", "P17", "exact"), ("robot", "P17", "exact"),
    ("neck", "P11", "exact"), ("skin", "P12", "exact"), ("french", "P08", "exact"),
    ("deep work", "P01", "exact"), ("study english", "P20", "exact"), ("do sport", "P10", "exact"),
    ("building robots", "P17", "exact"), ("talk to a mentor", "T02", "exact"),
    ("play piano", "P09", "exact"), ("call my family", "P06", "exact"),

    # genuinely ambiguous (multiple valid targets)
    ("play", ("C01", "P09"), "ambiguous"), ("english", ("P08", "P20"), "ambiguous"),
    ("hair", ("P12", "P19"), "ambiguous"), ("work", ("P01", "P18"), "ambiguous"),

    # synonyms / paraphrase (intent target; substring often misses -> recall test)
    ("cuisine", "P07", "synonym"), ("meal prep", "P07", "synonym"),
    ("tidy up", "P07", "synonym"), ("clean the house", "P07", "synonym"),
    ("phone mom", "P06", "synonym"), ("parents", "P06", "synonym"),
    ("call parents", "P06", "synonym"), ("novel", "P13", "synonym"),
    ("book", "P13", "synonym"), ("language practice", ("P08", "P20"), "synonym"),
    ("learn french", "P08", "synonym"), ("learn english", "P20", "synonym"),
    ("coding", ("P17", "P18"), "synonym"), ("programming", ("P17", "P18"), "synonym"),
    ("app development", "P18", "synonym"), ("haircare", "P12", "synonym"),
    ("skincare", "P12", "synonym"), ("fitness", ("C02", "P10", "P11"), "synonym"),
    ("workout", ("C02", "P10", "P11"), "synonym"), ("sport", ("C02", "P10", "P11"), "synonym"),
    ("exercise", ("C02", "P10", "P11"), "synonym"), ("weightlifting", "C02", "synonym"),
    ("mentorship", "T02", "synonym"), ("career advice", "T02", "synonym"),

    # typos
    ("cookng", "P07", "typo"), ("cokking", "P07", "typo"), ("robto", "P17", "typo"),
    ("robos", "P17", "typo"), ("pian", "P09", "typo"), ("familly", "P06", "typo"),
    ("vollyball", "P21", "typo"), ("crossft", "C02", "typo"), ("redaing", "P13", "typo"),
    ("menter", "T02", "typo"), ("frnch", "P08", "typo"), ("pianno", "P09", "typo"),

    # natural multiword phrases
    ("cook tuna tonight", "P07", "phrase"), ("play the piano", "P09", "phrase"),
    ("work on the app", "P18", "phrase"), ("call my mom", "P06", "phrase"),
    ("go to the gym", "C02", "phrase"), ("read a book", "P13", "phrase"),
    ("do some sport", "P10", "phrase"), ("talk to mentor", "T02", "phrase"),
    ("build a robot", "P17", "phrase"), ("study french and english", ("P08", "P20"), "phrase"),

    # novel -> should be no-match -> one-time promise fallback (DESIRED)
    ("dentist appointment", None, "novel"), ("buy groceries", None, "novel"),
    ("car insurance", None, "novel"), ("meditate", None, "novel"),
    ("water the plants", None, "novel"), ("write a blog post", None, "novel"),
    ("do taxes", None, "novel"), ("yoga", None, "novel"), ("swimming", None, "novel"),
    ("clean the garage", None, "novel"), ("doctor visit", None, "novel"),
    ("pay rent", None, "novel"), ("birthday gift", None, "novel"), ("learn guitar", None, "novel"),
]


def parse_search(out: str):
    """Return (match_type, set_of_ids). match_type in {single, multi, none}."""
    s = out.strip()
    if s.startswith("{"):
        try:
            j = json.loads(s)
            if j.get("single_match"):
                return "single", {j.get("promise_id")}
        except Exception:
            pass
    if s.startswith(("No promises found", "You don't have", "Please provide")):
        return "none", set()
    ids = set(re.findall(r"#([A-Za-z0-9]+)", s))
    if ids:
        return "multi", ids
    return "none", set()


def expect_set(expect):
    if expect is None:
        return None
    return set(expect) if isinstance(expect, tuple) else {expect}


def main():
    rows = []
    for query, expect, cat in Q:
        out = PlannerAPIAdapter.search_promises(FAKE, 108648163, query)
        mtype, ids = parse_search(out)
        E = expect_set(expect)
        rows.append({"q": query, "cat": cat, "expect": E, "mtype": mtype, "ids": ids})

    total = len(rows)
    targeted = [r for r in rows if r["expect"] is not None]
    novel = [r for r in rows if r["expect"] is None]

    def recall(r):  # target found at all
        return bool(r["expect"] & r["ids"])

    def clean_resolve(r):  # single auto-select to a correct target
        return r["mtype"] == "single" and bool(r["ids"] & r["expect"])

    n_recall = sum(recall(r) for r in targeted)
    n_clean = sum(clean_resolve(r) for r in targeted)
    n_multi_ok = sum(1 for r in targeted if r["mtype"] == "multi" and recall(r))
    n_miss = sum(1 for r in targeted if not recall(r))

    novel_correct = sum(1 for r in novel if r["mtype"] == "none")
    novel_false_attach = sum(1 for r in novel if r["mtype"] != "none")

    mtype_dist = defaultdict(int)
    for r in rows:
        mtype_dist[r["mtype"]] += 1

    def pct(a, b):
        return f"{(100.0 * a / b):5.1f}%" if b else "  n/a"

    print(f"\n{'='*64}")
    print(f"search_promises eval — {total} queries vs {len(PROMISES)} promises")
    print(f"{'='*64}")
    print(f"match-type distribution:  single={mtype_dist['single']}  "
          f"multi={mtype_dist['multi']}  none={mtype_dist['none']}")

    print(f"\n--- TARGETED queries (n={len(targeted)}): a real promise exists ---")
    print(f"  recall@any (target found):      {pct(n_recall, len(targeted))}  ({n_recall}/{len(targeted)})")
    print(f"  clean auto-resolve (single==target): {pct(n_clean, len(targeted))}  ({n_clean}/{len(targeted)})")
    print(f"  found-but-needs-pick (multi):   {pct(n_multi_ok, len(targeted))}  ({n_multi_ok}/{len(targeted)})")
    print(f"  MISS (target not found):        {pct(n_miss, len(targeted))}  ({n_miss}/{len(targeted)})")

    print(f"\n--- NOVEL queries (n={len(novel)}): no promise -> want one-time fallback ---")
    print(f"  correct no-match (-> one-time): {pct(novel_correct, len(novel))}  ({novel_correct}/{len(novel)})")
    print(f"  WRONG attach (false match):     {pct(novel_false_attach, len(novel))}  ({novel_false_attach}/{len(novel)})")

    print(f"\n--- by category ---")
    cats = defaultdict(lambda: [0, 0, 0])  # [n, good, label-specific]
    for r in rows:
        c = cats[r["cat"]]
        c[0] += 1
        if r["expect"] is None:
            c[1] += 1 if r["mtype"] == "none" else 0
        else:
            c[1] += 1 if recall(r) else 0
    print(f"  {'category':<11} {'n':>3} {'good':>5}  rate")
    for cat in ["exact", "ambiguous", "synonym", "typo", "phrase", "novel"]:
        n, good, _ = cats[cat]
        metric = "no-match" if cat == "novel" else "recall"
        print(f"  {cat:<11} {n:>3} {good:>5}  {pct(good, n)}  ({metric})")

    print(f"\n--- recall MISSES (targeted queries where the right promise was not found) ---")
    for r in targeted:
        if not recall(r):
            print(f"  [{r['cat']:<8}] {r['q']!r:<28} -> {r['mtype']:<5} {sorted(r['ids']) or ''}  (wanted {sorted(r['expect'])})")

    if novel_false_attach:
        print(f"\n--- NOVEL false-attaches (would wrongly attach instead of one-time) ---")
        for r in novel:
            if r["mtype"] != "none":
                print(f"  {r['q']!r:<28} -> {r['mtype']} {sorted(r['ids'])}")
    print()


if __name__ == "__main__":
    main()
