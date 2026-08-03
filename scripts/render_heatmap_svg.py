#!/usr/bin/env python3
"""
render_heatmap_svg.py — draw data/contributions.json as an animated SVG heatmap.

Classic 53-week x 7-day calendar of rounded boxes, revealed once with a
diagonal cascade — each box slides in from the upper-left along the wave —
that freezes when it finishes (no looping glow).
Includes a Less->More legend and a stats footer.

Usage:
    python scripts/render_heatmap_svg.py
    python scripts/render_heatmap_svg.py --bg "#0d1117" --out dark.svg
"""

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path

IN_PATH = Path("data/contributions.json")
OUT_PATH = Path("contrib-heatmap.svg")

# none -> brightest (level 5 is a neon top end)
PALETTE = ["#161b22", "#3d1229", "#701a45", "#a92964", "#db61a2", "#ff9ecf"]

CELL = 12          # box edge length
GAP = 3            # space between boxes
RADIUS = 2.5       # corner rounding
STEP = CELL + GAP

PAD_L = 34         # room for Mon/Wed/Fri labels
PAD_T = 24         # room for month labels
PAD_R = 16
FOOTER_H = 58      # legend + stats line

TEXT = "#8b949e"       # readable on both light and dark README themes
TEXT_BRIGHT = "#c9d1d9"
ACCENT = "#db61a2"

# Reveal timing
DIAG_STEP = 0.022      # seconds added per diagonal band
FALL_DUR = 0.42        # how long one box takes to settle

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WEEKDAY_LABELS = {1: "Mon", 3: "Wed", 5: "Fri"}


