"""
Full EV pipeline for a single sport.

Steps:
1. Fetch PrizePicks projections (httpx)
2. Fetch Odds API props (httpx, async batched)
3. For each (player, stat, line) on PrizePicks:
   a. Collect all book odds → Shin devig → weighted market probability
   b. Fetch game logs (cached) → historical hit rate with Beta prior + minutes filter
   c. Query previous odds snapshot → steam signal (≥3 books required)
   d. Blend signals → EVResult
4. Persist odds snapshots + ev_results + predictions to DB
5. Return list of serialisable dicts for the API layer
"""
from __future__ import annotations

import unicodedata
from collections import defaultdict
from datetime import datetime
from difflib import get_close_matches

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import BOOK_WEIGHTS, PRIVATE_BOOKS
from backend.scrapers.prizepicks import fetch_projections, PPProjection
from backend.scrapers.odds_api import fetch_odds, OddsProp
from backend.ev.shin import devig_book_odds
from backend.ev.historical import compute_hit_rate, rolling_window_rates
from backend.ev.movement import compute_movement_signal
from backend.ev.blend import EVResult, breakeven
from backend.db.models import OddsSnapshot, EVResult as EVResultModel, Prediction, GameLogCache


# ---------- name normalisation ----------

def _normalise(name: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_name = nfkd.encode("ascii", "ignore").decode()
    return " ".join(ascii_name.lower().split())


async def _load_corrections(db: AsyncSession, sport: str) -> dict[str, str]:
    """Load manual name corrections: raw_name → canonical_name."""
    from backend.db.models import NameCorrection
    rows = await db.execute(
        select(NameCorrection).where(NameCorrection.sport == sport)
    )
    return {_normalise(r.raw_name): r.canonical_name for r in rows.scalars()}


def _resolve_name(name: str, canonical_pool: set[str], corrections: dict[str, str]) -> str:
    norm = _normalise(name)
    if norm in corrections:
        return corrections[norm]
    # fuzzy match against known canonical names
    matches = get_close_matches(norm, canonical_pool, n=1, cutoff=0.85)
    return matches[0] if matches else norm


# ---------- stats dispatch ----------

async def _get_game_logs(player_name: str, sport: str, db: AsyncSession) -> list[dict]:
    from backend.stats import nba, nhl, mlb

    # Check cache first (game logs don't change mid-season)
    cached = await db.execute(
        select(GameLogCache)
        .where(GameLogCache.player_name == player_name, GameLogCache.sport == sport)
        .order_by(desc(GameLogCache.cached_at))
        .limit(30)
    )
    rows = cached.scalars().all()
    if rows:
        return [r.stats for r in rows]

    match sport:
        case "NBA": logs = await nba.fetch_game_logs(player_name)
        case "NHL": logs = await nhl.fetch_game_logs(player_name)
        case "MLB": logs = await mlb.fetch_game_logs(player_name)
        case _:     logs = []

    # Cache results
    for log in logs:
        db.add(GameLogCache(
            player_name=player_name,
            sport=sport,
            game_date=log["game_date"],
            stats=log,
        ))
    if logs:
        await db.commit()
    return logs


def _get_stat_fn(sport: str):
    from backend.stats import nba, nhl, mlb
    match sport:
        case "NBA": return nba._extract_stat
        case "NHL": return nhl.get_stat_value
        case "MLB": return mlb.get_stat_value
    raise ValueError(f"Unknown sport: {sport}")


def _minutes_flag(logs: list[dict], sport: str) -> bool:
    if sport == "NBA":
        from backend.stats.nba import filter_by_minutes
        _, flag = filter_by_minutes(logs)
        return flag
    return False


# ---------- main pipeline ----------

async def run_pipeline(sport: str, db: AsyncSession) -> list[dict]:
    # 1. Fetch data in parallel
    import asyncio
    pp_task   = fetch_projections(sport)
    odds_task = fetch_odds(sport)
    pp_lines, odds_props = await asyncio.gather(pp_task, odds_task)

    # Load name corrections
    corrections = await _load_corrections(db, sport)
    canonical_pool = {_normalise(p.player_name) for p in pp_lines}

    # 2. Build odds lookup: (canonical_name, stat_type, line, direction) → [(book, odds)]
    OddsKey = tuple  # (name, stat, line, direction)
    odds_map: dict[OddsKey, list[tuple[str, int]]] = defaultdict(list)

    for prop in odds_props:
        canon = _resolve_name(prop.player_name, canonical_pool, corrections)
        key = (canon, prop.stat_type, prop.line, prop.direction)
        odds_map[key].append((prop.book, prop.odds))

    # 3. Load previous snapshot for steam detection (last scrape)
    prev_snap_rows = await db.execute(
        select(OddsSnapshot)
        .where(OddsSnapshot.sport == sport)
        .order_by(desc(OddsSnapshot.snapshot_at))
        .limit(5000)
    )
    prev_by_key: dict[OddsKey, list[dict]] = defaultdict(list)
    for row in prev_snap_rows.scalars():
        k = (row.player_name, row.stat_type, row.line_score, row.direction)
        prev_by_key[k].append({"book": row.book, "direction": row.direction, "odds": row.odds})

    now = datetime.utcnow()
    results: list[dict] = []
    stat_fn = _get_stat_fn(sport)

    seen: set[tuple] = set()

    for proj in pp_lines:
        canon = _resolve_name(proj.player_name, canonical_pool, corrections)

        for direction in ("Over", "Under"):
            # Check both half-line and ±0.5 (PrizePicks whole vs half lines)
            candidate_lines = {proj.line_score, proj.line_score - 0.5, proj.line_score + 0.5}

            for line in candidate_lines:
                key = (canon, proj.stat_type, line, direction)
                if key in seen:
                    continue

                book_odds = odds_map.get(key, [])
                if not book_odds:
                    continue
                seen.add(key)

                # --- Shin-devigged weighted market probability ---
                over_key  = (canon, proj.stat_type, line, "Over")
                under_key = (canon, proj.stat_type, line, "Under")
                over_by_book  = dict(odds_map.get(over_key, []))
                under_by_book = dict(odds_map.get(under_key, []))

                weighted_prob = 0.0
                weight_sum    = 0.0
                for book in set(over_by_book) & set(under_by_book):
                    p = devig_book_odds(over_by_book[book], under_by_book[book])
                    if p is None:
                        continue
                    p_dir = p[0] if direction == "Over" else p[1]
                    w = BOOK_WEIGHTS.get(book, 1.0) if book not in PRIVATE_BOOKS else 0.5
                    weighted_prob += p_dir * w
                    weight_sum    += w

                if weight_sum == 0:
                    continue
                market_prob = weighted_prob / weight_sum

                # --- Historical hit rate ---
                logs = await _get_game_logs(canon, sport, db)
                hist_prob, sample_n = compute_hit_rate(logs, proj.stat_type, line, direction, stat_fn)
                roll_rates = rolling_window_rates(logs, proj.stat_type, line, direction, stat_fn)
                min_flag = _minutes_flag(logs, sport)

                # --- Steam signal ---
                curr_snaps = [
                    {"book": b, "direction": d, "odds": o}
                    for (nm, st, ln, d), book_list in odds_map.items()
                    if nm == canon and st == proj.stat_type and ln == line
                    for b, o in book_list
                ]
                prev_snaps = prev_by_key.get((canon, proj.stat_type, line, direction), [])
                movement = compute_movement_signal(prev_snaps, curr_snaps)

                # --- Blend ---
                ev = EVResult(market_prob, hist_prob, movement, direction, sample_n)

                # --- Persist snapshots ---
                for book, odds_val in book_odds:
                    db.add(OddsSnapshot(
                        player_name=canon, stat_type=proj.stat_type,
                        line_score=line, sport=sport,
                        direction=direction, odds=odds_val, book=book,
                        snapshot_at=now,
                    ))

                # --- Persist EV result ---
                ev_row = EVResultModel(
                    player_name=canon, stat_type=proj.stat_type,
                    line_score=line, sport=sport, direction=direction,
                    market_prob=ev.market_prob,
                    historical_prob=ev.historical_prob,
                    movement_signal=ev.movement_signal,
                    blended_prob=ev.blended_prob,
                    ev_pct=ev.ev_pct,
                    ev_std=ev.ev_std,
                    kelly_2pick=ev.kelly_2pick,
                    kelly_3pick=ev.kelly_3pick,
                    kelly_4pick=ev.kelly_4pick,
                    sample_n=sample_n,
                    minutes_flag=int(min_flag),
                    computed_at=now,
                )
                db.add(ev_row)

                # --- Persist prediction for ML training ---
                db.add(Prediction(
                    player_name=canon, stat_type=proj.stat_type,
                    line_score=line, sport=sport, direction=direction,
                    predicted_prob=ev.blended_prob,
                    market_prob=ev.market_prob,
                    historical_prob=ev.historical_prob,
                    movement_signal=ev.movement_signal,
                    game_date=proj.game_date,
                    predicted_at=now,
                ))

                results.append({
                    "player_name":     canon,
                    "stat_type":       proj.stat_type,
                    "line_score":      line,
                    "sport":           sport,
                    "direction":       direction,
                    "game_date":       proj.game_date,
                    "market_prob":     round(ev.market_prob, 4),
                    "historical_prob": round(ev.historical_prob, 4),
                    "movement_signal": round(ev.movement_signal, 4),
                    "blended_prob":    round(ev.blended_prob, 4),
                    "ev_pct":          round(ev.ev_pct * 100, 2),
                    "ev_std":          round(ev.ev_std * 100, 2),
                    "kelly_2pick":     round(ev.kelly_2pick * 100, 2),
                    "kelly_3pick":     round(ev.kelly_3pick * 100, 2),
                    "kelly_4pick":     round(ev.kelly_4pick * 100, 2),
                    "sample_n":        sample_n,
                    "minutes_flag":    min_flag,
                    "roll_l5":         round(roll_rates.get(5, 0) * 100, 1),
                    "roll_l10":        round(roll_rates.get(10, 0) * 100, 1),
                    "roll_l20":        round(roll_rates.get(20, 0) * 100, 1),
                    "breakeven_2pick": round(breakeven(2) * 100, 2),
                    "breakeven_3pick": round(breakeven(3) * 100, 2),
                    "breakeven_4pick": round(breakeven(4) * 100, 2),
                })

    await db.commit()
    return sorted(results, key=lambda x: x["ev_pct"], reverse=True)
