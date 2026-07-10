"""
Bet tracking endpoints.
POST /api/bets  → log a bet, snapshotting EV/prob from the latest matching EVResult
GET  /api/bets  → list logged bets (open + settled) for the portfolio page
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.db.models import BetLog, EVResult

router = APIRouter(prefix="/api/bets")


class BetIn(BaseModel):
    player_name: str
    stat_type:   str
    line_score:  float
    sport:       str
    direction:   str = Field(pattern="^(Over|Under)$")
    pick_count:  int = Field(ge=2, le=4)
    stake_pct:   float = Field(gt=0, le=100)


def _serialize(b: BetLog) -> dict:
    return {
        "id":                    b.id,
        "player_name":           b.player_name,
        "stat_type":             b.stat_type,
        "line_score":            b.line_score,
        "sport":                 b.sport,
        "direction":             b.direction,
        "odds_type":             b.odds_type or "standard",
        "pick_count":            b.pick_count,
        "stake_pct":             b.stake_pct,
        "game_date":             b.game_date,
        "ev_pct_at_entry":       b.ev_pct_at_entry,
        "blended_prob_at_entry": b.blended_prob_at_entry,
        "actual_result":         b.actual_result,
        "settled_at":            b.settled_at,
        "created_at":            b.created_at,
    }


@router.post("", status_code=201)
async def log_bet(body: BetIn, db: AsyncSession = Depends(get_db)):
    sport = body.sport.upper()

    # Snapshot entry EV from the most recent matching EVResult
    ev_row = (await db.execute(
        select(EVResult)
        .where(
            EVResult.player_name == body.player_name,
            EVResult.stat_type   == body.stat_type,
            EVResult.line_score  == body.line_score,
            EVResult.sport       == sport,
            EVResult.direction   == body.direction,
        )
        .order_by(desc(EVResult.computed_at))
        .limit(1)
    )).scalar_one_or_none()

    if ev_row is None:
        raise HTTPException(
            404,
            "No EV result found for this prop — refresh the sport first, "
            "then log the bet from a live row.",
        )

    bet = BetLog(
        player_name=body.player_name,
        stat_type=body.stat_type,
        line_score=body.line_score,
        sport=sport,
        direction=body.direction,
        odds_type=ev_row.odds_type or "standard",
        pick_count=body.pick_count,
        stake_pct=body.stake_pct,
        game_date=ev_row.game_date,
        ev_pct_at_entry=ev_row.ev_pct,
        blended_prob_at_entry=ev_row.blended_prob,
    )
    db.add(bet)
    await db.commit()
    await db.refresh(bet)
    return _serialize(bet)


@router.get("")
async def list_bets(
    status: str = Query("all", pattern="^(all|open|settled)$"),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(BetLog).order_by(desc(BetLog.created_at))
    if status == "open":
        stmt = stmt.where(BetLog.actual_result == None)  # noqa: E711
    elif status == "settled":
        stmt = stmt.where(BetLog.actual_result != None)  # noqa: E711
    rows = (await db.execute(stmt)).scalars().all()
    return [_serialize(b) for b in rows]