def parse_iso(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def grid_position(day: date, origin: date) -> tuple[int, int]:
    """Return (column, row) where row 0 is Sunday, matching GitHub's layout."""
    offset = (day - origin).days
    return offset // 7, offset % 7


def sunday_on_or_before(day: date) -> date:
    # Python: Monday=0 ... Sunday=6. Shift so Sunday=0.
    return day - timedelta(days=(day.weekday() + 1) % 7)


def month_label_columns(days: list[dict], origin: date) -> list[tuple[int, str]]:
    """One label per month, placed at the column of its first appearance."""
    labels, seen = [], set()
    for entry in days:
        day = parse_iso(entry["date"])
        key = (day.year, day.month)
        if key in seen:
            continue
        seen.add(key)
        col, _ = grid_position(day, origin)
        # Skip a label that would collide with the previous one.
        if labels and col - labels[-1][0] < 3:
            continue
        labels.append((col, MONTHS[day.month - 1]))
    return labels


def esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def pretty_date(iso: str) -> str:
    day = parse_iso(iso)
    return f"{MONTHS[day.month - 1]} {day.day}, {day.year}"


def build_svg(payload: dict, bg: str) -> str:
    days = payload["days"]
    stats = payload["stats"]

    origin = sunday_on_or_before(parse_iso(days[0]["date"]))
    last_col, _ = grid_position(parse_iso(days[-1]["date"]), origin)
    n_cols = last_col + 1

    grid_w = n_cols * STEP - GAP
    grid_h = 7 * STEP - GAP
    width = PAD_L + grid_w + PAD_R
    height = PAD_T + grid_h + FOOTER_H

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{esc(payload["username"])} GitHub contribution heatmap">'
    )

    # --- styles: one cascade animation, plays once, then holds ---------------
    parts.append(f"""<style>
  .cell {{
    opacity: 0;
    animation: drop {FALL_DUR}s cubic-bezier(.22,.9,.3,1) forwards;
  }}
  @keyframes drop {{
    from {{ opacity: 0; transform: translate(-13px, -13px) scale(.72); }}
    to   {{ opacity: 1; transform: translate(0, 0) scale(1); }}
  }}
  text {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 10px;
    fill: {TEXT};
  }}
  .stat {{ font-size: 11px; }}
  .stat-num {{ fill: {TEXT_BRIGHT}; font-weight: 600; }}
  @media (prefers-reduced-motion: reduce) {{
    .cell {{ animation: none; opacity: 1; }}
  }}
</style>""")

    if bg.lower() not in ("none", "transparent", "00000000", "#00000000"):
        parts.append(f'<rect width="{width}" height="{height}" fill="{bg}" rx="6"/>')

    # --- month labels --------------------------------------------------------
    for col, label in month_label_columns(days, origin):
        x = PAD_L + col * STEP
        parts.append(f'<text x="{x}" y="{PAD_T - 8}">{label}</text>')

    # --- weekday labels ------------------------------------------------------
    for row, label in WEEKDAY_LABELS.items():
        y = PAD_T + row * STEP + CELL - 2
        parts.append(f'<text x="0" y="{y}">{label}</text>')

    # --- the grid ------------------------------------------------------------
    parts.append("<g>")
    for entry in days:
        day = parse_iso(entry["date"])
        col, row = grid_position(day, origin)
        x = PAD_L + col * STEP
        y = PAD_T + row * STEP
        fill = PALETTE[entry["level"]]
        delay = round((col + row) * DIAG_STEP, 3)
        count = entry["count"]
        noun = "contribution" if count == 1 else "contributions"
        title = f"{count} {noun} on {pretty_date(entry['date'])}"
        parts.append(
            f'<rect class="cell" x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
            f'rx="{RADIUS}" fill="{fill}" style="animation-delay:{delay}s;'
            f'transform-origin:{x + CELL / 2}px {y + CELL / 2}px">'
            f"<title>{esc(title)}</title></rect>"
        )
    parts.append("</g>")

    # --- legend (right aligned, under the grid) ------------------------------
    legend_y = PAD_T + grid_h + 16
    swatch = 11
    legend_w = 30 + len(PALETTE) * (swatch + 3) + 32
    legend_x = PAD_L + grid_w - legend_w
    total_delay = round((n_cols + 7) * DIAG_STEP + FALL_DUR, 3)

    parts.append(
        f'<text x="{legend_x}" y="{legend_y + swatch - 2}" text-anchor="start">Less</text>'
    )
    for i, color in enumerate(PALETTE):
        x = legend_x + 30 + i * (swatch + 3)
        parts.append(
            f'<rect class="cell" x="{x}" y="{legend_y}" width="{swatch}" height="{swatch}" '
            f'rx="2" fill="{color}" style="animation-delay:{round(total_delay + i * 0.04, 3)}s;'
            f'transform-origin:{x + swatch / 2}px {legend_y + swatch / 2}px"/>'
        )
    more_x = legend_x + 30 + len(PALETTE) * (swatch + 3) + 4
    parts.append(f'<text x="{more_x}" y="{legend_y + swatch - 2}">More</text>')

    # --- stats footer --------------------------------------------------------
    footer_y = legend_y + swatch + 20
    current = stats["current_streak"]["length"]
    longest = stats["longest_streak"]["length"]
    busiest = stats["busiest_day"]

    segments = [
        (f'{stats["total"]:,}', " contributions in the last year"),
        (f"{current}", f' day{"" if current == 1 else "s"} current streak'),
        (f"{longest}", f' day{"" if longest == 1 else "s"} longest streak'),
        (f'{busiest["count"]}', f' on {pretty_date(busiest["date"])} (best day)'),
    ]

    parts.append(f'<text class="stat" x="{PAD_L}" y="{footer_y}">')
    for i, (number, label) in enumerate(segments):
        if i:
            parts.append(f'<tspan fill="{ACCENT}" dx="6">·</tspan>')
        parts.append(f'<tspan class="stat-num" dx="{6 if i else 0}">{number}</tspan>')
        parts.append(f"<tspan>{esc(label)}</tspan>")
    parts.append("</text>")

    parts.append("</svg>")
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=IN_PATH)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument(
        "--bg",
        default="none",
        help='Background fill. "none" for transparent (default), or a hex like "#0d1117".',
    )
    args = parser.parse_args()

    payload = json.loads(args.data.read_text(encoding="utf-8"))
    svg = build_svg(payload, args.bg)
    args.out.write_text(svg, encoding="utf-8")

    print(f"wrote {args.out}  ({len(svg):,} bytes, {len(payload['days'])} days)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
