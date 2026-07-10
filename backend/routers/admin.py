"""
Admin endpoints.
POST /api/admin/corrections         → add / update a name correction
GET  /api/admin/corrections         → list all corrections
DELETE /api/admin/corrections/{id}  → remove a correction
POST /api/admin/outcomes/{pred_id}  → manually resolve a prediction outcome
POST /api/admin/train               → train the ML model on resolved predictions
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
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
    from backend.jobs.resolver import settle_bet_logs_for_prediction

    result = body.actual_result.lower()
    if result not in ("over", "under"):
        raise HTTPException(422, "actual_result must be 'over' or 'under'")
    pred = await db.get(Prediction, pred_id)
    if not pred:
        raise HTTPException(404, "Prediction not found")
    pred.actual_result = result
    pred.resolved_at   = datetime.utcnow()
    settled = await settle_bet_logs_for_prediction(db, pred)
    await db.commit()
    return {"id": pred_id, "actual_result": pred.actual_result, "bets_settled": settled}


@router.post("/train")
async def train_ml_model(db: AsyncSession = Depends(get_db)):
    """
    Train the ML probability model on all resolved predictions.
    Requires at least settings.ml_min_resolved_predictions resolved rows.
    On success the model is persisted to disk and ML mode is switched on for
    this process; the pipeline also auto-detects the model file on restart.
    """
    from backend.ev import ml_model

    resolved = (await db.execute(
        select(Prediction).where(Prediction.actual_result != None)  # noqa: E711
    )).scalars().all()

    n = len(resolved)
    if n < settings.ml_min_resolved_predictions:
        raise HTTPException(
            400,
            f"Not enough resolved predictions to train: {n} < "
            f"{settings.ml_min_resolved_predictions}",
        )

    X: list[list[float]] = []
    y: list[int] = []
    for p in resolved:
        feats = ml_model.build_features(
            p.market_prob, p.historical_prob, p.movement_signal,
            p.sample_n or 0, p.sport, p.direction,
        )
        if feats is None:
            continue
        X.append(feats)
        y.append(1 if p.actual_result == p.direction.lower() else 0)

    if len(set(y)) < 2:
        raise HTTPException(400, "Training data has only one outcome class — cannot train")

    # sklearn is synchronous; keep the event loop free
    accuracy, n_samples = await asyncio.to_thread(ml_model.train_model, X, y)

    settings.use_ml_model = True
    return {"trained": True, "n_samples": n_samples, "accuracy": round(accuracy, 4)}
