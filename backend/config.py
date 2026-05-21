import os
from dotenv import load_dotenv

load_dotenv()

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")

# Sportsbook market-cap weights (sharp books weighted higher)
BOOK_WEIGHTS: dict[str, float] = {
    "FanDuel":    34.04,
    "DraftKings": 17.18,
    "BetMGM":     12.37,
    "Caesars":    7.67,
    "BetRivers":  2.01,
}

# Books excluded from weighted average (private/offshore, lower signal)
PRIVATE_BOOKS: set[str] = {"MyBookie.ag", "BetOnline.ag", "Bovada", "SuperBook"}

# PrizePicks league IDs
LEAGUE_IDS: dict[str, int] = {
    "NBA": 7,
    "NHL": 8,
    "MLB": 2,
}

# PrizePicks Power Play payout multipliers (update if PrizePicks changes them)
# breakeven per pick = (1/multiplier)^(1/n_picks)
POWER_PLAY_MULTIPLIERS: dict[int, float] = {
    2: 3.0,
    3: 5.0,
    4: 10.0,
    5: 20.0,
    6: 25.0,
}

# Blend weights — converge as sample size grows
# α (market) + β (historical) + γ (movement) = 1
# β scales with sample size: β_effective = BETA_MAX * min(n / BETA_RAMP_N, 1)
# remainder goes to α so γ stays fixed
ALPHA_BASE  = 0.85   # market weight when n=0
BETA_MAX    = 0.35   # max historical weight (reached at n >= BETA_RAMP_N)
GAMMA       = 0.15   # movement weight (fixed)
BETA_RAMP_N = 20     # sample size at which β reaches max

# Beta(a, b) prior for hit-rate regression to mean
# Beta(10,10) → prior centered at 50% with weight of 20 synthetic games
BETA_PRIOR_A = 10
BETA_PRIOR_B = 10

# Rolling windows for historical hit rate (games)
ROLLING_WINDOWS = [5, 10, 20]
# Exponential decay half-life in games (more recent = more weight)
EXP_DECAY_HALFLIFE = 5

# Steam detection: minimum books that must move in same direction
STEAM_MIN_BOOKS = 3

# Minutes filter: exclude games where player played outside ±N std devs of season avg
MINUTES_FILTER_STD = 1.0

# Minimum EV% to include in default response (clients can override)
DEFAULT_MIN_EV = 0.0

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./ev_bets.db")
