"""
Unified Odds API scraper for NBA, NHL, MLB.

Batches all stat markets into a single request per game — reducing API usage
from (n_games × n_markets) calls down to (n_games + 1) calls per refresh.

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
            "Hits":               "batter_hits",
            "RBIs":               "batter_rbis",
            "Runs":               "batter_runs_scored",
            "Singles":            "batter_singles",
            "Doubles":            "batter_doubles",
            "Walks":              "batter_walks",
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
    """1 request — returns all upcoming game IDs for the sport."""
    resp = await client.get(
        f"{_BASE}/{sport_slug}/events",
        params={"apiKey": ODDS_API_KEY, "regions": "us",
                "markets": "h2h", "oddsFormat": "american"},
    )
    if resp.status_code != 200:
        return []
    return [g["id"] for g in resp.json()]


async def _get_all_markets_for_game(
    client: httpx.AsyncClient,
    sport_slug: str,
    game_id: str,
    market_map: dict[str, str],   # {pp_stat: odds_api_key}
    sport: str,
) -> list[OddsProp]:
    """1 request per game — fetches all markets in a single batched call."""
    # Build reverse lookup: odds_api_key → pp_stat_type
    api_key_to_pp = {v: k for k, v in market_map.items()}
    markets_param = ",".join(market_map.values())

    resp = await client.get(
        f"{_BASE}/{sport_slug}/events/{game_id}/odds",
        params={
            "apiKey":      ODDS_API_KEY,
            "regions":     "us",
            "markets":     markets_param,
            "oddsFormat":  "american",
        },
    )
    if resp.status_code != 200:
        return []

    results: list[OddsProp] = []
    for bm in resp.json().get("bookmakers", []):
        for mkt in bm["markets"]:
            pp_stat = api_key_to_pp.get(mkt["key"])
            if pp_stat is None:
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
    """
    Fetches all player prop odds for a sport.
    Request count: 1 (game IDs) + n_games (one batched call each).
    Previously: 1 + n_games × n_markets.
    """
    sport_slug, market_map = SPORT_CONFIG[sport]

    async with httpx.AsyncClient(timeout=30) as client:
        game_ids = await _get_game_ids(client, sport_slug)
        if not game_ids:
            return []

        # Fetch all markets for all games concurrently, chunked to be polite
        tasks = [
            _get_all_markets_for_game(client, sport_slug, gid, market_map, sport)
            for gid in game_ids
        ]
        results: list[OddsProp] = []
        chunk = 10
        for i in range(0, len(tasks), chunk):
            batch = await asyncio.gather(*tasks[i:i + chunk])
            for props in batch:
                results.extend(props)

    return results
