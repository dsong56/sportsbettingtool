from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- External APIs ---
    odds_api_key: str = ""
    balldontlie_api_key: str = ""

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./ev_bets.db"

    # --- Book weights (sharpness-based, NOT market-cap-based) ---
    # Pinnacle and Circa set lines; retail books follow. Weight accordingly.
    # If a book isn't listed, it gets book_weight_default.
    book_weights: dict[str, float] = {
        "pinnacle":    0.40,
        "circa":       0.30,
        "draftkings":  0.15,
        "fanduel":     0.15,
        "betmgm":      0.05,
        "caesars":     0.05,
        "betrivers":   0.03,
    }
    book_weight_default: float = 0.03

    # Books excluded from weighted average entirely (offshore/private, low signal)
    private_books: set[str] = {"mybookie.ag", "betonline.ag", "bovada", "superbook"}

    # --- PrizePicks league IDs ---
    league_ids: dict[str, int] = {"NBA": 7, "NHL": 8, "MLB": 2}

    # --- PrizePicks Power Play payout multipliers ---
    # breakeven_per_pick(n) = (1 / multiplier)^(1/n)
    power_play_multipliers: dict[int, float] = {
        2: 3.0,
        3: 5.0,
        4: 10.0,
        5: 20.0,
        6: 25.0,
    }

    # --- Blend weights ---
    # α (market) is the anchor. β scales up with sample size; remainder → α.
    # γ is applied as a multiplier on the additive movement nudge.
    alpha_market: float       = 0.50
    beta_historical_max: float = 0.35
    gamma_movement: float     = 0.15
    historical_full_sample: int = 20  # n games where β reaches β_max

    # --- Beta prior for hit-rate regression-to-mean ---
    # Beta(10, 10) → 10 synthetic overs + 10 unders before real data
    beta_prior_overs: float  = 10.0
    beta_prior_unders: float = 10.0

    # --- Exponential decay for recent games ---
    decay_lambda: float = 0.10  # weight = exp(-lambda * games_ago)

    # --- Minutes filter ---
    minutes_std_threshold: float = 1.0  # exclude games >1σ off player's mean

    # --- Steam detection ---
    steam_min_books: int      = 3
    steam_window_minutes: int = 30
    steam_noise_floor: float  = 0.005   # ignore moves < 0.5pp implied prob
    steam_sharp_boost: float  = 1.25    # boost signal when sharp book moved first

    # --- Alternate lines (15+ / 20+ style markets) ---
    # Alternate markets are usually quoted one-sided (Over only), so there's no
    # Under price to devig against. We borrow the book's vig exponent k from its
    # main line on the same prop; if the book has no main line, we fall back to
    # dividing by a typical per-book overround.
    include_alt_lines: bool = True
    alt_min_books: int = 2              # min books in consensus before trusting an alt line
    alt_fallback_overround: float = 1.06  # assumed two-way overround when no main line exists

    # --- Kelly ---
    kelly_fraction_multiplier: float = 0.5   # half-Kelly for safety
    kelly_max: float = 0.25                  # hard cap regardless

    # --- Frontend EV thresholds ---
    ev_threshold_green: float  = 3.0   # %
    ev_threshold_yellow: float = 1.0   # %

    # --- Fuzzy name matching ---
    name_match_threshold: int = 80    # rapidfuzz score 0-100
    name_match_warn_below: float = 0.85

    # --- ML migration ---
    use_ml_model: bool = False
    ml_min_resolved_predictions: int = 500


settings = Settings()

# Convenience re-exports used throughout the codebase
BOOK_WEIGHTS        = settings.book_weights
BOOK_WEIGHT_DEFAULT = settings.book_weight_default
PRIVATE_BOOKS       = settings.private_books
LEAGUE_IDS          = settings.league_ids
POWER_PLAY_MULTIPLIERS = settings.power_play_multipliers
ODDS_API_KEY        = settings.odds_api_key
DATABASE_URL        = settings.database_url
