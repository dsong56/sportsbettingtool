"""
PrizePicks scraper — direct httpx calls, no Selenium.
api.prizepicks.com/projections returns clean JSON with a standard User-Agent.
"""
from datetime import datetime, timezone, timedelta
from typing import NamedTuple

import httpx

from backend.config import LEAGUE_IDS

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
_BASE = "https://api.prizepicks.com/projections"
_CENTRAL = timezone(timedelta(hours=-5))


class PPProjection(NamedTuple):
    player_name: str
    stat_type:   str
    line_score:  float
    game_date:   str   # "May-21-2026 07:10 PM"
    sport:       str


def _fmt_date(iso: str) -> str:
    dt = datetime.fromisoformat(iso).astimezone(_CENTRAL)
    return dt.strftime(f"{dt.strftime('%b')}-{dt.day}-%Y %I:%M %p")


async def fetch_projections(sport: str) -> list[PPProjection]:
    league_id = LEAGUE_IDS[sport]
    params = {"league_id": league_id, "per_page": 1000, "single_stat": True}

    async with httpx.AsyncClient(headers=_HEADERS, timeout=15) as client:
        resp = await client.get(_BASE, params=params)
        resp.raise_for_status()
        data = resp.json()

    player_map: dict[str, str] = {
        elem["id"]: elem["attributes"]["name"]
        for elem in data.get("included", [])
        if elem["type"] == "new_player"
    }

    results: list[PPProjection] = []
    for proj in data.get("data", []):
        if proj["type"] != "projection":
            continue
        attrs = proj["attributes"]
        if attrs.get("status") != "pre_game":
            continue

        player_id = proj["relationships"]["new_player"]["data"]["id"]
        player_name = player_map.get(player_id, "Unknown")
        line = attrs.get("flash_sale_line_score") or attrs["line_score"]
        stat = attrs["stat_type"]
        date_str = _fmt_date(attrs["start_time"])

        results.append(PPProjection(player_name, stat, float(line), date_str, sport))

    return results
