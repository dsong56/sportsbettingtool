"""
Sportsbook mode endpoints.
GET /api/sportsbook        → latest per-book lines scored vs consensus (filterable)
GET /api/sportsbook/books  → distinct books available, for the filter dropdown
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.db.models import SportsbookLine

router = APIRouter(prefix="/api/sportsbook")


def _prob_to_american(p: float) -> int:
    """Fair (no-vig) American odds implied by a probability."""
    p = min(max(p, 0.01), 0.99)
    if p >= 0.5:
        return -round(p / (1 - p) * 100)
    return round((1 - p) / p * 100)


@router.get("")
async def get_sportsbook_lines(
    sport:     str | None = Query(None),
    book:      str | None = Query(None),
    stat_type: str | None = Query(None),
    direction: str | None = Query(None),
    min_ev:    float      = Query(-999.0),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(SportsbookLine)
        .where(SportsbookLine.ev_pct >= min_ev)
        .order_by(desc(SportsbookLine.ev_pct), desc(SportsbookLine.computed_at))
    )
    if sport:
        stmt = stmt.where(SportsbookLine.sport == sport.upper())
    if book:
        stmt = stmt.where(SportsbookLine.book == book)
    if stat_type:
        stmt = stmt.where(SportsbookLine.stat_type == stat_type)
    if direction:
        stmt = stmt.where(SportsbookLine.direction == direction)

    rows = (await db.execute(stmt)).scalars().all()

    # Keep only the most recent row per (player, stat, line, direction, book)
    seen: set[tuple] = set()
    results = []
    for r in rows:
        key = (r.player_name, r.stat_type, r.line_score, r.direction, r.book)
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "player_name":       r.player_name,
            "stat_type":         r.stat_type,
            "line_score":        r.line_score,
            "sport":             r.sport,
            "direction":         r.direction,
            "book":              r.book,
            "odds":              r.odds,
            "fair_odds":         _prob_to_american(r.consensus_prob or 0.5),
            "consensus_prob":    r.consensus_prob,
            "historical_prob":   r.historical_prob,
            "ev_pct":            r.ev_pct,
            "kelly_pct":         r.kelly_pct,
            "n_books_consensus": r.n_books_consensus,
            "computed_at":       r.computed_at,
        })

    return sorted(results, key=lambda x: x["ev_pct"] or 0, reverse=True)


@router.get("/books")
async def list_books(
    sport: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SportsbookLine.book).distinct().order_by(SportsbookLine.book)
    if sport:
        stmt = stmt.where(SportsbookLine.sport == sport.upper())
    return [b for (b,) in (await db.execute(stmt)).all()]
