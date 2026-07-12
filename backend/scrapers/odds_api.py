"""
Unified Odds API scraper for NBA, NHL, MLB.

Batches all stat markets into a single request per game — reducing API usage
from (n_games × n_markets) calls down to (n_games + 1) calls per refresh.

Returns raw prop rows: (player_name, direction, line, odds, book, stat_type, sport)
"""
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
import asyncio
import logging
import httpx

from backend.config import ODDS_API_KEY, settings

log = logging.getLogger(__name__)

_BASE = "https://api.the-odds-api.com/v4/sports"

# Most recent x-requests-remaining seen on any Odds API response.
# Surfaced on the scrape job so the frontend can display it.
last_credits_remaining: str | None = None

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
    "NFL": (
        "americanfootball_nfl",
        # Keys must match PrizePicks NFL stat_type labels; verify against the
        # live board at preseason. Combined "Touchdowns" has no O/U odds market,
        # so those props rely on historical signal only and are skipped here.
        {
            "Pass Yards":         "player_pass_yds",
            "Rush Yards":         "player_rush_yds",
            "Receiving Yards":    "player_reception_yds",
            "Receptions":         "player_receptions",
            "Pass Completions":   "player_pass_completions",
            "INT":                "player_pass_interceptions",
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
    """Free request — game IDs for the sport, limited to the slate window
    so we don't pay for per-game odds calls on games days away."""
    window_end = (
        datetime.now(timezone.utc) + timedelta(hours=settings.odds_window_hours)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    resp = await client.get(
        f"{_BASE}/{sport_slug}/events",
        params={"apiKey": ODDS_API_KEY, "regions": "us",
                "markets": "h2h", "oddsFormat": "american",
                "commenceTimeTo": window_end},
    )
    if resp.status_code != 200:
        return []
    _track_credits(resp)
    return [g["id"] for g in resp.json()]


def _track_credits(resp: httpx.Response) -> None:
    global last_credits_remaining
    remaining = resp.headers.get("x-requests-remaining")
    if remaining is not None:
        last_credits_remaining = remaining
        log.info("Odds API credits remaining: %s", remaining)


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
    _track_credits(resp)

    results: list[OddsProp] = []
    for bm in resp.json().get("bookmakers", []):
        for mkt in bm["markets"]:
            pp_stat = api_key_to_pp.get(mkt["key"])
            if pp_stat is None:
                continue
            for oc in mkt["outcomes"]:
                if oc.get("point") is None:  # yes/no markets carry no line
                    continue
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


async def fetch_odds(sport: str, stat_types: set[str] | None = None) -> list[OddsProp]:
    """
    Fetches player prop odds for a sport.

    stat_types: when given, only these PrizePicks stat labels are requested.
    Credits are billed per market per game, so requesting only the markets
    actually on today's board is the main cost lever.
    """
    if not ODDS_API_KEY:
        # Fail loudly — returning [] here would surface as a confusing
        # "0 props found" instead of pointing at the actual problem
        raise RuntimeError("ODDS_API_KEY missing — add it to your .env file")

    sport_slug, market_map = SPORT_CONFIG[sport]
    if stat_types is not None:
        market_map = {k: v for k, v in market_map.items() if k in stat_types}
    if settings.odds_markets_exclude:
        market_map = {k: v for k, v in market_map.items()
                      if k not in settings.odds_markets_exclude}
    if not market_map:
        return []

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
