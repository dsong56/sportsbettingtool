"""
MLB game log fetcher via the official MLB Stats API (free, no auth).
"""
import httpx

_BASE = "https://statsapi.mlb.com/api/v1"

_STAT_MAP = {
    "Pitcher Strikeouts": "strikeOuts",
    "Total Bases":        "totalBases",
    "Hits Allowed":       "hits",          # pitcher hits allowed
    "Pitcher Outs":       "outs",
    "Hits+Runs+RBIs":     None,            # computed
}


async def _search_player_id(client: httpx.AsyncClient, name: str) -> tuple[int | None, str | None]:
    """Returns (player_id, position) or (None, None)."""
    resp = await client.get(f"{_BASE}/people/search", params={"names": name, "sportId": 1})
    if resp.status_code != 200:
        return None, None
    people = resp.json().get("people", [])
    if not people:
        return None, None
    p = people[0]
    return p["id"], p.get("primaryPosition", {}).get("abbreviation", "")


async def fetch_game_logs(player_name: str, n_games: int = 30) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        player_id, position = await _search_player_id(client, player_name)
        if not player_id:
            return []

        is_pitcher = position in ("SP", "RP", "P")
        group = "pitching" if is_pitcher else "hitting"

        resp = await client.get(
            f"{_BASE}/people/{player_id}/stats",
            params={"stats": "gameLog", "group": group, "sportId": 1, "season": 2025},
        )
        if resp.status_code != 200:
            return []
        splits = resp.json().get("stats", [{}])[0].get("splits", [])

    rows = []
    for entry in splits[-n_games:]:
        s = entry.get("stat", {})

        # Innings pitched → approximate minutes (3 outs = 1 inning ≈ 15-20 min)
        ip_raw = s.get("inningsPitched", "0.0")
        try:
            ip = float(ip_raw)
            minutes = ip * 17  # rough proxy for pitchers
        except ValueError:
            minutes = 0.0

        hits = s.get("hits")
        runs = s.get("runs")
        rbi  = s.get("rbi")

        rows.append({
            "game_date":    entry.get("date", "")[:10],
            "minutes":      minutes,
            "strikeOuts":   s.get("strikeOuts"),
            "totalBases":   s.get("totalBases"),
            "hits":         hits,
            "outs":         s.get("outs"),
            "hits_runs_rbi": (hits + runs + rbi)
                             if all(v is not None for v in (hits, runs, rbi)) else None,
        })

    return sorted(rows, key=lambda x: x["game_date"], reverse=True)


def get_stat_value(row: dict, stat_type: str) -> float | None:
    match stat_type:
        case "Pitcher Strikeouts": v = row.get("strikeOuts")
        case "Total Bases":        v = row.get("totalBases")
        case "Hits Allowed":       v = row.get("hits")
        case "Pitcher Outs":       v = row.get("outs")
        case "Hits+Runs+RBIs":     v = row.get("hits_runs_rbi")
        case _:                    v = None
    return float(v) if v is not None else None
