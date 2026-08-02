#!/usr/bin/env python3
"""
fetch_contributions.py — pull a GitHub contribution calendar without a token.

GitHub serves the calendar as a public HTML fragment at
    https://github.com/users/<username>/contributions
which is the same markup the profile page itself renders. That means it
already reflects whatever your profile shows -- including private and
private-org contributions, if "Include private contributions on my
profile" is enabled in your settings.

Writes data/contributions.json with raw days plus derived stats.

Usage:
    python scripts/fetch_contributions.py
    python scripts/fetch_contributions.py --username someoneelse
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

DEFAULT_USERNAME = "Malakbadawyy"
CONTRIB_URL = "https://github.com/users/{username}/contributions"
OUT_PATH = Path("data/contributions.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; contrib-heatmap/1.0)",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "text/html",
}

# Tooltips read like "12 contributions on March 3rd." or
# "No contributions on August 3rd."
COUNT_RE = re.compile(r"^([\d,]+)\s+contribution", re.I)


def fetch_html(username: str, timeout: int = 30) -> str:
    url = CONTRIB_URL.format(username=username)
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    if "ContributionCalendar-day" not in resp.text:
        raise RuntimeError(
            f"No calendar found for '{username}'. Check the username is correct "
            "and the profile is public."
        )
    return resp.text


def parse_days(html: str) -> list[dict]:
    """Return [{date, count, gh_level}, ...] sorted by date ascending."""
    soup = BeautifulSoup(html, "html.parser")

    # Counts live in sibling <tool-tip for="contribution-day-component-R-C">
    counts_by_cell_id: dict[str, int] = {}
    for tip in soup.find_all("tool-tip"):
        target = tip.get("for")
        if not target:
            continue
        text = tip.get_text(strip=True)
        match = COUNT_RE.match(text)
        counts_by_cell_id[target] = (
            int(match.group(1).replace(",", "")) if match else 0
        )

    days: list[dict] = []
    for cell in soup.select("td.ContributionCalendar-day"):
        day_iso = cell.get("data-date")
        if not day_iso:
            continue
        cell_id = cell.get("id", "")
        days.append(
            {
                "date": day_iso,
                "count": counts_by_cell_id.get(cell_id, 0),
                "gh_level": int(cell.get("data-level") or 0),
            }
        )

    if not days:
        raise RuntimeError("Parsed zero day cells -- GitHub markup may have changed.")

    days.sort(key=lambda d: d["date"])
    return days


def total_from_header(html: str) -> int | None:
    """GitHub prints the yearly total in the <h2> above the grid."""
    soup = BeautifulSoup(html, "html.parser")
    header = soup.find(id="js-contribution-activity-description")
    if not header:
        return None
    match = re.search(r"([\d,]+)\s+contribution", header.get_text(" ", strip=True), re.I)
    return int(match.group(1).replace(",", "")) if match else None


def compute_streaks(days: list[dict]) -> tuple[dict, dict]:
    """Current streak (ending today/yesterday) and longest streak overall."""
    longest = {"length": 0, "start": None, "end": None}
    run_len, run_start = 0, None

    for day in days:
        if day["count"] > 0:
            run_len += 1
            run_start = run_start or day["date"]
            if run_len > longest["length"]:
                longest = {"length": run_len, "start": run_start, "end": day["date"]}
        else:
            run_len, run_start = 0, None

    # Current streak: walk backwards, tolerating an empty "today" so the
    # streak doesn't look broken before you've committed in the morning.
    today = date.today()
    by_date = {d["date"]: d["count"] for d in days}
    cursor = today
    if by_date.get(cursor.isoformat(), 0) == 0:
        cursor -= timedelta(days=1)

    current_len, current_end = 0, None
    while by_date.get(cursor.isoformat(), 0) > 0:
        current_len += 1
        current_end = current_end or cursor.isoformat()
        cursor -= timedelta(days=1)

    current = {
        "length": current_len,
        "start": (cursor + timedelta(days=1)).isoformat() if current_len else None,
        "end": current_end,
    }
    return current, longest


def compute_levels(days: list[dict]) -> None:
    """
    Assign a 0-5 level in place. GitHub only ships 0-4; we add a sixth tier so
    the brightest palette entry is reserved for genuine outlier days.
    Quantile-based so it adapts to your actual commit volume.
    """
    active = sorted(d["count"] for d in days if d["count"] > 0)
    if not active:
        for day in days:
            day["level"] = 0
        return

    def quantile(fraction: float) -> int:
        idx = min(int(len(active) * fraction), len(active) - 1)
        return active[idx]

    cuts = [quantile(f) for f in (0.25, 0.50, 0.75, 0.93)]

    for day in days:
        count = day["count"]
        if count <= 0:
            day["level"] = 0
        elif count <= cuts[0]:
            day["level"] = 1
        elif count <= cuts[1]:
            day["level"] = 2
        elif count <= cuts[2]:
            day["level"] = 3
        elif count <= cuts[3]:
            day["level"] = 4
        else:
            day["level"] = 5


def build_payload(username: str, html: str, days: list[dict]) -> dict:
    compute_levels(days)
    current, longest = compute_streaks(days)

    monthly: dict[str, int] = defaultdict(int)
    for day in days:
        monthly[day["date"][:7]] += day["count"]

    best = max(days, key=lambda d: d["count"])
    scraped_total = sum(d["count"] for d in days)
    active_days = sum(1 for d in days if d["count"] > 0)

    return {
        "username": username,
        "generated_at": date.today().isoformat(),
        "range": {"from": days[0]["date"], "to": days[-1]["date"]},
        "stats": {
            "total": total_from_header(html) or scraped_total,
            "active_days": active_days,
            "total_days": len(days),
            "busiest_day": {"date": best["date"], "count": best["count"]},
            "daily_average": round(scraped_total / len(days), 2),
            "current_streak": current,
            "longest_streak": longest,
            "monthly_totals": dict(sorted(monthly.items())),
        },
        "days": days,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    try:
        html = fetch_html(args.username)
        days = parse_days(html)
    except (requests.RequestException, RuntimeError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    payload = build_payload(args.username, html, days)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    stats = payload["stats"]
    print(f"wrote {args.out}")
    print(f"  {stats['total']:,} contributions  ({payload['range']['from']} to {payload['range']['to']})")
    print(f"  active days:     {stats['active_days']}/{stats['total_days']}")
    print(f"  current streak:  {stats['current_streak']['length']} days")
    print(f"  longest streak:  {stats['longest_streak']['length']} days")
    print(f"  busiest day:     {stats['busiest_day']['date']} ({stats['busiest_day']['count']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
