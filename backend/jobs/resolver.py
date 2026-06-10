"""
Nightly auto-resolution job.

1. Resolves ML training predictions (marks over/under from stats APIs)
2. Settles pending paper bets once all picks in a parlay have outcomes
"""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import AsyncSessionLocal
from backend.db.models import Prediction, PaperBet, PaperSettings

log = logging.getLogger(__name__)

# Flex Play payout tables — mirror what's in ParlayOptimizer.tsx
FLEX_PAYOUTS: dict[int, dict[int, float]] = {
    3: {3: 2.5,  2: 1.25},
    4: {4: 5.0,  3: 1.5},
    5: {5: 10.0, 4: 2.0, 3: 0.4},
    6: {6: 25.0, 5: 2.0, 4: 0.4},
}

POWER_MULTIPLIERS: dict[int, float] = {2: 3, 3: 5, 4: 10, 5: 20, 6: 25}


# ── prediction resolution ─────────────────────────────────────────────────────

async def _resolve_predictions(db: AsyncSession):
    from backend.stats import nba, nhl, mlb

    today = datetime.utcnow().date().isoformat()
    stmt = (
        select(Prediction)
        .where(Prediction.actual_result == None, Prediction.game_date < today)  # noqa: E711
    )
    pending = (await db.execute(stmt)).scalars().all()
    log.info("Resolver: %d unresolved predictions", len(pending))

    fetchers   = {"NBA": nba.fetch_game_logs, "NHL": nhl.fetch_game_logs, "MLB": mlb.fetch_game_logs}
    extractors = {"NBA": nba._extract_stat,   "NHL": nhl.get_stat_value,  "MLB": mlb.get_stat_value}

    for pred in pending:
        try:
            fetch = fetchers.get(pred.sport)
            extract = extractors.get(pred.sport)
            if not fetch or not extract:
                continue
            logs = await fetch(pred.player_name, n_games=5)
            match = [g for g in logs if g["game_date"] == pred.game_date]
            if not match:
                continue
            val = extract(match[0], pred.stat_type)
            if val is None:
                continue
            pred.actual_result = "over" if val > pred.line_score else "under"
            pred.resolved_at   = datetime.utcnow()
        except Exception as exc:
            log.warning("Failed to resolve prediction %d: %s", pred.id, exc)

    await db.commit()


# ── paper bet settlement ──────────────────────────────────────────────────────

def _pick_result(pick: dict, resolved: dict[tuple, str]) -> str | None:
    """Look up resolved outcome for a single pick. Returns 'over'|'under'|None."""
    key = (pick["player_name"], pick["stat_type"],
           pick["line_score"], pick["direction"], pick["sport"])
    return resolved.get(key)


async def _settle_paper_bets(db: AsyncSession):
    # Build a lookup of all resolved predictions
    resolved_rows = (await db.execute(
        select(Prediction).where(Prediction.actual_result != None)  # noqa: E711
    )).scalars().all()

    resolved: dict[tuple, str] = {}
    for p in resolved_rows:
        key = (p.player_name, p.stat_type, p.line_score, p.direction, p.sport)
        resolved[key] = p.actual_result  # 'over' | 'under'

    pending_bets = (await db.execute(
        select(PaperBet).where(PaperBet.status == "pending")
    )).scalars().all()

    if not pending_bets:
        return

    settings = (await db.execute(select(PaperSettings).limit(1))).scalars().first()
    if not settings:
        return

    for bet in pending_bets:
        picks = bet.picks  # list of dicts
        outcomes = [_pick_result(p, resolved) for p in picks]

        # Only settle when all picks have a known outcome
        if any(o is None for o in outcomes):
            continue

        # Count hits — a pick "hits" when the outcome matches the direction
        hits = sum(
            1 for pick, outcome in zip(picks, outcomes)
            if outcome == pick["direction"].lower()
        )

        if bet.play_type == "power":
            won = hits == bet.n_picks
            actual_payout = bet.stake * bet.multiplier if won else 0.0
            status = "won" if won else "lost"
        else:
            # Flex — look up tiered payout
            flex_table = FLEX_PAYOUTS.get(bet.n_picks, {})
            payout_mult = flex_table.get(hits, 0.0)
            actual_payout = bet.stake * payout_mult
            if hits == bet.n_picks:
                status = "won"
            elif payout_mult > 0:
                status = "partial"
            else:
                status = "lost"

        profit_loss = round(actual_payout - bet.stake, 2)
        settings.current_bankroll = round(settings.current_bankroll + actual_payout, 2)
        settings.updated_at = datetime.utcnow()

        bet.status         = status
        bet.hits           = hits
        bet.actual_payout  = round(actual_payout, 2)
        bet.profit_loss    = profit_loss
        bet.bankroll_after = settings.current_bankroll
        bet.settled_at     = datetime.utcnow()

        log.info("Settled paper bet #%d %s %s-pick: %d/%d hits → %s ($%.2f)",
                 bet.id, bet.play_type, bet.n_picks, hits, bet.n_picks, status, profit_loss)

    await db.commit()


# ── main loop ─────────────────────────────────────────────────────────────────

async def _nightly_loop():
    while True:
        now = datetime.utcnow()
        next_run = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()
        log.info("Resolver sleeping %.0f seconds until %s UTC", wait_seconds, next_run.isoformat())
        await asyncio.sleep(wait_seconds)

        async with AsyncSessionLocal() as db:
            await _resolve_predictions(db)
            await _settle_paper_bets(db)


async def start_nightly_resolver() -> asyncio.Task:
    return asyncio.create_task(_nightly_loop())
