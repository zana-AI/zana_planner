from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

import html


DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _clamp(n: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, n))


def _progress_pct(spent: float, promised: float) -> int:
    if promised <= 0:
        return 0
    return int(_clamp((spent / promised) * 100.0, 0.0, 999.0))


def _status_emoji(progress: int) -> str:
    if progress >= 90:
        return "✅"
    if progress >= 60:
        return "🟡"
    if progress >= 30:
        return "🟠"
    return "🔴"


def _escape(s: Any) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def _week_days(week_start: datetime) -> List[date]:
    # week_start is Monday 00:00 from utils.get_week_range()
    start = week_start.date()
    return [start + timedelta(days=i) for i in range(7)]


def build_weekly_report_card_html(
    summary: Dict[str, Any],
    *,
    week_start: datetime,
    week_end: datetime,
    width: int = 1200,
) -> str:
    """
    Build an HTML weekly report card image.

    RTL handling strategy:
    - Use browser shaping (Chromium) and per-field `dir="auto"`.
    - Use `unicode-bidi: plaintext` so mixed RTL/LTR promise titles behave well.
    - Keep numeric fragments in `dir="ltr"` spans to avoid digit reordering in RTL contexts.
    """
    week_days = _week_days(week_start)

    # Totals
    total_promised = 0.0
    total_spent = 0.0
    for _pid, data in (summary or {}).items():
        total_promised += float((data or {}).get("hours_promised", 0.0) or 0.0)
        total_spent += float((data or {}).get("hours_spent", 0.0) or 0.0)

    # Cards
    cards: List[str] = []
    for pid, data in sorted((summary or {}).items(), key=lambda kv: str(kv[0])):
        d = data or {}
        title = str(d.get("text", "") or "")
        promised = float(d.get("hours_promised", 0.0) or 0.0)
        spent = float(d.get("hours_spent", 0.0) or 0.0)
        pct = _progress_pct(spent, promised)
        emoji = _status_emoji(min(pct, 100))

        # Day bars
        per_day = {sd.get("date"): float(sd.get("hours", 0.0) or 0.0) for sd in (d.get("sessions") or []) if sd}
        day_hours = [float(per_day.get(day, 0.0) or 0.0) for day in week_days]
        max_day = max(day_hours) if day_hours else 0.0
        baseline = max(promised / 7.0 if promised > 0 else 0.0, max_day, 0.25)

        bars_html = []
        for i, h in enumerate(day_hours):
            height_pct = int(_clamp((h / baseline) * 100.0, 0.0, 100.0))
            bars_html.append(
                f'<div class="dayCol" title="{DAY_LABELS[i]}: {h:.2f}h">'
                f'  <div class="dayBar" style="height:{height_pct}%"></div>'
                f'  <div class="dayLbl" dir="ltr">{DAY_LABELS[i][0]}</div>'
                f"</div>"
            )

        cards.append(
            f"""
            <section class="card">
              <div class="cardTop">
                <div class="cardTitle" dir="auto"><span class="emoji">{_escape(emoji)}</span><span class="titleText">{_escape(title)}</span></div>
                <div class="cardMeta">
                  <span class="pid" dir="ltr">#{_escape(pid)}</span>
                  <span class="ratio" dir="ltr">{spent:.1f}/{promised:.1f} h</span>
                  <span class="pct" dir="ltr">{min(pct, 100)}%</span>
                </div>
              </div>

              <div class="progressRow" aria-hidden="true">
                <div class="progressTrack">
                  <div class="progressFill" style="width:{int(_clamp(pct, 0, 100))}%"></div>
                </div>
              </div>

              <div class="daysRow" aria-hidden="true">
                {''.join(bars_html)}
              </div>
            </section>
            """.strip()
        )

    # Empty state
    empty_state = ""
    if not cards:
        empty_state = """
        <section class="empty">
          <div class="emptyTitle" dir="auto">No data available for this week</div>
        </section>
        """.strip()

    week_range = f"{week_start.strftime('%d %b')} - {week_end.strftime('%d %b')}"
    html_doc = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      :root {{
        --bg: #0b1020;
        --panel: #0f1730;
        --card: #0f1a38;
        --text: #e8eefc;
        --muted: rgba(232, 238, 252, 0.72);
        --border: rgba(232, 238, 252, 0.10);
        --accent: #5ba3f5;
        --accent2: #7dd3fc;
        --good: #22c55e;
        --warn: #f59e0b;
        --bad: #ef4444;
      }}

      /* Global */
      html, body {{
        padding: 0;
        margin: 0;
        background: var(--bg);
        color: var(--text);
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
      }}
      body {{
        width: {int(width)}px;
        font-family: "Noto Sans", "Noto Sans Arabic", "Noto Sans Hebrew", system-ui, -apple-system, "Segoe UI", Arial, sans-serif;
      }}

      /* Mixed RTL/LTR handling */
      .cardTitle, .titleText, .emptyTitle {{
        unicode-bidi: plaintext;
      }}

      .wrap {{
        padding: 28px 28px 30px 28px;
      }}

      .header {{
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 16px;
        padding: 18px 18px;
        border: 1px solid var(--border);
        border-radius: 18px;
        background: linear-gradient(135deg, rgba(91,163,245,0.20), rgba(125,211,252,0.08));
      }}
      .hTitle {{
        font-size: 22px;
        font-weight: 800;
        letter-spacing: 0.2px;
      }}
      .hSub {{
        font-size: 13px;
        color: var(--muted);
        margin-top: 4px;
      }}
      .hRight {{
        text-align: right;
        font-size: 13px;
        color: var(--muted);
      }}
      .hNums {{
        margin-top: 4px;
        font-weight: 700;
        color: var(--text);
      }}

      .grid {{
        margin-top: 18px;
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 14px;
      }}

      .card {{
        border: 1px solid var(--border);
        border-radius: 16px;
        background: linear-gradient(180deg, rgba(15,26,56,0.98), rgba(15,23,48,0.98));
        padding: 14px 14px 12px 14px;
      }}
      .cardTop {{
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 10px;
      }}
      .cardTitle {{
        flex: 1;
        min-width: 0;
        font-size: 15px;
        font-weight: 800;
        line-height: 1.25;
        display: flex;
        gap: 8px;
        align-items: flex-start;
      }}
      .emoji {{
        flex: 0 0 auto;
        margin-top: 1px;
      }}
      .titleText {{
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        text-overflow: ellipsis;
      }}
      .cardMeta {{
        flex: 0 0 auto;
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        gap: 2px;
        font-size: 12px;
        color: var(--muted);
        white-space: nowrap;
      }}
      .pct {{
        color: var(--text);
        font-weight: 800;
        font-size: 13px;
      }}

      .progressRow {{
        margin-top: 10px;
      }}
      .progressTrack {{
        height: 10px;
        border-radius: 999px;
        background: rgba(232, 238, 252, 0.10);
        overflow: hidden;
        border: 1px solid rgba(232, 238, 252, 0.06);
      }}
      .progressFill {{
        height: 100%;
        background: linear-gradient(90deg, var(--accent), var(--accent2));
        border-radius: 999px;
      }}

      .daysRow {{
        margin-top: 10px;
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        gap: 6px;
        align-items: end;
      }}
      .dayCol {{
        position: relative;
        height: 46px;
        border-radius: 10px;
        background: rgba(232, 238, 252, 0.05);
        border: 1px solid rgba(232, 238, 252, 0.06);
        overflow: hidden;
        display: flex;
        flex-direction: column;
        justify-content: flex-end;
      }}
      .dayBar {{
        width: 100%;
        background: rgba(91, 163, 245, 0.70);
        border-top: 1px solid rgba(232, 238, 252, 0.20);
      }}
      .dayLbl {{
        position: absolute;
        bottom: 3px;
        left: 6px;
        font-size: 10px;
        color: rgba(232, 238, 252, 0.72);
        font-weight: 700;
      }}

      .empty {{
        margin-top: 18px;
        padding: 40px 18px;
        border-radius: 16px;
        border: 1px solid var(--border);
        background: rgba(15, 23, 48, 0.7);
        text-align: center;
      }}
      .emptyTitle {{
        font-size: 16px;
        font-weight: 800;
        color: var(--text);
      }}

      /* Print safety */
      @media print {{
        body {{ background: #ffffff; color: #000000; }}
      }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <header class="header">
        <div>
          <div class="hTitle" dir="auto">Weekly Report</div>
          <div class="hSub" dir="ltr">{_escape(week_range)}</div>
        </div>
        <div class="hRight">
          <div dir="ltr">Totals</div>
          <div class="hNums" dir="ltr">{total_spent:.1f}/{total_promised:.1f} h</div>
        </div>
      </header>

      <main class="grid">
        {empty_state if empty_state else ''.join(cards)}
      </main>
    </div>
  </body>
</html>
"""
    return html_doc


def render_weekly_report_card_png(
    *,
    summary: Dict[str, Any],
    output_path: str,
    week_start: datetime,
    week_end: datetime,
    width: int = 1200,
) -> str:
    """
    Render the weekly report card HTML to a PNG at output_path.
    """
    # Local import so the bot can still run without Playwright installed (text-only fallback).
    from playwright.sync_api import sync_playwright  # type: ignore

    html_doc = build_weekly_report_card_html(
        summary,
        week_start=week_start,
        week_end=week_end,
        width=width,
    )

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        try:
            page = browser.new_page(
                viewport={"width": int(width), "height": 900},
                device_scale_factor=2,
            )
            page.set_content(html_doc, wait_until="load")
            # Ensure web fonts are ready before screenshot (important for RTL shaping and consistent layout).
            page.evaluate("() => document.fonts && document.fonts.ready ? document.fonts.ready.then(() => true) : true")
            page.screenshot(path=output_path, full_page=True, type="png")
        finally:
            browser.close()

    return output_path

