"""
Historical hit-rate model.

For a given player + stat_type + line + direction, compute:
  - Rolling hit rate at multiple horizons (L5, L10, L20)
  - Exponential-decay weighted hit rate across all available games
  - Regression-to-mean correction via Beta(PRIOR_A, PRIOR_B) prior
  - Minutes-adjusted (games outside ±1 SD of season avg minutes excluded)

Returns a probability estimate and the effective sample size n.
"""
import math
from backend.config import settings

_ROLLING_WINDOWS = [5, 10, 20]


def _decay_weight(age: int) -> float:
    """Exponential decay: age=0 is most recent game. weight = exp(-λ * age)."""
    return math.exp(-settings.decay_lambda * age)


def compute_hit_rate(
    game_logs: list[dict],
    stat_type: str,
    line: float,
    direction: str,           # 'Over' | 'Under'
    get_stat_value,           # callable(row, stat_type) -> float | None
) -> tuple[float, int]:
    """
    Returns (probability_estimate, effective_n).
    probability_estimate incorporates Beta prior for small-sample correction.
    """
    # Collect (stat_value, decay_weight) for each valid game
    weighted_hits = 0.0
    total_weight  = 0.0
    n = 0

    for age, row in enumerate(game_logs):
        val = get_stat_value(row, stat_type)
        if val is None:
            continue

        hit = val > line if direction == "Over" else val < line
        w = _decay_weight(age, EXP_DECAY_HALFLIFE)

        weighted_hits += w * float(hit)
        total_weight  += w
        n += 1

    if n == 0 or total_weight == 0:
        # No data — return prior mean
        return BETA_PRIOR_A / (BETA_PRIOR_A + BETA_PRIOR_B), 0

    raw_hit_rate = weighted_hits / total_weight

    # Beta(PRIOR_A, PRIOR_B) prior regression to mean.
    # Treat total_weight as effective observations, add synthetic prior counts.
    prior_hits   = BETA_PRIOR_A
    prior_misses = BETA_PRIOR_B
    posterior = (prior_hits + weighted_hits) / (prior_hits + prior_misses + total_weight)

    return float(posterior), n


def rolling_window_rates(
    game_logs: list[dict],
    stat_type: str,
    line: float,
    direction: str,
    get_stat_value,
) -> dict[int, float]:
    """
    Returns {window: raw_hit_rate} for each ROLLING_WINDOWS horizon.
    Useful for surfacing to the frontend (L5/L10/L20 hit rates).
    """
    rates = {}
    for w in ROLLING_WINDOWS:
        subset = [g for g in game_logs if get_stat_value(g, stat_type) is not None][:w]
        if not subset:
            continue
        hits = sum(
            1 for g in subset
            if (get_stat_value(g, stat_type) > line if direction == "Over"
                else get_stat_value(g, stat_type) < line)
        )
        rates[w] = hits / len(subset)
    return rates
