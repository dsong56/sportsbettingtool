"""
Admin endpoints.
POST /api/admin/corrections         → add / update a name correction
GET  /api/admin/corrections         → list all corrections
DELETE /api/admin/corrections/{id}  → remove a correction
POST /api/admin/outcomes/{pred_id}  → manually resolve a prediction outcome
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.db.models import NameCorrection, Prediction

router = APIRouter(prefix="/api/admin")


class CorrectionIn(BaseModel):
    source:         str
    raw_name:       str
    canonical_name: str
    sport:          str


class OutcomeIn(BaseModel):
    actual_result: str  # 'over' | 'under'


@router.get("/corrections")
async def list_corrections(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(NameCorrection))).scalars().all()
    return [{"id": r.id, "source": r.source, "raw_name": r.raw_name,
             "canonical_name": r.canonical_name, "sport": r.sport} for r in rows]


@router.post("/corrections", status_code=201)
async def add_correction(body: CorrectionIn, db: AsyncSession = Depends(get_db)):
    row = NameCorrection(**body.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"id": row.id}


@router.delete("/corrections/{correction_id}")
async def delete_correction(correction_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(NameCorrection, correction_id)
    if not row:
        raise HTTPException(404, "Correction not found")
    await db.delete(row)
    await db.commit()
    return {"deleted": correction_id}


@router.post("/outcomes/{pred_id}")
async def resolve_outcome(pred_id: int, body: OutcomeIn, db: AsyncSession = Depends(get_db)):
    from datetime import datetime
    pred = await db.get(Prediction, pred_id)
    if not pred:
        raise HTTPException(404, "Prediction not found")
    pred.actual_result = body.actual_result.lower()
    pred.resolved_at   = datetime.utcnow()
    await db.commit()
    return {"id": pred_id, "actual_result": pred.actual_result}
