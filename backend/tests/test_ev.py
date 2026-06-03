"""
Unit tests for the EV math layer.
Run from the project root: pytest backend/tests/
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import math
import pytest
from datetime import datetime, UTC, timedelta

from backend.ev.shin import american_to_implied, power_devig, weighted_market_prob
from backend.ev.historical import compute_hit_rate, rolling_window_rates
from backend.ev.movement import compute_movement_signal
from backend.ev.blend import EVResult, breakeven, kelly_fraction


# ── american_to_implied ──────────────────────────────────────────────────────

def test_implied_negative_odds():
    assert abs(american_to_implied(-110) - 110 / 210) < 1e-9
    assert abs(american_to_implied(-200) - 200 / 300) < 1e-9

def test_implied_positive_odds():
    assert abs(american_to_implied(+100) - 0.5) < 1e-9
    assert abs(american_to_implied(+150) - 100 / 250) < 1e-9


# ── power_devig ──────────────────────────────────────────────────────────────

def test_power_devig_symmetric():
    """Symmetric -110/-110 → each side devigged to 50%."""
    p_o, p_u = power_devig(american_to_implied(-110), american_to_implied(-110))
    assert abs(p_o - 0.5) < 1e-4
    assert abs(p_u - 0.5) < 1e-4
    assert abs(p_o + p_u - 1.0) < 1e-9

def test_power_devig_sums_to_one():
    """Devigged probs must always sum to 1."""
    for over, under in [(-150, +130), (-300, +220), (-105, -115), (+110, -130)]:
        p_o, p_u = power_devig(american_to_implied(over), american_to_implied(under))
        assert abs(p_o + p_u - 1.0) < 1e-6, f"Failed for {over}/{under}"

def test_power_devig_lopsided_favors_favorite_more_than_additive():
    """Power method shrinks longshots more than additive normalization."""
    p_fav_raw = american_to_implied(-300)
    p_dog_raw = american_to_implied(+220)
    total = p_fav_raw + p_dog_raw
    simple_fav = p_fav_raw / total

    p_fav_power, p_dog_power = power_devig(p_fav_raw, p_dog_raw)
    assert p_fav_power > simple_fav
    assert p_dog_power < (p_dog_raw / total)

def test_power_devig_no_vig_passthrough():
    """If total implied prob ≤ 1 (no vig), fall back to normalization."""
    p_o, p_u = power_devig(0.48, 0.48)   # sum = 0.96, no vig
    assert abs(p_o - 0.5) < 1e-6


# ── weighted_market_prob ─────────────────────────────────────────────────────

def test_weighted_market_prob_sharp_book_dominates():
    """Pinnacle (weight 0.40) should pull consensus harder than DraftKings (0.15)."""
    book_probs = {
        "pinnacle":   (0.60, 0.40),
        "draftkings": (0.40, 0.60),
    }
    weights = {"pinnacle": 0.40, "draftkings": 0.15}
    p_o, p_u, n = weighted_market_prob(book_probs, weights, default_weight=0.03)
    assert n == 2
    assert p_o > 0.50          # closer to pinnacle's 0.60 than DK's 0.40
    assert abs(p_o + p_u - 1.0) < 1e-9

def test_weighted_market_prob_empty():
    p_o, p_u, n = weighted_market_prob({}, {}, 0.03)
    assert p_o == 0.5 and p_u == 0.5 and n == 0


# ── historical model ─────────────────────────────────────────────────────────

def _nba_stat(row: dict, stat_type: str) -> float | None:
    return row.get(stat_type)

def _make_logs(values: list[float], minutes: float = 32.0) -> list[dict]:
    return [
        {"game_date": f"2025-01-{i+1:02d}", "minutes": minutes,
         "pts": v, "reb": 5.0, "ast": 3.0, "fg3m": 2.0, "blk": 1.0, "stl": 1.0}
        for i, v in enumerate(values)
    ]

def get_pts(row: dict, stat_type: str) -> float | None:
    return row.get("pts")

def test_historical_empty_logs():
    prob, n = compute_hit_rate([], "Points", 20.5, "Over", get_pts)
    assert n == 0
    assert abs(prob - 0.5) < 0.01   # prior mean

def test_historical_beta_prior_anchors_small_sample():
    """One hit out of one game should stay close to 50% thanks to Beta(10,10) prior."""
    logs = _make_logs([25.0])   # one game, above 20.5
    prob, n = compute_hit_rate(logs, "Points", 20.5, "Over", get_pts)
    assert n == 1
    assert 0.50 < prob < 0.56   # prior pulls toward 50%

def test_historical_large_sample_moves_meaningfully():
    """20 hits should push well above the 50% prior."""
    logs = _make_logs([30.0] * 20)
    prob, n = compute_hit_rate(logs, "Points", 20.5, "Over", get_pts)
    assert prob > 0.60

def test_historical_all_misses_below_prior():
    """20 misses should produce a probability below 50%."""
    logs = _make_logs([10.0] * 20)
    prob, _ = compute_hit_rate(logs, "Points", 20.5, "Over", get_pts)
    assert prob < 0.50

def test_historical_rolling_windows():
    """rolling_window_rates returns a dict keyed by window size."""
    logs = _make_logs([25.0] * 5 + [10.0] * 15)
    rates = rolling_window_rates(logs, "Points", 20.5, "Over", get_pts)
    assert 5  in rates
    assert 10 in rates
    assert 20 in rates
    assert rates[5] == 1.0      # first 5 all above line
    assert rates[20] == 0.25    # only 5 of 20 above line


# ── movement signal ──────────────────────────────────────────────────────────

def _snap(book: str, over: int, under: int, minutes_ago: int) -> dict:
    return {
        "book": book,
        "direction": "Over",
        "over_odds": over,
        "under_odds": under,
        "snapshot_at": datetime.now(UTC) - timedelta(minutes=minutes_ago),
    }

def test_movement_no_data_returns_zero():
    assert compute_movement_signal([]) == 0.0

def test_movement_single_snapshot_returns_zero():
    snaps = [_snap("fanduel", -110, -110, 5)]
    assert compute_movement_signal(snaps) == 0.0

def test_movement_fewer_than_min_books_returns_zero():
    """Two books moving — below the 3-book minimum."""
    snaps = [
        _snap("fanduel",    -110, -110, 20),
        _snap("fanduel",    -130, +110, 5),
        _snap("draftkings", -110, -110, 20),
        _snap("draftkings", -130, +110, 5),
    ]
    assert compute_movement_signal(snaps) == 0.0

def test_movement_three_books_fires_signal():
    """Three books all shortening the Over → positive signal."""
    snaps = []
    for book in ("fanduel", "draftkings", "betmgm"):
        snaps.append(_snap(book, -110, -110, 20))   # earlier: balanced
        snaps.append(_snap(book, -140, +120, 5))    # later: Over shortened
    signal = compute_movement_signal(snaps)
    assert signal > 0.0

def test_movement_outside_window_ignored():
    """Moves older than the steam window should not contribute."""
    snaps = []
    for book in ("fanduel", "draftkings", "betmgm"):
        snaps.append(_snap(book, -110, -110, 120))  # 2 hours ago — outside window
        snaps.append(_snap(book, -140, +120, 110))  # also outside window
    # Only the old snapshots exist — nothing in the 30-min window has two time points
    assert compute_movement_signal(snaps) == 0.0

def test_movement_capped_at_ten_pct():
    """Even a huge move should be capped at 0.10."""
    snaps = []
    for book in ("fanduel", "draftkings", "betmgm", "caesars"):
        snaps.append(_snap(book, -100, -100, 25))
        snaps.append(_snap(book, -500, +400, 5))    # extreme move
    signal = compute_movement_signal(snaps)
    assert abs(signal) <= 0.10 * 1.25 + 1e-9   # cap * max sharp boost


# ── blend / EV / Kelly ───────────────────────────────────────────────────────

def test_blend_no_historical_folds_to_market():
    """β=0 means all weight goes to market prob (+ γ*movement)."""
    ev = EVResult(market_prob=0.60, historical_prob=0.50, movement_signal=0.0, sample_n=0)
    assert ev.weights_used["beta"] == 0.0
    # alpha_eff = alpha_market + beta_max = 0.50 + 0.35 = 0.85
    # blended = 0.85*0.60 + 0*0.50 + 0.15*0 = 0.51
    assert abs(ev.blended_prob - 0.51) < 1e-4

def test_blend_full_sample_uses_full_beta():
    ev = EVResult(market_prob=0.50, historical_prob=0.65, movement_signal=0.0, sample_n=20)
    # alpha=0.50, beta=0.35, gamma=0.15
    # blended = 0.50*0.50 + 0.35*0.65 + 0.15*0 = 0.25 + 0.2275 = 0.4775
    assert abs(ev.blended_prob - 0.4775) < 1e-4
    assert ev.weights_used["beta"] == 0.35

def test_blend_clamps_extremes():
    ev = EVResult(market_prob=0.99, historical_prob=0.99, movement_signal=0.10, sample_n=20)
    assert ev.blended_prob <= 0.99

def test_blend_ev_pct_sign():
    """High probability → positive EV; low → negative."""
    high = EVResult(market_prob=0.70, historical_prob=0.70, movement_signal=0.0, sample_n=20)
    low  = EVResult(market_prob=0.40, historical_prob=0.40, movement_signal=0.0, sample_n=20)
    assert high.ev_pct > 0
    assert low.ev_pct < 0

def test_blend_ev_std_nonnegative():
    ev = EVResult(market_prob=0.60, historical_prob=0.55, movement_signal=0.02, sample_n=10)
    assert ev.ev_std >= 0


def test_breakeven_2pick():
    be = breakeven(2)
    assert abs(be - (1/3) ** 0.5) < 1e-6   # sqrt(1/3) ≈ 0.5774

def test_breakeven_3pick():
    be = breakeven(3)
    assert abs(be - (1/5) ** (1/3)) < 1e-6

def test_breakeven_decreasing_then_increasing():
    """Breakeven per pick is not monotone — 4-pick (10x) is lower than 3-pick (5x)."""
    assert breakeven(2) > breakeven(4)


def test_kelly_positive_ev():
    # p=0.65, mult=3.0 → b=2.0 → full=(0.65*3-1)/2=0.475 → half=0.2375 → capped at 0.25
    k = kelly_fraction(0.65, 2)
    assert k == 0.25   # hits the hard cap

def test_kelly_negative_ev_zero():
    assert kelly_fraction(0.40, 2) == 0.0

def test_kelly_half_kelly_applied():
    # p=0.60, mult=2.0 → b=1.0 → full=(0.60*2-1)/1=0.20 → half=0.10
    k = kelly_fraction(0.60, 2)
    # mult=2 is not in our Power Play table; uses default 3.0
    # p=0.60, mult=3.0 → b=2.0 → full=(0.60*3-1)/2=0.40 → half=0.20 → *100 pct
    k = kelly_fraction(0.60, 2)
    assert 0 < k <= 25.0   # returned as percentage, capped at 25%
