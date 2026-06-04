"""
EV blend, Kelly criterion, and breakeven computation.

Weights:
  α (market_prob):      starts at alpha_market, absorbs unused β when sample is small
  β (historical_prob):  scales from 0 → beta_historical_max as sample size grows
  γ (movement_signal):  applied as a multiplier on the additive movement nudge

Movement is an ADDITIVE NUDGE (not a third probability):
  true_prob = α*market_prob + β*historical_prob + γ*movement_signal
  clamped to [0.01, 0.99]

This is cleaner than treating movement as an independent probability estimate —
the signal is a directional correction to the market price, not a standalone view.

Kelly uses half-Kelly by default (kelly_fraction_multiplier = 0.5) with a hard cap.
Breakeven per pick for a Power Play parlay:
  breakeven(n_picks) = (1 / multiplier)^(1/n_picks)
"""
import statistics
from backend.config import settings


def _effective_weights(sample_n: int) -> tuple[float, float, float]:
    """Return (alpha_eff, beta_eff, gamma) given the historical sample size."""
    ramp = min(sample_n / settings.historical_full_sample, 1.0)
    beta  = settings.beta_historical_max * ramp
    alpha = settings.alpha_market + (settings.beta_historical_max - beta)
    return alpha, beta, settings.gamma_movement


def breakeven(n_picks: int) -> float:
    """Minimum per-pick true probability for a Power Play parlay to be +EV."""
    mult = settings.power_play_multipliers.get(n_picks, 3.0)
    return (1.0 / mult) ** (1.0 / n_picks)


def kelly_fraction(true_prob: float, n_picks: int) -> float:
    """
    Half-Kelly fraction for one pick in an n-pick Power Play.
    b = net decimal odds = multiplier - 1
    full_kelly = (p*(b+1) - 1) / b
    Returns 0 if EV is negative.
    """
    mult = settings.power_play_multipliers.get(n_picks, 3.0)
    b = mult - 1.0
    if b <= 0:
        return 0.0
    full_kelly = (true_prob * (b + 1) - 1) / b
    if full_kelly <= 0:
        return 0.0
    half_kelly = full_kelly * settings.kelly_fraction_multiplier
    return min(half_kelly, settings.kelly_max)


class EVResult:
    __slots__ = (
        "market_prob", "historical_prob", "movement_signal",
        "blended_prob", "ev_pct", "ev_std",
        "kelly_2pick", "kelly_3pick", "kelly_4pick",
        "sample_n", "weights_used",
    )

    def __init__(
        self,
        market_prob:      float,
        historical_prob:  float,
        movement_signal:  float,   # additive nudge in [-0.10, +0.10]
        sample_n:         int,
    ):
        alpha, beta, gamma = _effective_weights(sample_n)

        self.market_prob     = market_prob
        self.historical_prob = historical_prob
        self.movement_signal = movement_signal
        self.sample_n        = sample_n
        self.weights_used    = {"alpha": alpha, "beta": beta, "gamma": gamma}

        # Normalize the probabilistic portion (market + historical) to sum to 1,
        # then add the movement nudge separately. This ensures that when
        # movement_signal = 0, blended_prob = market_prob (not 0.85 * market_prob).
        w_total = alpha + beta
        prob_blend = (alpha / w_total) * market_prob + (beta / w_total) * historical_prob
        raw = prob_blend + gamma * movement_signal
        self.blended_prob = max(0.01, min(0.99, raw))

        # EV vs 2-pick breakeven as the primary displayed metric
        self.ev_pct = (self.blended_prob - breakeven(2)) * 100

        # Confidence interval: std dev across the three component estimates.
        # Convert movement to an implied over-prob for variance (centered on market).
        move_implied = max(0.0, min(1.0, market_prob + movement_signal))
        self.ev_std = statistics.pstdev([market_prob, historical_prob, move_implied]) * 100

        self.kelly_2pick = kelly_fraction(self.blended_prob, 2) * 100
        self.kelly_3pick = kelly_fraction(self.blended_prob, 3) * 100
        self.kelly_4pick = kelly_fraction(self.blended_prob, 4) * 100
