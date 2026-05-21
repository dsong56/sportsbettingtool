"""
NHL game log fetcher via the official NHL Stats API (free, no auth).
"""
import httpx

_BASE = "https://api-web.nhle.com/v1"

_STAT_MAP = {
    "Shots on Goal": "shots",
    "Saves":         "saves",       # goalie only
    "Points":        "points",
    "Blocked Shots": "blockedShots",
    "Assists":       "assists",
    "Goals":         "goals",
}


async def _search_player_id(client: httpx.AsyncClient, name: str) -> str | None:
    """Search the NHL roster index for a player ID by name."""
    resp = await client.get(f"{_BASE}/player-search", params={"q": name})
    if resp.status_code != 200:
        return None
    players = resp.json().get("players", [])
    if not players:
        return None
    return str(players[0]["playerId"])


async def fetch_game_logs(player_name: str, n_games: int = 30) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        player_id = await _search_player_id(client, player_name)
        if not player_id:
            return []

        resp = await client.get(f"{_BASE}/player/{player_id}/game-log/now")
        if resp.status_code != 200:
            return []
        raw = resp.json().get("gameLog", [])

    rows = []
    for entry in raw[:n_games]:
        toi_raw = entry.get("toi", "0:00") or "0:00"
        try:
            parts = str(toi_raw).split(":")
            minutes = int(parts[0]) + int(parts[1]) / 60 if len(parts) == 2 else 0.0
        except (ValueError, IndexError):
            minutes = 0.0

        rows.append({
            "game_date":    entry.get("gameDate", "")[:10],
            "minutes":      minutes,
            "shots":        entry.get("shots"),
            "saves":        entry.get("saves"),
            "points":       entry.get("points"),
            "blockedShots": entry.get("blockedShots"),
            "assists":      entry.get("assists"),
            "goals":        entry.get("goals"),
        })

    return sorted(rows, key=lambda x: x["game_date"], reverse=True)


def get_stat_value(row: dict, stat_type: str) -> float | None:
    key = _STAT_MAP.get(stat_type)
    if key is None:
        return None
    val = row.get(key)
    return float(val) if val is not None else None
