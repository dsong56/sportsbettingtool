"""
Unified Odds API scraper for NBA, NHL, MLB.

Batches all stat markets into a single request per game — reducing API usage
from (n_games × n_markets) calls down to (n_games + 1) calls per refresh.

Also fetches alternate markets (player_points_alternate etc.) — the "15+ / 20+
points" style props. These ride along in the same batched request per game, so
they add quota cost (the Odds API bills per market × region) but no extra
HTTP round trips.

Returns raw prop rows: (player_name, direction, line, odds, book, stat_type, sport, is_alt)
"""
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
import asyncio
import httpx

from backend.config import ODDS_API_KEY, settings

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
            "Goals":            "player_goals",
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


# Alternate-line markets: same stat, but books quote a ladder of lines
# (e.g. 15+, 20+, 25+ points). Usually Over-only.
# stat_type label → odds-api alternate market key, per sport.
ALT_MARKET_CONFIG: dict[str, dict[str, str]] = {
    "NBA": {
        "Points":           "player_points_alternate",
        "Rebounds":         "player_rebounds_alternate",
        "Assists":          "player_assists_alternate",
        "3-PT Made":        "player_threes_alternate",
        "Blocked Shots":    "player_blocks_alternate",
        "Steals":           "player_steals_alternate",
        "Pts+Rebs+Asts":    "player_points_rebounds_assists_alternate",
        "Pts+Rebs":         "player_points_rebounds_alternate",
        "Pts+Asts":         "player_points_assists_alternate",
        "Rebs+Asts":        "player_rebounds_assists_alternate",
    },
    "NHL": {
        "Shots on Goal":    "player_shots_on_goal_alternate",
        "Saves":            "player_total_saves_alternate",
        "Points":           "player_points_alternate",
        "Blocked Shots":    "player_blocked_shots_alternate",
        "Assists":          "player_assists_alternate",
        "Goals":            "player_goals_alternate",
    },
    "MLB": {
        "Pitcher Strikeouts": "pitcher_strikeouts_alternate",
        "Total Bases":        "batter_total_bases_alternate",
        "Hits Allowed":       "pitcher_hits_allowed_alternate",
        "Hits":               "batter_hits_alternate",
        "RBIs":               "batter_rbis_alternate",
        "Walks":              "batter_walks_alternate",
    },
}


class OddsProp(NamedTuple):
    player_name: str
    direction:   str    # 'Over' | 'Under'
    line:        float
    odds:        int    # American
    book:        str
    stat_type:   str    # PrizePicks label
    sport:       str
    is_alt:      bool = False   # True for alternate-line (15+/20+) markets


class OddsAPIError(RuntimeError):
    """Systemic Odds API failure (bad key, quota, invalid market) — fail the job loudly."""


def _raise_for_systemic(resp: httpx.Response, context: str) -> None:
    """401/403 = bad key or quota, 422 = invalid market key (body names it).

    These affect every request, so surface them instead of silently returning
    no props — otherwise the refresh job reports success over an empty table.
    """
    if resp.status_code in (401, 403, 422, 429):
        raise OddsAPIError(
            f"Odds API {context} failed with HTTP {resp.status_code}: {resp.text[:300]}"
        )


async def _get_game_ids(client: httpx.AsyncClient, sport_slug: str) -> list[str]:
    """1 request — returns game IDs starting within the lookahead window.

    Unfiltered, the events endpoint returns games up to ~8 days out; fetching
    odds for all of them is slow and burns quota (billed per market returned).
    """
    now = datetime.now(timezone.utc)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    resp = await client.get(
        f"{_BASE}/{sport_slug}/events",
        params={
            "apiKey": ODDS_API_KEY,
            "commenceTimeFrom": now.strftime(fmt),
            "commenceTimeTo": (now + timedelta(hours=settings.odds_lookahead_hours)).strftime(fmt),
        },
    )
    _raise_for_systemic(resp, f"events lookup for {sport_slug}")
    if resp.status_code != 200:
        raise OddsAPIError(
            f"Odds API events lookup for {sport_slug} returned HTTP {resp.status_code}: {resp.text[:300]}"
        )
    return [g["id"] for g in resp.json()]


