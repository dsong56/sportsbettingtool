"""
ML probability model that replaces the hand-tuned blend once enough
resolved predictions exist to train on.

Feature vector (order matters — training and inference must match):
  [market_prob, historical_prob, movement_signal, sample_n,
   sport_encoded, direction_encoded]

Model choice: LogisticRegression for small samples; once the training set is
large enough, a CalibratedClassifierCV-wrapped GradientBoostingClassifier
(probabilities matter more than raw accuracy here, so calibration is required
before boosted trees are trustworthy).

Serialized with joblib to settings.ml_model_path (relative paths resolve to
the repo root so the model is found regardless of uvicorn's working directory).
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

import joblib

from backend.config import settings

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]

SPORT_ENCODING = {"NBA": 0, "NHL": 1, "MLB": 2, "NFL": 3}
DIRECTION_ENCODING = {"Over": 0, "Under": 1}

# Use GradientBoosting only when there's enough data to calibrate it honestly
_GBM_MIN_SAMPLES = 2000

_lock = threading.Lock()
_cached_model = None
_cached_mtime: float | None = None


def model_path() -> Path:
    p = Path(settings.ml_model_path)
    return p if p.is_absolute() else _REPO_ROOT / p


def ml_enabled() -> bool:
    """
    True when the ML model should replace the weighted blend.
    An explicit USE_ML_MODEL in the env/.env (or set at runtime by the train
    endpoint) always wins; otherwise the presence of a trained model file
    auto-enables it.
    """
    if "use_ml_model" in settings.model_fields_set:
        return settings.use_ml_model
    return model_path().exists()


def build_features(
    market_prob: float,
    historical_prob: float,
    movement_signal: float,
    sample_n: int,
    sport: str,
    direction: str,
) -> list[float] | None:
    """Returns None when the row can't be encoded (unknown sport/direction)."""
    sport_enc = SPORT_ENCODING.get(sport)
    dir_enc = DIRECTION_ENCODING.get(direction)
    if sport_enc is None or dir_enc is None:
        return None
    return [
        float(market_prob or 0.0),
        float(historical_prob or 0.0),
        float(movement_signal or 0.0),
        float(sample_n or 0),
        float(sport_enc),
        float(dir_enc),
    ]


def _load_model():
    """Load the pickled model, caching by file mtime. Returns None if missing/broken."""
    global _cached_model, _cached_mtime
    path = model_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    with _lock:
        if _cached_model is not None and _cached_mtime == mtime:
            return _cached_model
        try:
            _cached_model = joblib.load(path)
            _cached_mtime = mtime
        except Exception as exc:
            log.warning("Failed to load ML model from %s: %s", path, exc)
            _cached_model = None
            _cached_mtime = None
        return _cached_model


def predict_prob(features: list[float]) -> float | None:
    """
    Probability that the pick hits, from the trained model.
    Returns None (caller falls back to the weighted blend) when the model is
    unavailable or prediction fails for any reason.
    """
    model = _load_model()
    if model is None:
        return None
    try:
        prob = float(model.predict_proba([features])[0][1])
    except Exception as exc:
        log.warning("ML predict_prob failed, falling back to blend: %s", exc)
        return None
    return max(0.01, min(0.99, prob))


def train_model(X: list[list[float]], y: list[int]) -> tuple[float, int]:
    """
    Train, evaluate, and persist the model. Synchronous sklearn work — call
    via asyncio.to_thread from async code. Returns (holdout_accuracy, n_samples).
    """
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score
    from sklearn.model_selection import train_test_split

    n = len(y)

    def make_model():
        if n >= _GBM_MIN_SAMPLES:
            return CalibratedClassifierCV(
                GradientBoostingClassifier(random_state=42), cv=3
            )
        return LogisticRegression(max_iter=1000)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y if len(set(y)) > 1 else None
    )
    eval_model = make_model()
    eval_model.fit(X_train, y_train)
    accuracy = float(accuracy_score(y_test, eval_model.predict(X_test)))

    # Refit on the full dataset for the production model
    final_model = make_model()
    final_model.fit(X, y)

    path = model_path()
    joblib.dump(final_model, path)
    log.info("Trained ML model on %d samples (holdout accuracy %.3f) → %s", n, accuracy, path)

    global _cached_model, _cached_mtime
    with _lock:
        _cached_model = final_model
        _cached_mtime = path.stat().st_mtime

    return accuracy, n
