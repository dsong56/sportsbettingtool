"""
NBA game log fetcher via BallDontLie API v1.
Requires a free API key from balldontlie.io — set BALLDONTLIE_API_KEY in .env.
"""
import statistics
import httpx
from backend.config import settings

_BASE = "https://api.balldontlie.io/v1"


def _headers() -> dict:
    return {"Authorization": settings.balldontlie_api_key} if settings.balldontlie_api_key else {}


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
    async with httpx.AsyncClient(headers=_headers(), timeout=15) as client:
        search_resp = await client.get(f"{_BASE}/players", params={"search": player_name, "per_page": 5})
        if search_resp.status_code != 200:
            return []
        players = search_resp.json().get("data", [])
        if not players:
            return []
        player_id = players[0]["id"]

        from datetime import date
        # BallDontLie season = year the season started (e.g. 2025 = 2025-26 season).
        # NBA season starts in October, so before October use the previous year.
        today = date.today()
        season = today.year if today.month >= 10 else today.year - 1

        stats_resp = await client.get(f"{_BASE}/stats", params={
            "player_ids[]": player_id,
            "per_page": n_games,
            "seasons[]": [season],
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
    Remove games outside ±minutes_std_threshold std devs of season avg.
    Returns (filtered_logs, trending_down_flag).
    """
    all_mins = [g["minutes"] for g in logs if g["minutes"] > 0]
    if len(all_mins) < 4:
        return logs, False

    mu = statistics.mean(all_mins)
    sd = statistics.stdev(all_mins)
    threshold = settings.minutes_std_threshold * sd
    filtered = [g for g in logs if abs(g["minutes"] - mu) <= threshold]

    recent_3 = [g["minutes"] for g in logs[:3] if g["minutes"] > 0]
    trending_down = bool(recent_3 and statistics.mean(recent_3) < mu - 0.5 * sd)

    return filtered, trending_down
