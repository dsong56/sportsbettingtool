"""
Sportsbook best-line pipeline.

Unlike the PrizePicks pipeline, this doesn't anchor on PrizePicks lines.
It scans ALL props from the Odds API — main lines AND alternate lines
(15+/20+ style ladders) — and finds where a sportsbook is offering a softer
price than the market consensus — i.e. a +EV straight bet.

For each (player, stat, line):
  1. Compute the devigged market consensus probability (true_prob)
     - main lines: standard two-way power-method devig per book
     - alternate lines: usually quoted Over-only, so each book's vig exponent k
       is borrowed from its own main line on the same prop and applied to the
       one-sided price (falling back to a default overround if no main line)
  2. For every book posting that prop, calculate EV vs the consensus
  3. Return the book with the best EV per prop, if EV > 0
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import BOOK_WEIGHTS, BOOK_WEIGHT_DEFAULT, PRIVATE_BOOKS, settings
from backend.scrapers.odds_api import fetch_odds
from backend.ev.shin import (
    american_to_implied,
    devig_book_odds,
    devig_one_sided,
    power_k,
    weighted_market_prob,
)
from backend.db.models import SportsbookLine


def _american_to_decimal(odds: int) -> float:
    if odds > 0:
        return odds / 100 + 1
    return 100 / abs(odds) + 1


def _kelly(true_prob: float, decimal_odds: float) -> float:
    b = decimal_odds - 1
    if b <= 0:
        return 0.0
    full = (true_prob * (b + 1) - 1) / b
    return max(0.0, min(full * 0.5, 0.25))   # half-Kelly, capped at 25%


async def run_sportsbook_pipeline(sport: str, db: AsyncSession) -> list[dict]:
    odds_props = await fetch_odds(sport)
    if not odds_props:
        return []

    # Group odds by (player, stat, line) → {book: odds} per direction
    over_map:  dict[tuple, dict[str, int]] = defaultdict(dict)
    under_map: dict[tuple, dict[str, int]] = defaultdict(dict)
    alt_keys:  set[tuple] = set()

    for p in odds_props:
        key = (p.player_name, p.stat_type, p.line)
        if p.is_alt:
            alt_keys.add(key)
        if p.direction == "Over":
            over_map[key][p.book] = p.odds
        else:
            under_map[key][p.book] = p.odds

    # Per-book vig exponent from each book's MAIN line on the same (player, stat).
    # Reused to devig the book's one-sided alternate quotes.
    book_k: dict[tuple[str, str, str], float] = {}
    for key in set(over_map) & set(under_map):
        if key in alt_keys:
            continue
        player, stat, _line = key
        for book in set(over_map[key]) & set(under_map[key]):
            k = power_k(
                american_to_implied(over_map[key][book]),
                american_to_implied(under_map[key][book]),
            )
            if k is not None:
                book_k[(player, stat, book)] = k

    now = datetime.utcnow()
    results: list[dict] = []
    all_keys = set(over_map) | set(under_map)

    for key in all_keys:
        player, stat, line = key
        is_alt      = key in alt_keys
        over_books  = over_map.get(key, {})
        under_books = under_map.get(key, {})

        public = lambda b: b.lower() not in PRIVATE_BOOKS
        two_sided = {b for b in set(over_books) & set(under_books) if public(b)}

        # Devig each two-sided book and build consensus
        book_probs: dict[str, tuple[float, float]] = {}
        for book in two_sided:
            p = devig_book_odds(over_books[book], under_books[book])
            if p:
                book_probs[book] = p

        if is_alt:
            # Alternate ladders are usually Over-only — devig one-sided quotes
            # using each book's own vig exponent from its main line.
            for direction_books, is_over in ((over_books, True), (under_books, False)):
                for book, odds in direction_books.items():
                    if book in book_probs or not public(book):
                        continue
                    p = devig_one_sided(
                        american_to_implied(odds),
                        book_k.get((player, stat, book)),
                        settings.alt_fallback_overround,
                    )
                    book_probs[book] = (p, 1 - p) if is_over else (1 - p, p)
            # One-sided estimates are noisier — require corroboration
            if len(book_probs) < settings.alt_min_books:
                continue
        elif not book_probs:
            continue

        market_p_over, market_p_under, n_books = weighted_market_prob(
            book_probs, BOOK_WEIGHTS, BOOK_WEIGHT_DEFAULT
        )

        # Evaluate every book for both directions
        for direction, true_prob, all_book_odds in (
            ("Over",  market_p_over,  over_books),
            ("Under", market_p_under, under_books),
        ):
            best_book  = None
            best_odds  = None
            best_ev    = 0.0   # only keep positive EV

            for book, odds in all_book_odds.items():
                if not public(book):
                    continue
                dec = _american_to_decimal(odds)
                ev  = true_prob * dec - 1   # net return per $1 staked
                if ev > best_ev:
                    best_ev   = ev
                    best_book = book
                    best_odds = odds

            if best_book is None:
                continue

            dec    = _american_to_decimal(best_odds)
            kelly  = _kelly(true_prob, dec)

            # Persist
            db.add(SportsbookLine(
                player_name=player,
                stat_type=stat,
                line_score=line,
                sport=sport,
                direction=direction,
                is_alt=is_alt,
                best_book=best_book,
                best_odds=best_odds,
                market_prob=round(true_prob, 4),
                ev_pct=round(best_ev * 100, 2),
                kelly_pct=round(kelly * 100, 2),
                n_books=n_books,
                computed_at=now,
            ))

            results.append({
                "player_name": player,
                "stat_type":   stat,
                "line_score":  line,
                "sport":       sport,
                "direction":   direction,
                "is_alt":      is_alt,
                "best_book":   best_book,
                "best_odds":   best_odds,
                "market_prob": round(true_prob, 4),
                "ev_pct":      round(best_ev * 100, 2),
                "kelly_pct":   round(kelly * 100, 2),
                "n_books":     n_books,
                "computed_at": now.isoformat(),
            })

    await db.commit()
    return sorted(results, key=lambda x: x["ev_pct"], reverse=True)
