"""
Full EV pipeline for a single sport.

Steps:
1. Fetch PrizePicks projections (httpx)
2. Fetch Odds API props (httpx, async batched)
3. For each (player, stat, line) on PrizePicks:
   a. Collect all book odds → power-method devig → weighted market probability
   b. Fetch game logs (cached) → historical hit rate with Beta prior + minutes filter
   c. Query previous odds snapshots → steam signal (additive nudge, ≥3 books, 30-min window)
   d. Blend signals → EVResult
4. Persist odds snapshots + ev_results + predictions to DB
5. Return list of serialisable dicts for the API layer
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import datetime, UTC
from typing import TypeAlias

from rapidfuzz import fuzz, process
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings, BOOK_WEIGHTS, BOOK_WEIGHT_DEFAULT, PRIVATE_BOOKS
from backend.scrapers.prizepicks import fetch_projections
from backend.scrapers.odds_api import fetch_odds
from backend.ev.shin import devig_book_odds, weighted_market_prob
from backend.ev.historical import compute_hit_rate, rolling_window_rates
from backend.ev.movement import compute_movement_signal
from backend.ev.blend import EVResult, breakeven
from backend.db.models import OddsSnapshot, EVResult as EVResultModel, Prediction, GameLogCache

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}


# ---------- name normalisation ----------

def _normalize(name: str) -> str:
    """Lowercase, strip accents and punctuation, drop name suffixes."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_name = nfkd.encode("ascii", "ignore").decode()
    cleaned = re.sub(r"[.\-']", "", ascii_name.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    parts = [p for p in cleaned.split() if p not in _SUFFIXES]
    return " ".join(parts)


async def _load_corrections(db: AsyncSession, sport: str) -> dict[str, str]:
    from backend.db.models import NameCorrection
    rows = (await db.execute(
        select(NameCorrection).where(NameCorrection.sport == sport)
    )).scalars()
    return {_normalize(r.raw_name): r.canonical_name for r in rows}


def _resolve_name(
    raw: str,
    canonical_pool: list[str],
    corrections: dict[str, str],
) -> tuple[str, float]:
    """Returns (canonical_name, confidence 0-1). Uses rapidfuzz token_sort_ratio."""
    norm = _normalize(raw)

    # 1. Manual override
    if norm in corrections:
        return corrections[norm], 1.0

    # 2. Exact normalized match
    norm_to_orig = {_normalize(c): c for c in canonical_pool}
    if norm in norm_to_orig:
        return norm_to_orig[norm], 1.0

    # 3. Fuzzy via rapidfuzz (token_sort handles word-order differences)
    if norm_to_orig:
        result = process.extractOne(
            norm, list(norm_to_orig.keys()),
            scorer=fuzz.token_sort_ratio,
        )
        if result and result[1] >= settings.name_match_threshold:
            return norm_to_orig[result[0]], result[1] / 100.0

    return raw, 0.0


# ---------- stats dispatch ----------

async def _get_game_logs(player_name: str, sport: str, db: AsyncSession) -> list[dict]:
    from backend.stats import nba, nhl, mlb

    cached = (await db.execute(
        select(GameLogCache)
        .where(GameLogCache.player_name == player_name, GameLogCache.sport == sport)
        .order_by(desc(GameLogCache.cached_at))
        .limit(30)
    )).scalars().all()
    if cached:
        return [r.stats for r in cached]

    match sport:
        case "NBA": logs = await nba.fetch_game_logs(player_name)
        case "NHL": logs = await nhl.fetch_game_logs(player_name)
        case "MLB": logs = await mlb.fetch_game_logs(player_name)
        case _:     logs = []

    for log in logs:
        db.add(GameLogCache(
            player_name=player_name, sport=sport,
            game_date=log["game_date"], stats=log,
        ))
    if logs:
        await db.commit()
    return logs


def _get_stat_fn(sport: str):
    from backend.stats import nba, nhl, mlb
    match sport:
        case "NBA": return nba._extract_stat
        case "NHL": return nhl.get_stat_value
        case "MLB": return mlb.get_stat_value
    raise ValueError(f"Unknown sport: {sport}")


def _minutes_flag(logs: list[dict], sport: str) -> bool:
    if sport == "NBA":
        from backend.stats.nba import filter_by_minutes
        _, flag = filter_by_minutes(logs)
        return flag
    return False


# ---------- main pipeline ----------

async def run_pipeline(sport: str, db: AsyncSession) -> list[dict]:
    import asyncio
    pp_lines, odds_props = await asyncio.gather(
        fetch_projections(sport),
        fetch_odds(sport),
    )

    corrections = await _load_corrections(db, sport)
    canonical_pool = [p.player_name for p in pp_lines]

    # Build odds lookup: (canonical_name, stat_type, line) → {book: odds}
    PropKey: TypeAlias = tuple[str, str, float]
    over_odds_map:  dict[PropKey, dict[str, int]] = defaultdict(dict)
    under_odds_map: dict[PropKey, dict[str, int]] = defaultdict(dict)

    for prop in odds_props:
        canon, _ = _resolve_name(prop.player_name, canonical_pool, corrections)
        key = (canon, prop.stat_type, prop.line)
        if prop.direction == "Over":
            over_odds_map[key][prop.book]  = prop.odds
        else:
            under_odds_map[key][prop.book] = prop.odds

    # Load recent snapshots for steam detection (last 2 hours to cover the window)
    from datetime import timedelta
    cutoff = datetime.now(UTC) - timedelta(hours=2)
    prev_snaps_rows = (await db.execute(
        select(OddsSnapshot)
        .where(OddsSnapshot.sport == sport, OddsSnapshot.snapshot_at >= cutoff)
        .order_by(OddsSnapshot.snapshot_at)
    )).scalars().all()

    prev_snaps_by_key: dict[PropKey, list[dict]] = defaultdict(list)
    for r in prev_snaps_rows:
        k = (r.player_name, r.stat_type, r.line_score)
        prev_snaps_by_key[k].append({
            "book": r.book,
            "direction": r.direction,
            "over_odds": r.odds if r.direction == "Over" else None,
            "under_odds": r.odds if r.direction == "Under" else None,
            "snapshot_at": r.snapshot_at,
        })

    now = datetime.now(UTC)
    stat_fn = _get_stat_fn(sport)
    seen: set[tuple] = set()
    results: list[dict] = []

    for proj in pp_lines:
        canon, _ = _resolve_name(proj.player_name, canonical_pool, corrections)

        for direction in ("Over", "Under"):
            for line in {proj.line_score, proj.line_score - 0.5, proj.line_score + 0.5}:
                prop_key = (canon, proj.stat_type, line, direction, sport)
                if prop_key in seen:
                    continue

                base_key = (canon, proj.stat_type, line)
                over_by_book  = over_odds_map.get(base_key, {})
                under_by_book = under_odds_map.get(base_key, {})

                # Need at least one book with both sides
                common_books = set(over_by_book) & set(under_by_book)
                if not common_books:
                    continue
                seen.add(prop_key)

                # --- Market probability (power-method devigged, sharpness-weighted) ---
                book_probs: dict[str, tuple[float, float]] = {}
                for book in common_books:
                    if book.lower() in PRIVATE_BOOKS:
                        continue
                    p = devig_book_odds(over_by_book[book], under_by_book[book])
                    if p:
                        book_probs[book] = p

                if not book_probs:
                    continue

                market_p_over, market_p_under, _ = weighted_market_prob(
                    book_probs, BOOK_WEIGHTS, BOOK_WEIGHT_DEFAULT
                )
                market_prob = market_p_over if direction == "Over" else market_p_under

                # --- Historical hit rate ---
                logs = await _get_game_logs(canon, sport, db)
                hist_prob, sample_n = compute_hit_rate(logs, proj.stat_type, line, direction, stat_fn)
                roll_rates = rolling_window_rates(logs, proj.stat_type, line, direction, stat_fn)
                min_flag = _minutes_flag(logs, sport)

                # --- Steam signal (additive nudge) ---
                # Merge prev snapshots with current scrape to give the time-window logic data
                curr_snaps = []
                for book, o_odds in over_by_book.items():
                    curr_snaps.append({"book": book, "direction": "Over",
                                       "over_odds": o_odds, "under_odds": under_by_book.get(book),
                                       "snapshot_at": now})
                for book, u_odds in under_by_book.items():
                    if book not in over_by_book:
                        curr_snaps.append({"book": book, "direction": "Under",
                                           "over_odds": None, "under_odds": u_odds,
                                           "snapshot_at": now})

                all_snaps = prev_snaps_by_key.get(base_key, []) + curr_snaps
                movement = compute_movement_signal(all_snaps, now)

                # --- Blend ---
                ev = EVResult(market_prob, hist_prob, movement, sample_n)

                # --- Persist odds snapshots ---
                for book, o_odds in over_by_book.items():
                    db.add(OddsSnapshot(
                        player_name=canon, stat_type=proj.stat_type,
                        line_score=line, sport=sport, direction="Over",
                        odds=o_odds, book=book, snapshot_at=now,
                    ))
                for book, u_odds in under_by_book.items():
                    db.add(OddsSnapshot(
                        player_name=canon, stat_type=proj.stat_type,
                        line_score=line, sport=sport, direction="Under",
                        odds=u_odds, book=book, snapshot_at=now,
                    ))

                # --- Persist EV result ---
                db.add(EVResultModel(
                    player_name=canon, stat_type=proj.stat_type,
                    line_score=line, sport=sport, direction=direction,
                    market_prob=ev.market_prob,
                    historical_prob=ev.historical_prob,
                    movement_signal=ev.movement_signal,
                    blended_prob=ev.blended_prob,
                    ev_pct=ev.ev_pct,
                    ev_std=ev.ev_std,
                    kelly_2pick=ev.kelly_2pick,
                    kelly_3pick=ev.kelly_3pick,
                    kelly_4pick=ev.kelly_4pick,
                    sample_n=sample_n,
                    minutes_flag=int(min_flag),
                    computed_at=now,
                ))

                # --- Persist prediction for ML training ---
                db.add(Prediction(
                    player_name=canon, stat_type=proj.stat_type,
                    line_score=line, sport=sport, direction=direction,
                    predicted_prob=ev.blended_prob,
                    market_prob=ev.market_prob,
                    historical_prob=ev.historical_prob,
                    movement_signal=ev.movement_signal,
                    game_date=proj.game_date,
                    predicted_at=now,
                ))

                results.append({
                    "player_name":     canon,
                    "stat_type":       proj.stat_type,
                    "line_score":      line,
                    "sport":           sport,
                    "direction":       direction,
                    "game_date":       proj.game_date,
                    "market_prob":     round(ev.market_prob, 4),
                    "historical_prob": round(ev.historical_prob, 4),
                    "movement_signal": round(ev.movement_signal, 4),
                    "blended_prob":    round(ev.blended_prob, 4),
                    "ev_pct":          round(ev.ev_pct, 2),
                    "ev_std":          round(ev.ev_std, 2),
                    "kelly_2pick":     round(ev.kelly_2pick, 2),
                    "kelly_3pick":     round(ev.kelly_3pick, 2),
                    "kelly_4pick":     round(ev.kelly_4pick, 2),
                    "sample_n":        sample_n,
                    "minutes_flag":    min_flag,
                    "roll_l5":         round(roll_rates.get(5,  0) * 100, 1),
                    "roll_l10":        round(roll_rates.get(10, 0) * 100, 1),
                    "roll_l20":        round(roll_rates.get(20, 0) * 100, 1),
                    "breakeven_2pick": round(breakeven(2) * 100, 2),
                    "breakeven_3pick": round(breakeven(3) * 100, 2),
                    "breakeven_4pick": round(breakeven(4) * 100, 2),
                })

    await db.commit()
    return sorted(results, key=lambda x: x["ev_pct"], reverse=True)
