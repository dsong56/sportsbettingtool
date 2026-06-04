"""
Prop data endpoints.
GET /api/props              → latest EV results (filterable)
GET /api/props/history      → odds snapshots for sparkline
GET /api/props/breakevens   → current breakeven probabilities per tier
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.db.models import EVResult, OddsSnapshot
from backend.ev.blend import breakeven
from backend.config import POWER_PLAY_MULTIPLIERS

router = APIRouter(prefix="/api/props")


@router.get("")
async def get_props(
    sport:     str | None = Query(None),
    stat_type: str | None = Query(None),
    direction: str | None = Query(None),
    min_ev:    float      = Query(-999.0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(EVResult).order_by(desc(EVResult.ev_pct), desc(EVResult.computed_at))
    if sport:
        stmt = stmt.where(EVResult.sport == sport.upper())
    if stat_type:
        stmt = stmt.where(EVResult.stat_type == stat_type)
    if direction:
        stmt = stmt.where(EVResult.direction == direction)

    rows = (await db.execute(stmt)).scalars().all()

    # Deduplicate: keep most recent result per (player, stat, line, direction)
    seen: set[tuple] = set()
    results = []
    for r in rows:
        key = (r.player_name, r.stat_type, r.line_score, r.direction, r.sport)
        if key in seen:
            continue
        seen.add(key)
        ev_pct = r.ev_pct or 0
        if ev_pct < min_ev:
            continue
        results.append({
            "player_name":     r.player_name,
            "stat_type":       r.stat_type,
            "line_score":      r.line_score,
            "sport":           r.sport,
            "direction":       r.direction,
            "odds_type":       r.odds_type or "standard",
            "matchup":         r.matchup or "",
            "market_prob":     r.market_prob,
            "historical_prob": r.historical_prob,
            "movement_signal": r.movement_signal,
            "blended_prob":    r.blended_prob,
            "ev_pct":          r.ev_pct,
            "ev_std":          r.ev_std,
            "kelly_2pick":     r.kelly_2pick,
            "kelly_3pick":     r.kelly_3pick,
            "kelly_4pick":     r.kelly_4pick,
            "sample_n":        r.sample_n,
            "minutes_flag":    r.minutes_flag,
            "computed_at":     r.computed_at,
        })

    return results


@router.get("/history")
async def get_odds_history(
    player_name: str,
    stat_type:   str,
    line_score:  float,
    sport:       str,
    direction:   str = "Over",
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(OddsSnapshot)
        .where(
            OddsSnapshot.player_name == player_name,
            OddsSnapshot.stat_type   == stat_type,
            OddsSnapshot.line_score  == line_score,
            OddsSnapshot.sport       == sport.upper(),
            OddsSnapshot.direction   == direction,
        )
        .order_by(OddsSnapshot.snapshot_at)
    )
    rows = (await db.execute(stmt)).scalars().all()

    # Aggregate by snapshot time: weighted average odds per timestamp
    from collections import defaultdict
    from backend.config import BOOK_WEIGHTS
    by_time: dict = defaultdict(list)
    for r in rows:
        ts = r.snapshot_at.strftime("%Y-%m-%dT%H:%M")
        by_time[ts].append((r.odds, BOOK_WEIGHTS.get(r.book, 1.0)))

    history = []
    for ts, items in sorted(by_time.items()):
        total_w = sum(w for _, w in items)
        wavg_odds = sum(o * w for o, w in items) / total_w if total_w else 0
        history.append({"timestamp": ts, "avg_odds": round(wavg_odds, 1)})

    return history


@router.get("/breakevens")
async def get_breakevens():
    return {
        str(n): round(breakeven(n) * 100, 2)
        for n in POWER_PLAY_MULTIPLIERS
    }
