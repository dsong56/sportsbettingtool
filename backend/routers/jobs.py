"""
Job management endpoints.
POST /api/refresh/{sport}  → triggers a scrape pipeline, returns job_id
GET  /api/jobs/{job_id}    → poll job status
"""
import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.db.models import ScrapeJob
from backend.ev.pipeline import run_pipeline
from backend.config import LEAGUE_IDS

router = APIRouter(prefix="/api")


async def _run_job(job_id: str, sport: str):
    from backend.db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        job = await db.get(ScrapeJob, job_id)
        if not job:
            return
        job.status = "running"
        job.started_at = datetime.utcnow()
        await db.commit()
        try:
            await run_pipeline(sport, db)
            job.status = "done"
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
        finally:
            job.finished_at = datetime.utcnow()
            await db.commit()


@router.post("/refresh/{sport}")
async def refresh_sport(
    sport: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    sport = sport.upper()
    if sport not in LEAGUE_IDS:
        raise HTTPException(400, f"Unsupported sport. Choose from: {list(LEAGUE_IDS)}")

    job_id = str(uuid.uuid4())
    job = ScrapeJob(id=job_id, sport=sport, status="pending", created_at=datetime.utcnow())
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
