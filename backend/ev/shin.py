"""
Shin (1993) devigging model for a two-outcome market (Over / Under).

Simple normalization assumes the book's margin is proportional across both sides.
Shin shows that informed bettors cause the margin to be asymmetric — heavier on
the long shot side. The Shin model recovers the true probability p* by solving
for the insider fraction z implied by the observed margin.

For a two-outcome market with raw implied probabilities q1, q2 (summing to >1):
    p* = (sqrt(z^2 + 4(1-z) * q1^2 / (q1+q2)) - z) / (2*(1-z))

z is estimated from the total margin:  sum(q_i) - 1
"""
import math


def _american_to_implied(odds: int) -> float:
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def _estimate_z(q1: float, q2: float) -> float:
    """Estimate insider fraction z from the observed margin."""
    margin = q1 + q2 - 1.0
    # Clamp to plausible range; typical sports books: 0.01 – 0.08
    return max(0.01, min(margin * 0.7, 0.08))


def shin_prob(over_odds: int, under_odds: int) -> tuple[float, float]:
    """
    Return (p_over, p_under) using the Shin model.
    Both sum to 1.0 (vig removed).
    """
    q_over  = _american_to_implied(over_odds)
    q_under = _american_to_implied(under_odds)
    total   = q_over + q_under

    z = _estimate_z(q_over, q_under)

    def _shin(q: float) -> float:
        discriminant = z**2 + 4 * (1 - z) * q**2 / total
        return (math.sqrt(discriminant) - z) / (2 * (1 - z))

    p_over  = _shin(q_over)
    p_under = _shin(q_under)

    # Normalise to ensure they sum to exactly 1
    s = p_over + p_under
    return p_over / s, p_under / s


def devig_book_odds(over_odds: int | None, under_odds: int | None) -> tuple[float, float] | None:
    """
    Returns Shin-devigged (p_over, p_under) for one book, or None if data missing.
    Falls back to simple normalisation when one side is missing.
    """
    if over_odds is None or under_odds is None:
        return None
    return shin_prob(over_odds, under_odds)
