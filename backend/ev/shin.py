"""
Power-method devigging for a two-outcome market (Over / Under).

The textbook "additive normalization" divides each raw implied prob by the total,
treating vig as spread evenly. That's biased on lopsided lines: it shrinks both
sides by the same factor, which doesn't match how books actually price asymmetric
markets.

The power method finds k > 1 such that:
    p_over_raw^k + p_under_raw^k = 1

Since k > 1 and each p < 1, raising to a higher power shrinks longshots MORE than
favorites — matching sharp book closing lines better than additive normalization.

For symmetric -110/-110 lines the result matches simple normalization to 4+ decimal
places. The methods diverge as the line becomes more lopsided.

Note: this is often called "Shin's method" in sports analytics blogs, but it's more
accurately the power / logarithmic method. The original Shin (1993) formula models
insider trading explicitly via a different parameterization. The power method is the
production workhorse most quant betting shops actually use.
"""
from scipy.optimize import brentq


def american_to_implied(odds: int) -> float:
    """Convert American odds to raw implied probability (vig still included)."""
    if odds < 0:
        return -odds / (-odds + 100)
    return 100 / (odds + 100)


def power_k(p_over_raw: float, p_under_raw: float) -> float | None:
    """Solve for the power-method vig exponent k > 1 of a two-way market.

    Returns None on degenerate inputs (no vig, or solver failure). The exponent
    characterizes how much vig the book bakes into each outcome, so it can be
    reused to devig one-sided quotes (alternate lines) from the same book.
    """
    total = p_over_raw + p_under_raw
    if total <= 1.0 + 1e-9:
        return None

    def f(k: float) -> float:
        return (p_over_raw ** k) + (p_under_raw ** k) - 1.0

    try:
        # At k=1: sum = total > 1. As k grows both terms shrink toward 0.
        # brentq finds the unique k > 1 where they sum to exactly 1.
        return brentq(f, 1.0, 10.0, xtol=1e-9, maxiter=50)
    except (ValueError, RuntimeError):
        return None


def power_devig(p_over_raw: float, p_under_raw: float) -> tuple[float, float]:
    """Return (true_p_over, true_p_under) via the power method.

    Falls back to simple normalization on degenerate inputs (no vig or bad data).
    """
    k = power_k(p_over_raw, p_under_raw)
    if k is None:
        total = p_over_raw + p_under_raw
        return p_over_raw / total, p_under_raw / total
    return p_over_raw ** k, p_under_raw ** k


def devig_one_sided(p_raw: float, k: float | None, fallback_overround: float) -> float:
    """Devig a one-sided quote (alternate lines are usually Over-only).

    Uses the book's vig exponent k from its main line on the same prop when
    available; otherwise divides by an assumed two-way overround.
    Result is clamped to (0, 1).
    """
    if k is not None and k > 1.0:
        p = p_raw ** k
    else:
        p = p_raw / fallback_overround
    return min(max(p, 1e-6), 1.0 - 1e-6)


def devig_book_odds(over_odds: int | None, under_odds: int | None) -> tuple[float, float] | None:
    """Devig a single book's two-way market. Returns None if either side is missing."""
    if over_odds is None or under_odds is None:
        return None
    return power_devig(american_to_implied(over_odds), american_to_implied(under_odds))


def weighted_market_prob(
    book_probs: dict[str, tuple[float, float]],
    book_weights: dict[str, float],
    default_weight: float,
) -> tuple[float, float, int]:
    """Aggregate per-book devigged probs into a market consensus.

    Sharp books (Pinnacle, Circa) lead the market and get the highest weight.
    Retail books lag and may distort the consensus, so they are discounted.

    Returns (market_p_over, market_p_under, n_books_used).
    """
    if not book_probs:
        return 0.5, 0.5, 0

    total_w = sum_over = sum_under = 0.0
    for book, (p_over, p_under) in book_probs.items():
        w = book_weights.get(book.lower(), default_weight)
        total_w   += w
        sum_over  += w * p_over
        sum_under += w * p_under

    if total_w == 0:
        return 0.5, 0.5, 0

    p_over  = sum_over  / total_w
    p_under = sum_under / total_w
    s = p_over + p_under
    return p_over / s, p_under / s, len(book_probs)
