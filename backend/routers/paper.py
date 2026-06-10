"""
Paper trading endpoints.

POST   /api/paper/bets          — place a parlay bet
GET    /api/paper/bets          — list all bets (filterable by status)
DELETE /api/paper/bets/{id}     — cancel a pending bet
GET    /api/paper/summary       — bankroll, P&L, win rate, bankroll history
POST   /api/paper/reset         — reset bankroll to starting amount
PUT    /api/paper/settings      — update starting bankroll
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.db.models import PaperBet, PaperSettings

router = APIRouter(prefix="/api/paper")

DEFAULT_BANKROLL = 100.0


# ── helpers ──────────────────────────────────────────────────────────────────

async def _get_or_create_settings(db: AsyncSession) -> PaperSettings:
    result = await db.execute(select(PaperSettings).limit(1))
    row = result.scalars().first()
    if not row:
        row = PaperSettings(
            starting_bankroll=DEFAULT_BANKROLL,
            current_bankroll=DEFAULT_BANKROLL,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


def _bet_out(b: PaperBet) -> dict:
    return {
        "id":               b.id,
        "play_type":        b.play_type,
        "n_picks":          b.n_picks,
        "picks":            b.picks,
        "stake":            b.stake,
        "multiplier":       b.multiplier,
        "potential_payout": b.potential_payout,
        "joint_prob":       b.joint_prob,
        "ev_pct":           b.ev_pct,
        "placed_at":        b.placed_at,
        "status":           b.status,
        "hits":             b.hits,
        "actual_payout":    b.actual_payout,
        "profit_loss":      b.profit_loss,
        "bankroll_after":   b.bankroll_after,
        "settled_at":       b.settled_at,
    }


# ── schemas ───────────────────────────────────────────────────────────────────

class PickIn(BaseModel):
    player_name:  str
    stat_type:    str
    line_score:   float
    direction:    str
    sport:        str
    odds_type:    str
    blended_prob: float
    game_date:    str = ""   # not stored in ev_results — informational only
    matchup:      str = ""

class PlaceBetIn(BaseModel):
    play_type:   str          # 'power' | 'flex'
    n_picks:     int
    picks:       list[PickIn]
    stake:       float
    multiplier:  float        # max payout multiplier
    joint_prob:  float
    ev_pct:      float

class UpdateSettingsIn(BaseModel):
    starting_bankroll: float


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/bets", status_code=201)
async def place_bet(body: PlaceBetIn, db: AsyncSession = Depends(get_db)):
    settings = await _get_or_create_settings(db)

    if body.stake > settings.current_bankroll:
        raise HTTPException(400, f"Stake ${body.stake:.2f} exceeds bankroll ${settings.current_bankroll:.2f}")
    if body.stake <= 0:
        raise HTTPException(400, "Stake must be positive")

    # Deduct stake from bankroll immediately (it's at risk)
    settings.current_bankroll = round(settings.current_bankroll - body.stake, 2)
    settings.updated_at = datetime.utcnow()

    bet = PaperBet(
        play_type=body.play_type,
        n_picks=body.n_picks,
        picks=[p.model_dump() for p in body.picks],
        stake=body.stake,
        multiplier=body.multiplier,
        potential_payout=round(body.stake * body.multiplier, 2),
        joint_prob=body.joint_prob,
        ev_pct=body.ev_pct,
        placed_at=datetime.utcnow(),
        status="pending",
    )
    db.add(bet)
    await db.commit()
    await db.refresh(bet)
    return {**_bet_out(bet), "current_bankroll": settings.current_bankroll}


@router.get("/bets")
async def list_bets(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(PaperBet).order_by(desc(PaperBet.placed_at))
    if status:
        stmt = stmt.where(PaperBet.status == status)
    rows = (await db.execute(stmt)).scalars().all()
    return [_bet_out(b) for b in rows]


@router.delete("/bets/{bet_id}")
async def cancel_bet(bet_id: int, db: AsyncSession = Depends(get_db)):
    bet = await db.get(PaperBet, bet_id)
    if not bet:
        raise HTTPException(404, "Bet not found")
    if bet.status != "pending":
        raise HTTPException(400, "Only pending bets can be cancelled")

    # Refund stake
    settings = await _get_or_create_settings(db)
    settings.current_bankroll = round(settings.current_bankroll + bet.stake, 2)
    settings.updated_at = datetime.utcnow()

    bet.status = "cancelled"
    bet.settled_at = datetime.utcnow()
    bet.actual_payout = 0
    bet.profit_loss = -bet.stake  # effectively lost the opportunity cost
    await db.commit()
    return {"cancelled": bet_id, "refunded": bet.stake, "current_bankroll": settings.current_bankroll}


@router.get("/summary")
async def get_summary(db: AsyncSession = Depends(get_db)):
    settings = await _get_or_create_settings(db)
    all_bets = (await db.execute(select(PaperBet).order_by(PaperBet.placed_at))).scalars().all()

    settled = [b for b in all_bets if b.status in ("won", "lost", "partial")]
    pending = [b for b in all_bets if b.status == "pending"]

    total_staked = sum(b.stake for b in settled)
    total_payout = sum(b.actual_payout or 0 for b in settled)
    total_pl     = total_payout - total_staked
    roi          = (total_pl / total_staked * 100) if total_staked > 0 else 0

    wins   = sum(1 for b in settled if b.status == "won")
    losses = sum(1 for b in settled if b.status in ("lost", "partial"))

    # Bankroll history: starting point + one entry per settled bet
    history = [{"date": settings.updated_at.isoformat()[:10],
                "bankroll": settings.starting_bankroll}]
    running = settings.starting_bankroll
    for b in settled:
        if b.bankroll_after is not None:
            history.append({
                "date": (b.settled_at or b.placed_at).isoformat()[:10],
                "bankroll": b.bankroll_after,
            })

    by_type: dict[str, dict] = {}
    for b in settled:
        key = f"{b.play_type}_{b.n_picks}"
        if key not in by_type:
            by_type[key] = {"play_type": b.play_type, "n_picks": b.n_picks,
                            "bets": 0, "wins": 0, "staked": 0, "payout": 0}
        by_type[key]["bets"]   += 1
        by_type[key]["staked"] += b.stake
        by_type[key]["payout"] += b.actual_payout or 0
        if b.status == "won":
            by_type[key]["wins"] += 1

    return {
        "current_bankroll":  round(settings.current_bankroll, 2),
        "starting_bankroll": settings.starting_bankroll,
        "total_pl":          round(total_pl, 2),
        "roi_pct":           round(roi, 2),
        "total_bets":        len(settled),
        "wins":              wins,
        "losses":            losses,
        "win_rate":          round(wins / len(settled) * 100, 1) if settled else 0,
        "pending_bets":      len(pending),
        "pending_at_risk":   round(sum(b.stake for b in pending), 2),
        "bankroll_history":  history,
        "by_type":           list(by_type.values()),
    }


@router.post("/reset")
async def reset_bankroll(db: AsyncSession = Depends(get_db)):
    settings = await _get_or_create_settings(db)
    # Cancel all pending bets
    pending = (await db.execute(
        select(PaperBet).where(PaperBet.status == "pending")
    )).scalars().all()
    for b in pending:
        b.status = "cancelled"
        b.settled_at = datetime.utcnow()
        b.actual_payout = 0
        b.profit_loss = 0
    settings.current_bankroll = settings.starting_bankroll
    settings.updated_at = datetime.utcnow()
    await db.commit()
    return {"current_bankroll": settings.current_bankroll}


@router.put("/settings")
async def update_settings(body: UpdateSettingsIn, db: AsyncSession = Depends(get_db)):
    if body.starting_bankroll <= 0:
        raise HTTPException(400, "Starting bankroll must be positive")
    settings = await _get_or_create_settings(db)
    settings.starting_bankroll = body.starting_bankroll
    settings.current_bankroll  = body.starting_bankroll
    settings.updated_at = datetime.utcnow()
    await db.commit()
    return {"starting_bankroll": settings.starting_bankroll,
            "current_bankroll":  settings.current_bankroll}
