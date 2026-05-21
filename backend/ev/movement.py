"""
Line movement / steam detection.

Compares the most recent odds snapshot to the previous one.
Fires a directional signal only when STEAM_MIN_BOOKS books have moved
in the same direction — a single book moving is noise.

Signal output: float in [-1, 1]
  > 0  → steam toward Over  (books shortening Over odds = more confident it hits)
  < 0  → steam toward Under
  0    → no consensus movement or insufficient books moved
"""
from collections import defaultdict
from backend.config import STEAM_MIN_BOOKS, BOOK_WEIGHTS


def _american_to_implied(odds: int) -> float:
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def compute_movement_signal(
    prev_snapshots: list[dict],   # [{book, direction, odds}, ...]
    curr_snapshots: list[dict],
) -> float:
    """
    Returns a movement signal in [-1, 1].
    Positive = steam toward Over, negative = steam toward Under.
    """
    if not prev_snapshots or not curr_snapshots:
        return 0.0

    # Build lookup: (book, direction) -> odds
    prev = {(s["book"], s["direction"]): s["odds"] for s in prev_snapshots}
    curr = {(s["book"], s["direction"]): s["odds"] for s in curr_snapshots}

    # Count books moving toward each direction
    # "Moving toward Over" = Over odds shortening (implied prob increasing)
    over_movers:  list[str] = []
    under_movers: list[str] = []

    books = set(b for b, _ in curr.keys())
    for book in books:
        prev_over  = prev.get((book, "Over"))
        curr_over  = curr.get((book, "Over"))
        if prev_over is None or curr_over is None:
            continue

        prev_p = _american_to_implied(prev_over)
        curr_p = _american_to_implied(curr_over)
        delta = curr_p - prev_p

        if delta > 0.005:    # Over implied prob increased → steam toward Over
            over_movers.append(book)
        elif delta < -0.005: # Over implied prob decreased → steam toward Under
            under_movers.append(book)

    def _weighted_count(movers: list[str]) -> float:
        return sum(BOOK_WEIGHTS.get(b, 1.0) for b in movers)

    over_weight  = _weighted_count(over_movers)
    under_weight = _weighted_count(under_movers)

    if len(over_movers) >= STEAM_MIN_BOOKS and over_weight > under_weight:
        # Normalise by max possible weighted count
        max_weight = sum(BOOK_WEIGHTS.values())
        return min(over_weight / max_weight, 1.0)

    if len(under_movers) >= STEAM_MIN_BOOKS and under_weight > over_weight:
        max_weight = sum(BOOK_WEIGHTS.values())
        return -min(under_weight / max_weight, 1.0)

    return 0.0
