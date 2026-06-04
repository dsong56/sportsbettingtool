"""
Job management endpoints.
POST /api/refresh/{sport}  → triggers a scrape pipeline, returns job_id
GET  /api/jobs/{job_id}    → poll job status
"""
import uuid
import httpx
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.db.models import ScrapeJob
from backend.ev.pipeline import run_pipeline
from backend.config import settings

router = APIRouter(prefix="/api")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _friendly_error(exc: Exception) -> str:
    msg = str(exc)
    if isinstance(exc, httpx.HTTPStatusError):
        url = exc.request.url.host
        code = exc.response.status_code
        if "prizepicks" in url:
            return f"PrizePicks API error ({code}) — their API may be down or rate-limiting"
        if "the-odds-api" in url:
            if code == 401:
                return "Odds API error (401) — check your ODDS_API_KEY in .env"
            if code == 422:
                return "Odds API error (422) — quota exceeded, check usage at the-odds-api.com"
            return f"Odds API error ({code})"
        if "balldontlie" in url:
            if code == 401:
                return "BallDontLie API error (401) — check your BALLDONTLIE_API_KEY in .env"
            return f"BallDontLie API error ({code})"
        return f"HTTP {code} from {url}"
    if isinstance(exc, httpx.ConnectError):
        return f"Network error — could not connect to {exc}"
    if isinstance(exc, httpx.TimeoutException):
        return "Request timed out — API may be slow, try again"
    if "ODDS_API_KEY" in msg or "odds_api_key" in msg:
        return "Odds API key missing — add ODDS_API_KEY to your .env file"
    return msg


async def _run_job(job_id: str, sport: str):
    from backend.db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        job = await db.get(ScrapeJob, job_id)
        if not job:
            return
        job.status = "running"
        job.started_at = _now()
        await db.commit()
        try:
            await run_pipeline(sport, db)
            job.status = "done"
        except Exception as exc:
            job.status = "failed"
            job.error = _friendly_error(exc)
            # Roll back any broken transaction before updating job status
            await db.rollback()
        finally:
            job.finished_at = _now()
            await db.commit()


@router.post("/refresh/{sport}")
async def refresh_sport(
    sport: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    sport = sport.upper()
    if sport not in settings.league_ids:
        raise HTTPException(400, f"Unsupported sport. Choose from: {list(settings.league_ids)}")

    job_id = str(uuid.uuid4())
    job = ScrapeJob(id=job_id, sport=sport, status="pending", created_at=_now())
    db.add(job)
    await db.commit()

    background_tasks.add_task(_run_job, job_id, sport)
    return {"job_id": job_id, "status": "pending"}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "job_id":      job.id,
        "sport":       job.sport,
        "status":      job.status,
        "error":       job.error,
        "started_at":  job.started_at,
        "finished_at": job.finished_at,
    }
