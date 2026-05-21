"""
Unified Odds API scraper for NBA, NHL, MLB.
Returns raw prop rows: (player_name, direction, line, odds, book, stat_type, sport)
"""
from typing import NamedTuple
import asyncio
import httpx

from backend.config import ODDS_API_KEY

_BASE = "https://api.the-odds-api.com/v4/sports"

# sport key → (odds-api sport slug, {pp_stat_type: odds_api_market_key})
SPORT_CONFIG: dict[str, tuple[str, dict[str, str]]] = {
    "NBA": (
        "basketball_nba",
        {
            "Points":           "player_points",
            "Rebounds":         "player_rebounds",
            "Assists":          "player_assists",
            "3-PT Made":        "player_threes",
            "Blocked Shots":    "player_blocks",
            "Steals":           "player_steals",
            "Pts+Rebs+Asts":    "player_points_rebounds_assists",
            "Pts+Rebs":         "player_points_rebounds",
            "Pts+Asts":         "player_points_assists",
            "Rebs+Asts":        "player_rebounds_assists",
        },
    ),
    "NHL": (
        "icehockey_nhl",
        {
            "Shots on Goal":    "player_shots_on_goal",
            "Saves":            "player_total_saves",
            "Points":           "player_points",
            "Blocked Shots":    "player_blocked_shots",
            "Assists":          "player_assists",
            "Goals":            "player_goal_scorer_anytime",
        },
    ),
    "MLB": (
        "baseball_mlb",
        {
            "Pitcher Strikeouts": "pitcher_strikeouts",
            "Total Bases":        "batter_total_bases",
            "Hits Allowed":       "pitcher_hits_allowed",
            "Pitcher Outs":       "pitcher_outs",
            "Hits+Runs+RBIs":     "batter_hits_runs_rbis",
        },
    ),
}


class OddsProp(NamedTuple):
    player_name: str
    direction:   str    # 'Over' | 'Under'
    line:        float
    odds:        int    # American
    book:        str
    stat_type:   str    # PrizePicks label
    sport:       str


async def _get_game_ids(client: httpx.AsyncClient, sport_slug: str) -> list[str]:
    url = f"{_BASE}/{sport_slug}/events"
    resp = await client.get(url, params={"apiKey": ODDS_API_KEY, "regions": "us",
                                          "markets": "h2h", "oddsFormat": "american"})
    if resp.status_code != 200:
        return []
    return [g["id"] for g in resp.json()]


async def _get_market(
    client: httpx.AsyncClient,
    sport_slug: str,
    game_id: str,
    market_key: str,
    pp_stat: str,
    sport: str,
) -> list[OddsProp]:
    url = f"{_BASE}/{sport_slug}/events/{game_id}/odds"
    resp = await client.get(url, params={
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": market_key,
        "oddsFormat": "american",
    })
    if resp.status_code != 200:
        return []

    results: list[OddsProp] = []
    for bm in resp.json().get("bookmakers", []):
        for mkt in bm["markets"]:
            if mkt["key"] != market_key:
                continue
            for oc in mkt["outcomes"]:
                results.append(OddsProp(
                    player_name=oc["description"],
                    direction=oc["name"],
                    line=float(oc["point"]),
                    odds=int(oc["price"]),
                    book=bm["title"],
                    stat_type=pp_stat,
                    sport=sport,
                ))
    return results


async def fetch_odds(sport: str) -> list[OddsProp]:
    sport_slug, market_map = SPORT_CONFIG[sport]

    async with httpx.AsyncClient(timeout=20) as client:
        game_ids = await _get_game_ids(client, sport_slug)
        if not game_ids:
            return []

        tasks = [
            _get_market(client, sport_slug, gid, mkey, pp_stat, sport)
            for gid in game_ids
            for pp_stat, mkey in market_map.items()
        ]
        # Chunk to avoid hammering the API simultaneously
        results: list[OddsProp] = []
        chunk = 10
        for i in range(0, len(tasks), chunk):
            batch = await asyncio.gather(*tasks[i:i + chunk])
            for props in batch:
                results.extend(props)

    return results
