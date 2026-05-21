"""
NBA game log fetcher via BallDontLie API (free, no auth required).
Returns per-game stat lines for a player, filtered for minutes played.
"""
import httpx
from backend.config import MINUTES_FILTER_STD

_BASE = "https://api.balldontlie.io/v1"
_STAT_MAP = {
    "Points":        "pts",
    "Rebounds":      "reb",
    "Assists":       "ast",
    "3-PT Made":     "fg3m",
    "Blocked Shots": "blk",
    "Steals":        "stl",
    "Pts+Rebs+Asts": None,  # computed
    "Pts+Rebs":      None,
    "Pts+Asts":      None,
    "Rebs+Asts":     None,
}


def _extract_stat(row: dict, stat_type: str) -> float | None:
    match stat_type:
        case "Points":        return row.get("pts")
        case "Rebounds":      return row.get("reb")
        case "Assists":       return row.get("ast")
        case "3-PT Made":     return row.get("fg3m")
        case "Blocked Shots": return row.get("blk")
        case "Steals":        return row.get("stl")
        case "Pts+Rebs+Asts":
            p, r, a = row.get("pts"), row.get("reb"), row.get("ast")
            return (p + r + a) if all(v is not None for v in (p, r, a)) else None
        case "Pts+Rebs":
            p, r = row.get("pts"), row.get("reb")
            return (p + r) if all(v is not None for v in (p, r)) else None
        case "Pts+Asts":
            p, a = row.get("pts"), row.get("ast")
            return (p + a) if all(v is not None for v in (p, a)) else None
        case "Rebs+Asts":
            r, a = row.get("reb"), row.get("ast")
            return (r + a) if all(v is not None for v in (r, a)) else None
    return None


async def fetch_game_logs(player_name: str, n_games: int = 30) -> list[dict]:
    """
    Returns a list of game dicts with keys: game_date, minutes, stat_value (per stat).
    Minutes filter is applied by callers using season average ± MINUTES_FILTER_STD std devs.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        # Search for player
        search_resp = await client.get(f"{_BASE}/players", params={"search": player_name, "per_page": 5})
        if search_resp.status_code != 200:
            return []
        players = search_resp.json().get("data", [])
        if not players:
            return []
        player_id = players[0]["id"]

        # Fetch recent game stats
        stats_resp = await client.get(f"{_BASE}/stats", params={
            "player_ids[]": player_id,
            "per_page": n_games,
            "seasons[]": [2024],
        })
        if stats_resp.status_code != 200:
            return []

    rows = []
    for entry in stats_resp.json().get("data", []):
        mins_raw = entry.get("min", "0:00") or "0:00"
        try:
            parts = str(mins_raw).split(":")
            minutes = int(parts[0]) + int(parts[1]) / 60 if len(parts) == 2 else float(parts[0])
        except (ValueError, IndexError):
            minutes = 0.0

        rows.append({
            "game_date": entry["game"]["date"][:10],
            "minutes":   minutes,
            "pts":       entry.get("pts"),
            "reb":       entry.get("reb"),
            "ast":       entry.get("ast"),
            "fg3m":      entry.get("fg3m"),
            "blk":       entry.get("blk"),
            "stl":       entry.get("stl"),
        })

    return sorted(rows, key=lambda x: x["game_date"], reverse=True)


def filter_by_minutes(logs: list[dict]) -> tuple[list[dict], bool]:
    """
    Remove games outside ±MINUTES_FILTER_STD std devs of season avg minutes.
    Returns (filtered_logs, trending_down_flag).
    trending_down = True if the last 3 games avg minutes < season avg - 0.5 std.
    """
    import statistics
    all_mins = [g["minutes"] for g in logs if g["minutes"] > 0]
    if len(all_mins) < 4:
        return logs, False

    mu = statistics.mean(all_mins)
    sd = statistics.stdev(all_mins)
    lo, hi = mu - MINUTES_FILTER_STD * sd, mu + MINUTES_FILTER_STD * sd
    filtered = [g for g in logs if lo <= g["minutes"] <= hi]

    recent_3 = [g["minutes"] for g in logs[:3] if g["minutes"] > 0]
    trending_down = bool(recent_3 and statistics.mean(recent_3) < mu - 0.5 * sd)

    return filtered, trending_down
