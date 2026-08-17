"""
Render a club's rolling 7-day leaderboard (from
`services.club_leaderboard_service.compute_club_leaderboard`) as a PNG,
sent by the bot into the club's Telegram group.

Visual design ported 1:1 from the app's own leaderboard UI
(`webapp_frontend/src/components/clubs/ClubBadge.tsx` +
`webapp_frontend/src/styles/sheets.css`, `.club-leaderboard-row` /
`.club-activity-cell` / `.club-leaderboard-progress`) — same colors, same
rank pill / streak / 7-day activity strip / progress bar layout — rather
than the older dark heatmap style in `visualisation/streak_heatmap.py`.
"""
from __future__ import annotations

import html
import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional

DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Design tokens copied from webapp_frontend/src/styles/design-system.css
_BG = "#0B0F1A"          # --ink-900 / --bg
_SURFACE = "#141C34"     # --ink-800 / --surface
_FG = "#E6EAF5"          # --ink-100 / --fg
_FG_MUTED = "#98A3C3"    # --ink-300 / --fg-muted
_BORDER = "rgba(230, 234, 245, 0.08)"
_ACCENT = "#22D3EE"      # --cyan-500 / --accent
_ACCENT_SOFT = "rgba(34, 211, 238, 0.12)"
_GOOD = "#34D399"        # --good-500

# Same thresholds as ClubBadge.tsx's getActivityLevel()
_LEVEL_COLORS = {
    2: ("rgba(20, 184, 166, 0.42)", "rgba(45, 212, 191, 0.28)"),
    3: ("rgba(20, 184, 166, 0.7)", "rgba(45, 212, 191, 0.42)"),
    4: (_GOOD, "rgba(45, 212, 191, 0.72)"),
}
_LEVEL_DEFAULT = ("rgba(230, 234, 245, 0.08)", "rgba(230, 234, 245, 0.1)")


def _escape(s: Any) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def _activity_level(score_percent: float) -> int:
    if score_percent >= 90:
        return 4
    if score_percent >= 60:
        return 3
    if score_percent > 0:
        return 2
    return 0


def _avatar_color(user_id: str) -> str:
    """Same hash -> HSL scheme as webapp_frontend/src/utils/publicUserDisplay.ts getAvatarColor()."""
    h = 0
    for ch in user_id:
        h = ord(ch) + ((h << 5) - h)
        h &= 0xFFFFFFFF
    if h >= 0x80000000:
        h -= 0x100000000
    hue = abs(h) % 360
    return f"hsl({hue}, 65%, 50%)"


def _display_name(member: dict) -> str:
    return str(member.get("first_name") or member.get("username") or "Member")


def _format_breakdown(member: dict) -> str:
    breakdown = member.get("breakdown") or []
    if not breakdown:
        return "No activity yet"
    parts = []
    for item in breakdown[:3]:
        metric = item.get("metric_type") or "hours"
        achieved = float(item.get("achieved_value") or 0.0)
        target = float(item.get("target_value") or 0.0)
        if metric == "hours":
            fmt = lambda v: f"{v:.0f}h" if v % 1 == 0 else f"{v:.1f}h"
        else:
            fmt = lambda v: str(round(v))
        parts.append(f"{item.get('promise_text', 'Club promise')}: {fmt(achieved)}/{fmt(target)}")
    return " | ".join(parts)


