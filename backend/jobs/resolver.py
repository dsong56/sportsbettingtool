"""
Nightly auto-resolution job.

Runs once per day (at ~02:00 local time). For each unresolved Prediction
whose game_date is in the past, queries the appropriate stats API to find
the player's actual stat line and marks the prediction over/under accordingly.

This is what makes the ML layer trainable without manual outcome logging.
"""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import AsyncSessionLocal
from backend.db.models import Prediction

log = logging.getLogger(__name__)


async def _resolve_predictions(db: AsyncSession):
    from backend.stats import nba, nhl, mlb

    today = datetime.utcnow().date().isoformat()

    # Only attempt to resolve predictions for games that should be finished
    stmt = (
        select(Prediction)
        .where(
            Prediction.actual_result == None,  # noqa: E711
            Prediction.game_date < today,
        )
    )
    pending = (await db.execute(stmt)).scalars().all()
    log.info("Resolver: %d unresolved predictions to attempt", len(pending))

    stat_fetchers = {"NBA": nba.fetch_game_logs, "NHL": nhl.fetch_game_logs, "MLB": mlb.fetch_game_logs}
    stat_extractors = {"NBA": nba._extract_stat, "NHL": nhl.get_stat_value, "MLB": mlb.get_stat_value}

    for pred in pending:
        try:
            fetcher = stat_fetchers.get(pred.sport)
            extractor = stat_extractors.get(pred.sport)
            if not fetcher or not extractor:
                continue

            logs = await fetcher(pred.player_name, n_games=5)
            # Find the log entry matching game_date
            matching = [g for g in logs if g["game_date"] == pred.game_date]
            if not matching:
                continue

            val = extractor(matching[0], pred.stat_type)
            if val is None:
                continue

            if pred.direction == "Over":
                result = "over" if val > pred.line_score else "under"
            else:
                result = "under" if val < pred.line_score else "over"

            pred.actual_result = result
            pred.resolved_at   = datetime.utcnow()
            log.info("Resolved %s %s %s %.1f → %s (actual: %.1f)",
                     pred.player_name, pred.stat_type, pred.direction, pred.line_score, result, val)
        except Exception as exc:
            log.warning("Failed to resolve prediction %d: %s", pred.id, exc)

    await db.commit()


async def _nightly_loop():
    while True:
        now = datetime.utcnow()
        # Schedule next run at 07:00 UTC (02:00 Central)
        next_run = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()
        log.info("Resolver sleeping %.0f seconds until %s UTC", wait_seconds, next_run.isoformat())
        await asyncio.sleep(wait_seconds)

        async with AsyncSessionLocal() as db:
            await _resolve_predictions(db)


async def start_nightly_resolver() -> asyncio.Task:
    return asyncio.create_task(_nightly_loop())
