"""
Line movement / steam detection.

Every scrape inserts rows into odds_snapshots. To compute the signal for a prop
we look at snapshots within a rolling window (default 30 min) and ask:
  - How many books moved in the same direction?
  - How large was the average move?
  - Did a sharp book (Pinnacle / Circa) move first?

Requirements before the signal fires:
  - At least STEAM_MIN_BOOKS books moved the same way
  - Each individual book move must exceed STEAM_NOISE_FLOOR (0.5 pp) — smaller
    moves are data noise or routine micro-adjustments

Output: additive nudge in [-0.10, +0.10] added directly to the blended
true_prob. Positive = steam toward Over. The blend layer's γ weight further
scales it, keeping it a small correction rather than a dominant signal.

Sharp-book boost: if Pinnacle or Circa initiated the move in the consensus
direction, the signal is boosted by STEAM_SHARP_BOOST (25%). Sharp books
moving first is a stronger EV indicator than retail books following.
"""
from collections import defaultdict
from datetime import datetime, timedelta

from backend.config import settings
from backend.ev.shin import american_to_implied, power_devig

SHARP_BOOKS = {"pinnacle", "circa"}


def _devig_to_over_prob(over_odds: int | None, under_odds: int | None) -> float | None:
    if over_odds is None or under_odds is None:
        return None
    p_o, p_u = power_devig(american_to_implied(over_odds), american_to_implied(under_odds))
    s = p_o + p_u
    return p_o / s if s > 0 else None


def compute_movement_signal(
    snapshots: list[dict],   # all snapshots for this prop, any time range
    now: datetime | None = None,
) -> float:
    """
    snapshots: list of dicts with keys: book, direction, over_odds, under_odds, snapshot_at (datetime)
    Returns additive signal in [-0.10, +0.10]. Positive = steam toward Over.
    """
    now = now or datetime.utcnow()
    window_start = now - timedelta(minutes=settings.steam_window_minutes)

    in_window = [s for s in snapshots if s["snapshot_at"] >= window_start]
    if len(in_window) < 2:
        return 0.0

    # Bucket by book → list of snapshots sorted ascending by time
    by_book: dict[str, list[dict]] = defaultdict(list)
    for s in in_window:
        by_book[s["book"].lower()].append(s)

    over_movers: list[str] = []
    under_movers: list[str] = []
    total_delta = 0.0
    earliest_sharp: dict[str, datetime | None] = {"over": None, "under": None}

    for book, snaps in by_book.items():
        if len(snaps) < 2:
            continue
        snaps_sorted = sorted(snaps, key=lambda x: x["snapshot_at"])
        first, last = snaps_sorted[0], snaps_sorted[-1]

        p0 = _devig_to_over_prob(first.get("over_odds"), first.get("under_odds"))
        p1 = _devig_to_over_prob(last.get("over_odds"),  last.get("under_odds"))
        if p0 is None or p1 is None:
            continue

        delta = p1 - p0
        if abs(delta) < settings.steam_noise_floor:
            continue

        total_delta += delta
        direction = "over" if delta > 0 else "under"
        (over_movers if delta > 0 else under_movers).append(book)

        if book in SHARP_BOOKS:
            t = last["snapshot_at"]
            if earliest_sharp[direction] is None or t < earliest_sharp[direction]:
                earliest_sharp[direction] = t

    dominant = "over" if len(over_movers) >= len(under_movers) else "under"
    dominant_count = len(over_movers) if dominant == "over" else len(under_movers)

    if dominant_count < settings.steam_min_books:
        return 0.0

    total_movers = len(over_movers) + len(under_movers)
    avg_delta = total_delta / total_movers if total_movers else 0.0
    signal = max(-0.10, min(0.10, avg_delta))

    # Boost if a sharp book initiated the move in the consensus direction
    if earliest_sharp[dominant] is not None:
        signal *= settings.steam_sharp_boost
        signal = max(-0.10, min(0.10, signal))

    return signal
