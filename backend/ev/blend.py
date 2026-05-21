"""
EV blend, Kelly criterion, and breakeven computation.

Weights:
  α (market_prob):     ALPHA_BASE → 0.50 as β scales up
  β (historical_prob): 0.0 → BETA_MAX  (scales with sample size n)
  γ (movement_signal): GAMMA (fixed)

Movement signal ∈ [-1, 1] is converted to a probability boost/penalty:
  p_movement = 0.5 + signal * 0.10  (±10 pp max contribution)
  This keeps it in [0, 1] and symmetrical around 50%.

EV% = blended_prob - breakeven_prob(n_picks)
Kelly fraction = (p*(b+1) - 1) / b  where b = net_odds_decimal
"""
import math
import statistics
from backend.config import (
    ALPHA_BASE, BETA_MAX, BETA_RAMP_N, GAMMA,
    POWER_PLAY_MULTIPLIERS,
)


def _weights(n: int) -> tuple[float, float, float]:
    """Return (alpha, beta, gamma) given sample size n."""
    beta  = BETA_MAX * min(n / BETA_RAMP_N, 1.0)
    alpha = 1.0 - beta - GAMMA
    return alpha, beta, GAMMA


def _movement_to_prob(signal: float, direction: str) -> float:
    """
    Convert a [-1,1] movement signal to a probability for the given direction.
    signal > 0 → steam toward Over → boosts Over probability.
    """
    # signal is already in "toward Over" convention; flip for Under
    directional = signal if direction == "Over" else -signal
    return 0.5 + directional * 0.10


def breakeven(n_picks: int) -> float:
    """
    Minimum per-pick true probability for a Power Play parlay to be +EV.
    breakeven_per_pick = (1 / multiplier) ^ (1 / n_picks)
    """
    mult = POWER_PLAY_MULTIPLIERS.get(n_picks, POWER_PLAY_MULTIPLIERS[2])
    return (1.0 / mult) ** (1.0 / n_picks)


def kelly_fraction(true_prob: float, n_picks: int) -> float:
    """
    Kelly fraction for one pick in an n-pick Power Play parlay.
    b = net_decimal_odds - 1  (e.g., 3x payout on a 2-pick = b=2)
    f = (p*(b+1) - 1) / b
    Clamped to [0, 0.25] (max quarter-Kelly for safety).
    """
    mult = POWER_PLAY_MULTIPLIERS.get(n_picks, POWER_PLAY_MULTIPLIERS[2])
    b = mult - 1.0
    f = (true_prob * (b + 1) - 1) / b
    return max(0.0, min(f, 0.25))


class EVResult:
    __slots__ = (
        "market_prob", "historical_prob", "movement_signal",
        "blended_prob", "ev_pct", "ev_std",
        "kelly_2pick", "kelly_3pick", "kelly_4pick",
        "sample_n",
    )

    def __init__(
        self,
        market_prob: float,
        historical_prob: float,
        movement_signal: float,
        direction: str,
        sample_n: int,
    ):
        alpha, beta, gamma = _weights(sample_n)
        p_move = _movement_to_prob(movement_signal, direction)

        self.market_prob     = market_prob
        self.historical_prob = historical_prob
        self.movement_signal = movement_signal
        self.sample_n        = sample_n

        self.blended_prob = (
            alpha * market_prob +
            beta  * historical_prob +
            gamma * p_move
        )

        # EV vs 2-pick breakeven as the baseline displayed metric
        self.ev_pct = self.blended_prob - breakeven(2)

        # Confidence interval: std dev across the three component estimates
        self.ev_std = statistics.pstdev([market_prob, historical_prob, p_move])

        self.kelly_2pick = kelly_fraction(self.blended_prob, 2)
        self.kelly_3pick = kelly_fraction(self.blended_prob, 3)
        self.kelly_4pick = kelly_fraction(self.blended_prob, 4)
