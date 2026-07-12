"""
NFL game log fetcher.

Primary source: ESPN's hidden site API (free, no auth).
Fallback: BallDontLie's NFL API (uses the same BALLDONTLIE_API_KEY; NFL
endpoints require a paid plan, so this only helps when the key supports it).

Normalized log row keys (same shape contract as nba/nhl/mlb):
  game_date, minutes, passing_yards, rushing_yards, receiving_yards,
  receptions, touchdowns (passing + rushing + receiving combined),
  completions, interceptions
"""
import httpx
from backend.config import settings

_ESPN_SEARCH = "https://site.web.api.espn.com/apis/search/v2"
_ESPN_GAMELOG = "https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes/{athlete_id}/gamelog"
_BDL_BASE = "https://api.balldontlie.io/nfl/v1"

# ESPN gamelog stat names → our normalized keys (single-source stats)
_ESPN_STAT_KEYS = {
    "passingYards":      "passing_yards",
    "rushingYards":      "rushing_yards",
    "receivingYards":    "receiving_yards",
    "receptions":        "receptions",
    "completions":       "completions",
    "interceptions":     "interceptions",
}
_ESPN_TD_KEYS = ("passingTouchdowns", "rushingTouchdowns", "receivingTouchdowns")


def _to_float(v) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


# ---------- ESPN ----------

async def _espn_search_athlete_id(client: httpx.AsyncClient, name: str) -> str | None:
    resp = await client.get(_ESPN_SEARCH, params={"query": name, "limit": 10})
    if resp.status_code != 200:
        return None
    for section in resp.json().get("results", []):
        if section.get("type") != "player":
            continue
        for item in section.get("contents", []):
            uid = item.get("uid", "")
            # uid format: "s:20~l:28~a:<athlete_id>"; s:20/l:28 = football/NFL
            if "l:28" not in uid:
                continue
            for part in uid.split("~"):
                if part.startswith("a:"):
                    return part[2:]
    return None


def _parse_espn_gamelog(data: dict, n_games: int) -> list[dict]:
    names: list[str] = data.get("names", [])
    events_meta: dict = data.get("events", {})

    rows: list[dict] = []
    for season_type in data.get("seasonTypes", []):
        for category in season_type.get("categories", []):
            for event in category.get("events", []):
                event_id = str(event.get("eventId", ""))
                meta = events_meta.get(event_id, {})
                game_date = str(meta.get("gameDate", ""))[:10]
                if not game_date:
                    continue

                stats = dict(zip(names, event.get("stats", [])))
                row: dict = {"game_date": game_date, "minutes": 0.0}
                for espn_key, our_key in _ESPN_STAT_KEYS.items():
                    row[our_key] = _to_float(stats.get(espn_key))

                td_parts = [_to_float(stats.get(k)) for k in _ESPN_TD_KEYS]
                present = [t for t in td_parts if t is not None]
                row["touchdowns"] = sum(present) if present else None

                rows.append(row)

    rows.sort(key=lambda r: r["game_date"], reverse=True)
    return rows[:n_games]


async def _fetch_espn(client: httpx.AsyncClient, player_name: str, n_games: int) -> list[dict]:
    athlete_id = await _espn_search_athlete_id(client, player_name)
    if not athlete_id:
        return []
    resp = await client.get(_ESPN_GAMELOG.format(athlete_id=athlete_id))
    if resp.status_code != 200:
        return []
    return _parse_espn_gamelog(resp.json(), n_games)


# ---------- BallDontLie fallback ----------

def _bdl_headers() -> dict:
    return {"Authorization": settings.balldontlie_api_key} if settings.balldontlie_api_key else {}


async def _fetch_balldontlie(client: httpx.AsyncClient, player_name: str, n_games: int) -> list[dict]:
    search = await client.get(
        f"{_BDL_BASE}/players",
        params={"search": player_name, "per_page": 5},
        headers=_bdl_headers(),
    )
    if search.status_code != 200:
        return []
    players = search.json().get("data", [])
    if not players:
        return []
    player_id = players[0]["id"]

    from datetime import date
    # NFL season = year it started (kicks off in September)
    today = date.today()
    season = today.year if today.month >= 9 else today.year - 1

    resp = await client.get(
        f"{_BDL_BASE}/stats",
        params={"player_ids[]": player_id, "seasons[]": [season], "per_page": n_games},
        headers=_bdl_headers(),
    )
    if resp.status_code != 200:
        return []

    rows: list[dict] = []
    for entry in resp.json().get("data", []):
        game_date = str(entry.get("game", {}).get("date", ""))[:10]
        if not game_date:
            continue

        td_parts = [_to_float(entry.get(k)) for k in
                    ("passing_touchdowns", "rushing_touchdowns", "receiving_touchdowns")]
        present = [t for t in td_parts if t is not None]

        rows.append({
            "game_date":       game_date,
            "minutes":         0.0,
            "passing_yards":   _to_float(entry.get("passing_yards")),
            "rushing_yards":   _to_float(entry.get("rushing_yards")),
            "receiving_yards": _to_float(entry.get("receiving_yards")),
            "receptions":      _to_float(entry.get("receptions")),
            "touchdowns":      sum(present) if present else None,
            "completions":     _to_float(entry.get("passing_completions")),
            "interceptions":   _to_float(entry.get("passing_interceptions")),
        })

    return sorted(rows, key=lambda r: r["game_date"], reverse=True)[:n_games]


# ---------- public API (same contract as nba/nhl/mlb) ----------

async def fetch_game_logs(player_name: str, n_games: int = 30) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            logs = await _fetch_espn(client, player_name, n_games)
        except httpx.HTTPError:
            logs = []
        if logs:
            return logs
        try:
            return await _fetch_balldontlie(client, player_name, n_games)
        except httpx.HTTPError:
            return []


_STAT_MAP = {
    "Passing Yards":   "passing_yards",
    "Pass Yards":      "passing_yards",     # PrizePicks alias
    "Rushing Yards":   "rushing_yards",
    "Rush Yards":      "rushing_yards",
    "Receiving Yards": "receiving_yards",
    "Receptions":      "receptions",
    "Touchdowns":      "touchdowns",        # pass + rush + rec combined
    "Completions":     "completions",
    "Pass Completions": "completions",
    "Interceptions":   "interceptions",
    "Pass Interceptions": "interceptions",
    "INT":             "interceptions",
}


def get_stat_value(row: dict, stat_type: str) -> float | None:
    key = _STAT_MAP.get(stat_type)
    if key is None:
        return None
    val = row.get(key)
    return float(val) if val is not None else None
