from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

import html

from utils.time_utils import get_week_range


DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _escape(s: Any) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def _get_activity_color(hours: float) -> tuple[str, str]:
    """Get color based on hours spent (gradient from dark to bright).
    Returns (base_color, lighter_variant) tuple for gradient.
    """
    if hours <= 0:
        return ("#1e293b", "#1e293b")  # Dark slate (inactive)
    elif hours < 1.0:
        return ("#3b82f6", "#60a5fa")  # Blue (low activity)
    elif hours < 2.0:
        return ("#60a5fa", "#93c5fd")  # Lighter blue (medium-low)
    elif hours < 4.0:
        return ("#38bdf8", "#7dd3fc")  # Light blue (medium)
    else:
        return ("#22c55e", "#4ade80")  # Green (high activity)


def _get_week_days(week_start: date) -> List[date]:
    """Get all 7 days of a week starting from Monday."""
    return [week_start + timedelta(days=i) for i in range(7)]


def build_streak_heatmap_html(
    heatmap_data: Dict[str, Any],
    *,
    ref_time: datetime,
    width: int = 1400,
) -> str:
    """
    Build an HTML streak heatmap visualization (GitHub-style).
    
    RTL handling strategy:
    - Use browser shaping (Chromium) and per-field `dir="auto"` for promise text.
    - Use `unicode-bidi: plaintext` so mixed RTL/LTR promise titles behave well.
    - Keep numeric fragments and dates in `dir="ltr"` spans.
    """
    # Calculate the Monday of 4 weeks ago
    week_start, _ = get_week_range(ref_time)
    four_weeks_monday = (week_start - timedelta(days=21)).date()
    
    # Get all 4 weeks
    weeks = []
    for week_offset in range(4):
        week_monday = four_weeks_monday + timedelta(days=week_offset * 7)
        weeks.append(_get_week_days(week_monday))
    
    # Build promise cards
    promise_cards: List[str] = []
    for pid, data in sorted((heatmap_data or {}).items(), key=lambda kv: str(kv[0])):
        d = data or {}
        title = str(d.get("text", "") or "").replace('_', ' ')
        days_dict = d.get("days", {})
        hours_dict = d.get("hours_by_date", {})
        
        # Build heatmap grid (4 weeks x 7 days)
        heatmap_cells = []
        for week in weeks:
            week_cells = []
            for day_date in week:
                has_activity = days_dict.get(day_date, False)
                hours = hours_dict.get(day_date, 0.0)
                base_color, lighter_color = _get_activity_color(hours)
                
                # Format date for tooltip
                date_str = day_date.strftime("%b %d")
                tooltip = f"{date_str}: {hours:.1f}h" if has_activity else f"{date_str}: No activity"
                
                week_cells.append(
                    f'<div class="heatmapCell" style="background: linear-gradient(135deg, {base_color}, {lighter_color})" title="{_escape(tooltip)}"></div>'
                )
            heatmap_cells.append(f'<div class="heatmapWeek">{"".join(week_cells)}</div>')
        
        # Build week labels (Week 1, Week 2, etc.)
        week_labels = []
        for i in range(4):
            week_labels.append(f'<div class="weekLabel" dir="ltr">W{i+1}</div>')
        
        promise_cards.append(
            f"""
            <section class="promiseCard">
              <div class="promiseTitle" dir="auto">{_escape(title)}</div>
              <div class="promiseId" dir="ltr">#{_escape(pid)}</div>
              <div class="heatmapContainer">
                <div class="weekLabelsRow">
                  {''.join(week_labels)}
                </div>
                <div class="heatmapGrid">
                  {''.join(heatmap_cells)}
                </div>
                <div class="dayLabelsRow">
                  {''.join(f'<div class="dayLabel" dir="ltr">{label}</div>' for label in DAY_LABELS)}
                </div>
              </div>
            </section>
            """.strip()
        )
    
    # Empty state
    empty_state = ""
    if not promise_cards:
        empty_state = """
        <section class="empty">
          <div class="emptyTitle" dir="auto">No promises with activity in the last 4 weeks</div>
        </section>
        """.strip()
    
    # Format date range for header
    end_date = (week_start - timedelta(days=1)).date()  # Sunday of current week
    start_date = four_weeks_monday
    date_range = f"{start_date.strftime('%d %b')} - {end_date.strftime('%d %b')}"
    
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
      .promiseTitle, .emptyTitle {{
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
        margin-bottom: 20px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
      }}
      .hTitle {{
        font-size: 24px;
        font-weight: 800;
        letter-spacing: 0.2px;
        background: linear-gradient(135deg, var(--accent), var(--accent2));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
      }}
      .hSub {{
        font-size: 13px;
        color: var(--muted);
        margin-top: 4px;
      }}

      .promiseCard {{
        border: 1px solid var(--border);
        border-radius: 16px;
        background: linear-gradient(180deg, rgba(15,26,56,0.98), rgba(15,23,48,0.98));
        padding: 20px 20px 18px 20px;
        margin-bottom: 18px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
      }}
      .promiseTitle {{
        font-size: 16px;
        font-weight: 800;
        line-height: 1.3;
        margin-bottom: 8px;
        color: var(--text);
        text-align: start;
      }}
      .promiseId {{
        font-size: 12px;
        color: var(--muted);
        margin-bottom: 16px;
      }}

      .heatmapContainer {{
        display: flex;
        flex-direction: column;
        gap: 10px;
      }}
      .weekLabelsRow {{
        display: flex;
        gap: 6px;
        margin-left: 0;
        padding-left: 0;
        justify-content: flex-start;
        margin-bottom: 2px;
      }}
      .weekLabel {{
        width: 34px;
        font-size: 10px;
        color: var(--muted);
        font-weight: 700;
        text-align: center;
      }}
      .heatmapGrid {{
        display: flex;
        gap: 8px;
        align-items: flex-start;
      }}
      .heatmapWeek {{
        display: flex;
        flex-direction: column;
        gap: 5px;
      }}
      .heatmapCell {{
        width: 34px;
        height: 34px;
        border-radius: 7px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        transition: transform 0.1s ease;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
      }}
      .dayLabelsRow {{
        display: flex;
        gap: 6px;
        margin-left: 0;
        padding-left: 0;
        justify-content: flex-start;
        margin-top: 2px;
      }}
      .dayLabel {{
        width: 34px;
        font-size: 10px;
        color: var(--muted);
        font-weight: 700;
        text-align: center;
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
          <div class="hTitle" dir="auto">Streak Heatmap</div>
          <div class="hSub" dir="ltr">{_escape(date_range)}</div>
        </div>
      </header>

      <main>
        {empty_state if empty_state else ''.join(promise_cards)}
      </main>
    </div>
  </body>
</html>
"""
    return html_doc


async def render_streak_heatmap_png(
    *,
    heatmap_data: Dict[str, Any],
    output_path: str,
    ref_time: datetime,
    width: int = 1400,
) -> str:
    """
    Render the streak heatmap HTML to a PNG at output_path.
    Uses async Playwright API to work within asyncio event loop.
    """
    # Local import so the bot can still run without Playwright installed (text-only fallback).
    from playwright.async_api import async_playwright  # type: ignore  # pylint: disable=import-error

    html_doc = build_streak_heatmap_html(
        heatmap_data,
        ref_time=ref_time,
        width=width,
    )

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        try:
            page = await browser.new_page(
                viewport={"width": int(width), "height": 1200},
                device_scale_factor=2,
            )
            await page.set_content(html_doc, wait_until="load")
            # Ensure web fonts are ready before screenshot (important for RTL shaping and consistent layout).
            await page.evaluate("() => document.fonts && document.fonts.ready ? document.fonts.ready.then(() => true) : true")
            await page.screenshot(path=output_path, full_page=True, type="png")
        finally:
            await browser.close()

    return output_path

