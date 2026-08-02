#!/usr/bin/env python3
"""
render_stats_svg.py — draw data/contributions.json as a stats card SVG.

Same data source as the heatmap, so every number includes private and
private-org contributions (GitHub's calendar shows them once "Include
private contributions on my profile" is enabled). No tokens, no API.

ponytail: no stars/PRs/issues rows — those need the API and can't include
private-org activity anyway; add an API step if public-only rows are wanted.

Usage:
    python scripts/render_stats_svg.py
    python scripts/render_stats_svg.py --out stats-card.svg
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

IN_PATH = Path("data/contributions.json")
OUT_PATH = Path("stats-card.svg")

WIDTH, HEIGHT = 460, 165

TEXT = "#8b949e"
TEXT_BRIGHT = "#c9d1d9"
ACCENT = "#db61a2"
BULLETS = ["#ff9ecf", "#db61a2", "#a92964", "#701a45", "#a92964"]  # heatmap palette

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def pretty_date(iso: str) -> str:
    day = datetime.strptime(iso, "%Y-%m-%d").date()
    return f"{MONTHS[day.month - 1]} {day.day}"


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_svg(payload: dict) -> str:
    stats = payload["stats"]
    total = stats["total"]
    active = stats["active_days"]
    total_days = max(stats["total_days"], 1)
    pct = round(100 * active / total_days)
    current = stats["current_streak"]["length"]
    longest = stats["longest_streak"]["length"]
    busiest = stats["busiest_day"]

    rows = [
        ("Total Contributions", f"{total:,}"),
        ("Active Days", f"{active} / {total_days}"),
        ("Current Streak", f"{current} day{'' if current == 1 else 's'}"),
        ("Longest Streak", f"{longest} day{'' if longest == 1 else 's'}"),
        ("Busiest Day", f"{busiest['count']} on {pretty_date(busiest['date'])}"),
    ]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
        f'aria-label="{esc(payload["username"])} GitHub stats: {total:,} contributions in the last year">'
    ]

    parts.append(f"""<style>
  text {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 12px;
    fill: {TEXT};
  }}
  .title {{ font-size: 15px; font-weight: 600; fill: {ACCENT}; }}
  .num {{ fill: {TEXT_BRIGHT}; font-weight: 600; }}
  .big {{ font-size: 22px; font-weight: 700; fill: {TEXT_BRIGHT}; }}
  .row, .ring, .center {{ opacity: 0; animation: fade .5s ease-out forwards; }}
  @keyframes fade {{ to {{ opacity: 1; }} }}
  .arc {{
    fill: none; stroke: {ACCENT}; stroke-width: 7; stroke-linecap: round;
    stroke-dasharray: {pct} {100 - pct};
    animation: grow 1s ease-out forwards;
  }}
  @keyframes grow {{ from {{ stroke-dasharray: 0 100; }} }}
  @media (prefers-reduced-motion: reduce) {{
    .row, .ring, .center {{ animation: none; opacity: 1; }}
    .arc {{ animation: none; }}
  }}
</style>""")

    parts.append(
        f'<text class="title" x="20" y="28">GitHub Stats '
        f'<tspan style="font-weight:400;font-size:11px" fill="{TEXT}">'
        f'· last 365 days · incl. private</tspan></text>'
    )

    y = 56
    for i, (label, value) in enumerate(rows):
        delay = round(0.15 + i * 0.1, 2)
        parts.append(f'<g class="row" style="animation-delay:{delay}s">')
        parts.append(
            f'<rect x="20" y="{y - 9}" width="9" height="9" rx="2" fill="{BULLETS[i]}"/>'
        )
        parts.append(f'<text x="38" y="{y}">{esc(label)}</text>')
        parts.append(f'<text class="num" x="310" y="{y}" text-anchor="end">{esc(value)}</text>')
        parts.append("</g>")
        y += 24

    # Activity ring: share of days with at least one contribution.
    cx, cy, r = 390, 88, 44
    parts.append(f'<g class="ring" style="animation-delay:.3s">')
    parts.append(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{TEXT}" '
        f'stroke-opacity="0.18" stroke-width="7"/>'
    )
    parts.append(
        f'<circle class="arc" cx="{cx}" cy="{cy}" r="{r}" pathLength="100" '
        f'transform="rotate(-90 {cx} {cy})"/>'
    )
    parts.append("</g>")
    parts.append(f'<g class="center" style="animation-delay:.6s">')
    parts.append(f'<text class="big" x="{cx}" y="{cy + 2}" text-anchor="middle">{pct}%</text>')
    parts.append(f'<text x="{cx}" y="{cy + 20}" text-anchor="middle">days active</text>')
    parts.append("</g>")

    parts.append("</svg>")
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=IN_PATH)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    payload = json.loads(args.data.read_text(encoding="utf-8"))
    svg = build_svg(payload)
    args.out.write_text(svg, encoding="utf-8")
    print(f"wrote {args.out}  ({len(svg):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