def build_club_leaderboard_html(
    club_name: str,
    leaderboard: Dict[str, Any],
    *,
    avatar_data_uris: Optional[Dict[str, str]] = None,
    width: int = 760,
) -> str:
    window_start: date = leaderboard["window_start"]
    window_end: date = leaderboard["window_end"]
    members: List[Dict[str, Any]] = leaderboard.get("members") or []
    average_score = float(leaderboard.get("average_score_percent") or 0.0)
    member_count = int(leaderboard.get("member_count") or len(members))
    window_dates = [d.date() if isinstance(d, datetime) else d for d in _seven_days(window_end)]

    day_label_cells = "".join(
        f'<div class="dayCell" dir="ltr">{DAY_LABELS[d.weekday()]}</div>' for d in window_dates
    )

    avatar_data_uris = avatar_data_uris or {}
    rows_html: List[str] = []
    for member in members:
        user_id = str(member["user_id"])
        name = _display_name(member)
        avatar_data_uri = avatar_data_uris.get(user_id)
        if avatar_data_uri:
            avatar_html = f'<img class="avatar" src="{_escape(avatar_data_uri)}" alt="" />'
        else:
            initial = _escape((name or "U")[0].upper())
            color = _avatar_color(user_id)
            avatar_html = f'<div class="avatar avatarFallback" style="background:{color}">{initial}</div>'

        daily_by_date = {item["date"]: item for item in (member.get("daily_activity") or [])}
        strip_cells = []
        for d in window_dates:
            item = daily_by_date.get(d.isoformat(), {})
            score = float(item.get("score_percent") or 0.0)
            level = _activity_level(score)
            base, border = _LEVEL_COLORS.get(level, _LEVEL_DEFAULT)
            checkins = int(item.get("checkins") or 0)
            duration = float(item.get("duration_hours") or 0.0)
            title = f"{d.strftime('%b %d')}: " + (
                ", ".join(
                    p for p in [
                        f"{checkins} check-in{'s' if checkins != 1 else ''}" if checkins else "",
                        f"{duration:.1f}h logged" if duration > 0 else "",
                    ] if p
                ) or "no club activity"
            )
            strip_cells.append(
                f'<span class="cell" style="background:{base};border-color:{border}" title="{_escape(title)}"></span>'
            )

        score_percent = float(member.get("score_percent") or 0.0)
        rows_html.append(f"""
        <div class="row">
          <span class="rank">{member.get("rank", "")}</span>
          {avatar_html}
          <div class="person">
            <strong dir="auto">{_escape(name)}</strong>
            <span dir="auto">{member.get("freeze_streak", 0)} day streak | {_escape(_format_breakdown(member))}</span>
          </div>
          <div class="strip">{''.join(strip_cells)}</div>
          <div class="progress">
            <span dir="ltr">{score_percent:g}%</span>
            <div class="track"><div class="fill" style="width:{max(0, min(100, score_percent))}%"></div></div>
          </div>
        </div>
        """.strip())

    empty_state = ""
    if not rows_html:
        empty_state = '<div class="empty" dir="auto">No leaderboard activity yet.</div>'

    date_range = f"{window_start.strftime('%d %b')} - {window_end.strftime('%d %b')}"

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <style>
      html, body {{
        margin: 0;
        padding: 0;
        background: {_BG};
        color: {_FG};
        -webkit-font-smoothing: antialiased;
      }}
      body {{
        width: {int(width)}px;
        font-family: "Noto Sans", "Noto Sans Arabic", system-ui, -apple-system, "Segoe UI", Arial, sans-serif;
      }}
      .wrap {{ padding: 24px; }}
      .header {{
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 16px;
        padding: 16px 18px;
        border: 1px solid {_BORDER};
        border-radius: 16px;
        background: linear-gradient(135deg, {_ACCENT_SOFT}, rgba(52,211,153,0.08));
        margin-bottom: 16px;
      }}
      .hTitle {{ font-size: 20px; font-weight: 800; }}
      .hSub {{ font-size: 12px; color: {_FG_MUTED}; margin-top: 4px; }}
      .hStats {{ text-align: right; font-size: 12px; color: {_FG_MUTED}; font-weight: 700; }}
      .hStats .avg {{ font-size: 22px; font-weight: 900; color: {_GOOD}; display: block; }}
      .dayLabels {{
        display: grid;
        grid-template-columns: 30px 36px minmax(0, 1fr) repeat(7, 12px) 88px;
        gap: 10px;
        padding: 0 10px;
        margin-bottom: 6px;
      }}
      .dayLabels .dayCell {{
        width: 12px;
        font-size: 9px;
        color: {_FG_MUTED};
        font-weight: 700;
        text-align: center;
      }}
      .rows {{ display: grid; gap: 8px; }}
      .row {{
        display: grid;
        grid-template-columns: 30px 36px minmax(0, 1fr) repeat(1, auto) 88px;
        align-items: center;
        gap: 10px;
        min-height: 56px;
        padding: 8px 10px;
        border: 1px solid {_BORDER};
        border-radius: 10px;
        background: {_SURFACE};
      }}
      .rank {{
        width: 24px;
        height: 24px;
        display: grid;
        place-items: center;
        border-radius: 999px;
        background: {_ACCENT_SOFT};
        color: {_ACCENT};
        font-size: 12px;
        font-weight: 900;
      }}
      .avatar {{
        width: 32px;
        height: 32px;
        border-radius: 999px;
        object-fit: cover;
      }}
      .avatarFallback {{
        display: grid;
        place-items: center;
        color: #0B0F1A;
        font-size: 13px;
        font-weight: 800;
      }}
      .person {{ min-width: 0; display: grid; gap: 2px; }}
      .person strong {{
        font-size: 13px;
        color: {_FG};
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }}
      .person span {{
        font-size: 11px;
        font-weight: 700;
        color: {_FG_MUTED};
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }}
      .strip {{ display: flex; gap: 4px; }}
      .strip .cell {{
        width: 12px;
        height: 12px;
        border-radius: 3px;
        border: 1px solid;
        display: inline-block;
      }}
      .progress {{ display: grid; gap: 5px; text-align: right; }}
      .progress span {{ font-size: 12px; font-weight: 800; color: {_FG_MUTED}; }}
      .track {{ height: 4px; border-radius: 999px; overflow: hidden; background: rgba(230,234,245,0.08); }}
      .fill {{ height: 100%; border-radius: inherit; background: {_GOOD}; }}
      .empty {{
        padding: 32px;
        text-align: center;
        border-radius: 16px;
        border: 1px solid {_BORDER};
        color: {_FG_MUTED};
        font-size: 14px;
      }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <header class="header">
        <div>
          <div class="hTitle" dir="auto">🏆 {_escape(club_name)}</div>
          <div class="hSub" dir="ltr">{_escape(date_range)} · {member_count} members</div>
        </div>
        <div class="hStats">
          <span class="avg" dir="ltr">{average_score:g}%</span>
          avg progress
        </div>
      </header>
      {f'<div class="dayLabels"><div></div><div></div><div></div>{day_label_cells}<div></div></div>' if rows_html else ''}
      <div class="rows">
        {empty_state if empty_state else ''.join(rows_html)}
      </div>
    </div>
  </body>
</html>
"""


def _seven_days(window_end: date) -> List[date]:
    from datetime import timedelta
    return [window_end - timedelta(days=offset) for offset in range(6, -1, -1)]


async def render_club_leaderboard_png(
    *,
    club_name: str,
    leaderboard: Dict[str, Any],
    output_path: str,
    avatar_data_uris: Optional[Dict[str, str]] = None,
    width: int = 760,
) -> str:
    """Render the club leaderboard HTML to a PNG at output_path (headless Chromium)."""
    from playwright.async_api import async_playwright  # type: ignore  # pylint: disable=import-error

    html_doc = build_club_leaderboard_html(
        club_name, leaderboard, avatar_data_uris=avatar_data_uris, width=width
    )

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        try:
            page = await browser.new_page(
                viewport={"width": int(width), "height": 800},
                device_scale_factor=2,
            )
            await page.set_content(html_doc, wait_until="load")
            await page.evaluate(
                "() => document.fonts && document.fonts.ready ? document.fonts.ready.then(() => true) : true"
            )
            await page.screenshot(path=output_path, full_page=True, type="png")
        finally:
            await browser.close()

    return output_path
