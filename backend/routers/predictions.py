"""
Prediction analytics endpoints.
GET /api/predictions/summary     → calibration + accuracy stats for the Calibration page
GET /api/predictions/unresolved  → past-dated predictions awaiting an outcome
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.database import get_db
from backend.db.models import Prediction
from backend.ev.ml_model import ml_enabled, model_path

router = APIRouter(prefix="/api/predictions")


def _hit(pred: Prediction) -> int:
    return 1 if pred.actual_result == pred.direction.lower() else 0


def _pearson(xs: list[float], ys: list[int]) -> float | None:
    """Pearson r, or None when the sample is too small/degenerate."""
    if len(xs) < 3 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    from scipy.stats import pearsonr
    r = float(pearsonr(xs, ys)[0])
    return None if r != r else round(r, 4)  # NaN guard


@router.get("/summary")
async def predictions_summary(db: AsyncSession = Depends(get_db)):
    resolved = (await db.execute(
        select(Prediction).where(Prediction.actual_result != None)  # noqa: E711
    )).scalars().all()

    total = len(resolved)
    hits = [_hit(p) for p in resolved]
    win_rate = sum(hits) / total if total else 0.0
    brier = (
        sum((p.predicted_prob - h) ** 2 for p, h in zip(resolved, hits)) / total
        if total else 0.0
    )

    # --- Calibration buckets (predicted prob rounded to 0.05) ---
    buckets: dict[float, list[tuple[float, int]]] = {}
    for p, h in zip(resolved, hits):
        b = round(round(p.predicted_prob / 0.05) * 0.05, 2)
        buckets.setdefault(b, []).append((p.predicted_prob, h))
    calibration_buckets = [
        {
            "prob_bin":      b,
            "predicted_avg": round(sum(pp for pp, _ in items) / len(items), 4),
            "actual_rate":   round(sum(hh for _, hh in items) / len(items), 4),
            "count":         len(items),
        }
        for b, items in sorted(buckets.items())
    ]

    # --- Signal attribution: point-biserial Pearson r of each signal vs hit.
    # Computed only over rows where that signal is present, since movement in
    # particular is missing/zero for most rows; n is reported alongside r so
    # the frontend can qualify weak-sample bars. ---
    def attribution(getter) -> dict:
        pairs = [(getter(p), h) for p, h in zip(resolved, hits) if getter(p) is not None]
        xs = [x for x, _ in pairs]
        ys = [y for _, y in pairs]
        return {"r": _pearson(xs, ys), "n": len(pairs)}

    market_attr = attribution(lambda p: p.market_prob)
    hist_attr = attribution(lambda p: p.historical_prob)
    move_attr = attribution(lambda p: p.movement_signal)

    # --- 30-day rolling win rate, one point per game_date with resolutions ---
    by_date: dict[str, list[int]] = {}
    for p, h in zip(resolved, hits):
        d = p.game_date or (p.resolved_at.date().isoformat() if p.resolved_at else None)
        if d:
            by_date.setdefault(d, []).append(h)

    rolling_accuracy = []
    dates = sorted(by_date)
    for d in dates:
        try:
            window_start = (datetime.fromisoformat(d) - timedelta(days=30)).date().isoformat()
        except ValueError:
            continue
        window = [h for wd in dates if window_start < wd <= d for h in by_date[wd]]
        if window:
            rolling_accuracy.append({
                "date":     d,
                "win_rate": round(sum(window) / len(window), 4),
                "count":    len(window),
            })

    return {
        "total_resolved": total,
        "win_rate":       round(win_rate, 4),
        "brier_score":    round(brier, 4),
        "calibration_buckets": calibration_buckets,
        "signal_attribution": {
            "market_correlation":     market_attr["r"],
            "market_n":               market_attr["n"],
            "historical_correlation": hist_attr["r"],
            "historical_n":           hist_attr["n"],
            "movement_correlation":   move_attr["r"],
            "movement_n":             move_attr["n"],
        },
        "rolling_accuracy": rolling_accuracy,
        "ml": {
            "active":       ml_enabled(),
            "model_exists": model_path().exists(),
            "min_required": settings.ml_min_resolved_predictions,
        },
    }


@router.get("/unresolved")
async def unresolved_predictions(
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    today = datetime.utcnow().date().isoformat()
    rows = (await db.execute(
        select(Prediction)
        .where(
            Prediction.actual_result == None,  # noqa: E711
            Prediction.game_date < today,
        )
        .order_by(desc(Prediction.game_date), Prediction.player_name)
        .limit(limit)
    )).scalars().all()

    return [
        {
            "id":             p.id,
            "player_name":    p.player_name,
            "stat_type":      p.stat_type,
            "line_score":     p.line_score,
            "sport":          p.sport,
            "direction":      p.direction,
            "game_date":      p.game_date,
            "predicted_prob": p.predicted_prob,
        }
        for p in rows
    ]
