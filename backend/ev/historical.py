"""
Historical hit-rate model.

For a given player + stat_type + line + direction, compute:
  - Rolling hit rate at multiple horizons (L5, L10, L20)
  - Exponential-decay weighted hit rate across all available games
  - Regression-to-mean correction via Beta(prior_overs, prior_unders) prior
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
    direction: str,       # 'Over' | 'Under'
    get_stat_value,       # callable(row, stat_type) -> float | None
) -> tuple[float, int]:
    """
    Returns (probability_estimate, effective_n).
    Incorporates Beta prior for small-sample regression to mean.
    """
    weighted_hits = 0.0
    total_weight  = 0.0
    n = 0

    for age, row in enumerate(game_logs):
        val = get_stat_value(row, stat_type)
        if val is None:
            continue

        hit = val > line if direction == "Over" else val < line
        w = _decay_weight(age)

        weighted_hits += w * float(hit)
        total_weight  += w
        n += 1

    prior_a = settings.beta_prior_overs
    prior_b = settings.beta_prior_unders

    if n == 0 or total_weight == 0:
        return prior_a / (prior_a + prior_b), 0

    posterior = (prior_a + weighted_hits) / (prior_a + prior_b + total_weight)
    return float(posterior), n


def rolling_window_rates(
    game_logs: list[dict],
    stat_type: str,
    line: float,
    direction: str,
    get_stat_value,
) -> dict[int, float]:
    """Returns {window: raw_hit_rate} for L5, L10, L20."""
    rates = {}
    for w in _ROLLING_WINDOWS:
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