async def _get_all_markets_for_game(
    client: httpx.AsyncClient,
    sport_slug: str,
    game_id: str,
    market_map: dict[str, str],       # {pp_stat: odds_api_key} — standard markets
    alt_market_map: dict[str, str],   # {pp_stat: odds_api_key} — alternate markets
    sport: str,
) -> list[OddsProp]:
    """1 request per game — fetches standard + alternate markets in a single batched call."""
    # Reverse lookups: odds_api_key → (pp_stat_type, is_alt)
    api_key_to_pp: dict[str, tuple[str, bool]] = {
        v: (k, False) for k, v in market_map.items()
    }
    api_key_to_pp.update({v: (k, True) for k, v in alt_market_map.items()})

    async def _fetch(markets: list[str]) -> httpx.Response:
        return await client.get(
            f"{_BASE}/{sport_slug}/events/{game_id}/odds",
            params={
                "apiKey":      ODDS_API_KEY,
                "regions":     "us",
                "markets":     ",".join(markets),
                "oddsFormat":  "american",
            },
        )

    resp = await _fetch(list(market_map.values()) + list(alt_market_map.values()))
    if resp.status_code == 422 and alt_market_map:
        # An alternate market key wasn't recognized — retry with standard markets only
        # rather than losing the whole game.
        resp = await _fetch(list(market_map.values()))
    _raise_for_systemic(resp, f"odds fetch for game {game_id}")
    if resp.status_code != 200:
        # Transient per-game issues (e.g. game started/removed) — skip just this game
        return []

    results: list[OddsProp] = []
    for bm in resp.json().get("bookmakers", []):
        for mkt in bm["markets"]:
            mapped = api_key_to_pp.get(mkt["key"])
            if mapped is None:
                continue
            pp_stat, is_alt = mapped
            for oc in mkt["outcomes"]:
                point = oc.get("point")
                if point is None or oc["name"] not in ("Over", "Under"):
                    continue   # yes/no markets (e.g. anytime scorer) don't fit the O/U model
                results.append(OddsProp(
                    player_name=oc["description"],
                    direction=oc["name"],
                    line=float(point),
                    odds=int(oc["price"]),
                    book=bm["title"],
                    stat_type=pp_stat,
                    sport=sport,
                    is_alt=is_alt,
                ))
    return results


async def fetch_odds(sport: str) -> list[OddsProp]:
    """
    Fetches all player prop odds for a sport.
    Request count: 1 (game IDs) + n_games (one batched call each).
    Previously: 1 + n_games × n_markets.
    """
    if not ODDS_API_KEY:
        raise OddsAPIError(
            "ODDS_API_KEY is not set. Add it to .env in the project root — note the file "
            "is read relative to the directory you launch uvicorn from."
        )

    sport_slug, market_map = SPORT_CONFIG[sport]
    alt_market_map = ALT_MARKET_CONFIG.get(sport, {}) if settings.include_alt_lines else {}

    async with httpx.AsyncClient(timeout=30) as client:
        game_ids = await _get_game_ids(client, sport_slug)
        if not game_ids:
            raise OddsAPIError(
                f"The Odds API returned no {sport} games starting in the next "
                f"{settings.odds_lookahead_hours}h."
            )

        # Fetch all markets for all games concurrently, chunked to be polite
        tasks = [
            _get_all_markets_for_game(client, sport_slug, gid, market_map, alt_market_map, sport)
            for gid in game_ids
        ]
        results: list[OddsProp] = []
        chunk = 10
        for i in range(0, len(tasks), chunk):
            batch = await asyncio.gather(*tasks[i:i + chunk])
            for props in batch:
                results.extend(props)

    return results
