"""
Sportsbook best-lines endpoints.
POST /api/lines/refresh/{sport}  → trigger sportsbook pipeline
GET  /api/lines?sport=NBA        → latest best-line results
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.db.models import SportsbookLine, ScrapeJob
from backend.ev.sportsbook_pipeline import run_sportsbook_pipeline
from backend.config import settings

router = APIRouter(prefix="/api/lines")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _run_lines_job(job_id: str, sport: str):
    from backend.db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        job = await db.get(ScrapeJob, job_id)
        if not job:
            return
        job.status = "running"
        job.started_at = _now()
        await db.commit()
        try:
            await run_sportsbook_pipeline(sport, db)
            job.status = "done"
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            await db.rollback()
        finally:
            job.finished_at = _now()
            await db.commit()


@router.post("/refresh/{sport}")
async def refresh_lines(
    sport: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    sport = sport.upper()
    if sport not in settings.league_ids:
        raise HTTPException(400, f"Unsupported sport. Choose from: {list(settings.league_ids)}")

    job_id = str(uuid.uuid4())
    db.add(ScrapeJob(id=job_id, sport=sport, status="pending", created_at=_now()))
    await db.commit()

    background_tasks.add_task(_run_lines_job, job_id, sport)
    return {"job_id": job_id, "status": "pending"}


@router.get("")
async def get_lines(
    sport:     str | None = Query(None),
    stat_type: str | None = Query(None),
    direction: str | None = Query(None),
    book:      str | None = Query(None),
    min_ev:    float      = Query(-999.0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SportsbookLine).order_by(
        desc(SportsbookLine.ev_pct),
        desc(SportsbookLine.computed_at),
    )
    if sport:
        stmt = stmt.where(SportsbookLine.sport == sport.upper())
    if stat_type:
        stmt = stmt.where(SportsbookLine.stat_type == stat_type)
    if direction:
        stmt = stmt.where(SportsbookLine.direction == direction)
    if book:
        stmt = stmt.where(SportsbookLine.best_book.ilike(f"%{book}%"))

    rows = (await db.execute(stmt)).scalars().all()

    seen: set[tuple] = set()
    results = []
    for r in rows:
        key = (r.player_name, r.stat_type, r.line_score, r.direction, r.sport)
        if key in seen:
            continue
        seen.add(key)
        if (r.ev_pct or 0) < min_ev:
            continue
        results.append({
            "player_name": r.player_name,
            "stat_type":   r.stat_type,
            "line_score":  r.line_score,
            "sport":       r.sport,
            "direction":   r.direction,
            "best_book":   r.best_book,
            "best_odds":   r.best_odds,
            "market_prob": r.market_prob,
            "ev_pct":      r.ev_pct,
            "kelly_pct":   r.kelly_pct,
            "n_books":     r.n_books,
            "computed_at": r.computed_at,
        })
    return results
