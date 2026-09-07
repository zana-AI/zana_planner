#!/usr/bin/env python3
"""Rank current French flashcards and compare them with latest Zotero highlights."""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sqlite3
import unicodedata
from pathlib import Path


def clean(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", "", value or ""))
    value = re.sub(r"\*{1,2}", "", value)
    return re.sub(r"\s+", " ", value).strip()


def key(value: str) -> str:
    value = clean(value).lower()
    value = "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))
    value = re.sub(r"^[\s'\"«».,:;!?-]*(?:un|une|le|la|les|l'|du|des)\s+", "", value)
    value = re.sub(r"\([^)]*\)", "", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def score(row: dict) -> dict[str, int | str]:
    front = clean(row.get("front", ""))
    back = clean(row.get("back", ""))
    example = clean(row.get("example", ""))
    source_context = clean(row.get("source_context", ""))
    words = front.split()
    # The score is deliberately decomposed so it can be used as an editing queue:
    # prompt fit (25), answer clarity (35), context/examples (25), learning value (15).
    # A card can contain a useful word and still rank low when its reverse side is
    # only a bare translation or lacks enough context to make the word memorable.
    front_points = 12
    if not front:
        front_points = 0
    elif 1 <= len(words) <= 5 and 3 <= len(front) <= 40:
        front_points += 10
    elif len(words) <= 8 and len(front) <= 60:
        front_points += 4
    else:
        front_points -= 6
    if len(words) > 8 or re.search(r"[.!?]$", front):
        front_points -= 8
    if re.search(r"\b(?:je|tu|il|elle|nous|vous|ils|elles)\b", front.lower()):
        front_points -= 6
    front_points = max(0, min(25, front_points))

    answer_points = 0
    if not back:
        pass
    else:
        # A useful definition earns more than an isolated translation. The
        # penalties catch the exact kind of low-value or hard-to-reverse card
        # the user called out (e.g. "Féminin de ..." and unexplained shorthand).
        answer_points = 12 if len(back.split()) <= 5 else 20
        if len(back) >= 40:
            answer_points += 5
        if len(back) >= 85:
            answer_points += 5
        if re.search(r"[;:.]", back):
            answer_points += 2
        if len(back) < 18:
            answer_points -= 4
        if re.search(r"\b(?:qqn|qqch|qch)\b", back, re.I):
            answer_points -= 5
        if re.match(r"féminin de\b", back, re.I):
            answer_points -= 12
        if re.match(r"homographe\b", back, re.I):
            answer_points -= 7
        if len(back) > 220:
            answer_points -= 5
    answer_points = max(0, min(35, answer_points))

    context_points = 0
    if example:
        context_points = 16
        if len(example) < 18:
            context_points -= 6
        if "euh" in example.lower() or not re.search(r"[.!?]", example):
            context_points -= 6
        if len(example.split()) > 5 and re.search(r"[.!?]", example):
            context_points += 2
    elif source_context:
        context_points = 5
    if row.get("source_url"):
        context_points += 3
    if row.get("note_fa"):
        context_points += 2
    context_points = min(25, max(0, context_points))

    value_points = 12
    low_value = {
        "citoyennes dès l'enfance", "citoyen / citoyenne", "être / suivre : suis",
        "être / suivre : je suis", "production orale", "maximum une par jour",
    }
    if front.lower() in {x.lower() for x in low_value}:
        value_points -= 4
    if front.lower() in {"jalouse", "suis", "cédez", "inondez", "ne pas"}:
        value_points -= 7
    if re.search(r"\b(?:maximum|production|source|page|unité|leçon)\b", front, re.I):
        value_points -= 4
    if len(words) == 1 and len(front) <= 3:
        value_points -= 3
    if re.match(r"^(?:l'heure civique|lingoda|language reactor)\b", front, re.I):
        value_points -= 5
    value_points = max(0, min(15, value_points))

    total = max(0, min(100, front_points + answer_points + context_points + value_points))
    if total >= 80:
        verdict = "strong"
    elif total >= 65:
        verdict = "useful"
    elif total >= 45:
        verdict = "needs polish"
    else:
        verdict = "rewrite/remove candidate"
    return {
        "score": total,
        "verdict": verdict,
        "prompt_score": front_points,
        "answer_score": answer_points,
        "context_score": context_points,
        "value_score": value_points,
    }


def read_cards(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_zotero(path: Path) -> list[dict]:
    con = sqlite3.connect(path)
    rows = con.execute("""
      SELECT text, comment, pageLabel, itemID
      FROM itemAnnotations
      WHERE parentItemID=143 AND text IS NOT NULL AND trim(text)<>''
      ORDER BY itemID
    """).fetchall()
    con.close()
    return [{"highlight": r[0], "comment": r[1] or "", "page": r[2] or "", "annotation_id": r[3]} for r in rows]


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", type=Path, default=Path("exports/french_learning/flashcards.csv"))
    ap.add_argument("--zotero", type=Path, default=Path("exports/zotero_readonly.sqlite"))
    ap.add_argument("--out", type=Path, default=Path("exports/french_learning"))
    args = ap.parse_args()
    cards = read_cards(args.cards)
    for row in cards:
        fields = json.loads(row.get("fields_json") or "{}")
        row["source_url"] = fields.get("source_url", "")
        row["source_context"] = fields.get("source_context", "")
        row.update(score(row))
        row["back_clean"] = clean(row.get("back", ""))
        row["front_clean"] = clean(row.get("front", ""))
    cards.sort(key=lambda r: (-int(r["score"]), r["front"].lower()))
    write_csv(args.out / "ranked_french_cards.csv", cards, ["score", "verdict", "prompt_score", "answer_score", "context_score", "value_score", "source", "deck_path", "front_clean", "front", "back_clean", "example", "note_fa", "source_url", "source_context", "note_id"])

    by_key = {key(row["front"]): row for row in cards}
    candidates = []
    for row in read_zotero(args.zotero):
        match = by_key.get(key(row["highlight"]))
        candidates.append({
            **row,
            "status": "already a card" if match else "new Zotero candidate",
            "matched_card": match["front"] if match else "",
            "score": match["score"] if match else 0,
            "verdict": match["verdict"] if match else "new card needed",
        })
    write_csv(args.out / "latest_zotero_edito_highlights.csv", candidates, ["status", "score", "verdict", "highlight", "comment", "page", "matched_card", "annotation_id"])

    md = ["# Ranked French flashcards", "", "Score: 0–100 = prompt fit (25) + answer clarity (35) + context/examples (25) + learning value (15). Strong ≥80; useful 65–79; needs polish 45–64; rewrite/remove candidate <45.", "", "| # | Score | Breakdown | Verdict | Source | Front | Back / translation | Example |", "|---:|---:|---|---|---|---|---|---|"]
    for i, row in enumerate(cards, 1):
        breakdown = f"P{row['prompt_score']}/25 A{row['answer_score']}/35 C{row['context_score']}/25 V{row['value_score']}/15"
        vals = [str(i), str(row["score"]), breakdown, row["verdict"], row["source"], row["front_clean"], row["back_clean"], row["example"]]
        md.append("| " + " | ".join(v.replace("|", "\\|").replace("\n", " ") for v in vals) + " |")
    md += ["", f"Latest Zotero: {len(candidates)} non-empty highlights; {sum(c['status']=='already a card' for c in candidates)} matched current cards; {sum(c['status']=='new Zotero candidate' for c in candidates)} still need card authoring."]
    (args.out / "ranked_french_cards.md").write_text("\n".join(md), encoding="utf-8")
    print(f"Ranked {len(cards)} current cards; exported {len(candidates)} latest Zotero highlights")


if __name__ == "__main__":
    main()
