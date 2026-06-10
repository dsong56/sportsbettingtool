from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, DateTime, JSON, UniqueConstraint, Boolean
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class OddsSnapshot(Base):
    """One row per book per direction per prop per scrape."""
    __tablename__ = "odds_snapshots"

    id           = Column(Integer, primary_key=True)
    player_name  = Column(String, nullable=False)
    stat_type    = Column(String, nullable=False)
    line_score   = Column(Float, nullable=False)
    sport        = Column(String, nullable=False)
    direction    = Column(String, nullable=False)   # 'Over' | 'Under'
    odds         = Column(Integer, nullable=False)   # American odds
    book         = Column(String, nullable=False)
    snapshot_at  = Column(DateTime, default=datetime.utcnow, nullable=False)


class EVResult(Base):
    """Computed EV for a (player, stat, line, direction) at a point in time."""
    __tablename__ = "ev_results"

    id               = Column(Integer, primary_key=True)
    player_name      = Column(String, nullable=False)
    stat_type        = Column(String, nullable=False)
    line_score       = Column(Float, nullable=False)
    sport            = Column(String, nullable=False)
    direction        = Column(String, nullable=False)
    odds_type        = Column(String, default="standard")  # standard | demon | goblin
    matchup          = Column(String, default="")           # e.g. "DET/BOS"
    market_prob      = Column(Float)   # Shin-devigged weighted market probability
    historical_prob  = Column(Float)   # rolling hit-rate model
    movement_signal  = Column(Float)   # [-1, 1] steam direction
    blended_prob     = Column(Float)   # final weighted blend
    ev_pct           = Column(Float)   # blended_prob - breakeven (2-pick baseline)
    ev_std           = Column(Float)   # std dev across the three signals
    kelly_2pick      = Column(Float)
    kelly_3pick      = Column(Float)
    kelly_4pick      = Column(Float)
    sample_n         = Column(Integer) # game log sample used for historical
    minutes_flag     = Column(Integer, default=0)  # 1 = recent minutes trending down
    computed_at      = Column(DateTime, default=datetime.utcnow, nullable=False)


class Prediction(Base):
    """Every EV result that was surfaced becomes a logged prediction for ML training."""
    __tablename__ = "predictions"

    id             = Column(Integer, primary_key=True)
    player_name    = Column(String, nullable=False)
    stat_type      = Column(String, nullable=False)
    line_score     = Column(Float, nullable=False)
    sport          = Column(String, nullable=False)
    direction      = Column(String, nullable=False)
    predicted_prob = Column(Float, nullable=False)
    market_prob    = Column(Float)
    historical_prob= Column(Float)
    movement_signal= Column(Float)
    predicted_at   = Column(DateTime, default=datetime.utcnow, nullable=False)
    game_date      = Column(String)
    actual_result  = Column(String)    # 'over' | 'under' | None (pending)
    resolved_at    = Column(DateTime)


class GameLogCache(Base):
    """Cached player game logs from stats APIs. Keyed by player + sport + date."""
    __tablename__ = "game_log_cache"
    __table_args__ = (UniqueConstraint("player_name", "sport", "game_date"),)

    id          = Column(Integer, primary_key=True)
    player_name = Column(String, nullable=False)
    sport       = Column(String, nullable=False)
    game_date   = Column(String, nullable=False)   # YYYY-MM-DD
    stats       = Column(JSON, nullable=False)      # full stat line
    cached_at   = Column(DateTime, default=datetime.utcnow, nullable=False)


class NameCorrection(Base):
    """Manual mapping for player name mismatches across data sources."""
    __tablename__ = "name_corrections"
    __table_args__ = (UniqueConstraint("source", "raw_name", "sport"),)

    id             = Column(Integer, primary_key=True)
    source         = Column(String, nullable=False)  # 'prizepicks' | 'fanduel' | etc.
    raw_name       = Column(String, nullable=False)
    canonical_name = Column(String, nullable=False)
    sport          = Column(String, nullable=False)


class ScrapeJob(Base):
    """Tracks async scrape job status for frontend polling."""
    __tablename__ = "scrape_jobs"

    id         = Column(String, primary_key=True)   # UUID
    sport      = Column(String, nullable=False)
    status     = Column(String, default="pending")  # pending | running | done | failed
    error      = Column(String)
    started_at = Column(DateTime)
    finished_at= Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PaperSettings(Base):
    """Single-row table storing the paper trading bankroll state."""
    __tablename__ = "paper_settings"

    id                = Column(Integer, primary_key=True)
    starting_bankroll = Column(Float, nullable=False, default=100.0)
    current_bankroll  = Column(Float, nullable=False, default=100.0)
    updated_at        = Column(DateTime, default=datetime.utcnow, nullable=False)


class PaperBet(Base):
    """A paper-traded parlay (Power Play or Flex Play)."""
    __tablename__ = "paper_bets"

    id               = Column(Integer, primary_key=True)
    play_type        = Column(String, nullable=False)   # 'power' | 'flex'
    n_picks          = Column(Integer, nullable=False)
    picks            = Column(JSON, nullable=False)     # list of pick dicts
    stake            = Column(Float, nullable=False)    # $ amount wagered
    multiplier       = Column(Float, nullable=False)    # e.g. 3.0 for 2-pick power
    potential_payout = Column(Float, nullable=False)    # stake * multiplier (max for flex)
    joint_prob       = Column(Float)                    # estimated probability at placement
    ev_pct           = Column(Float)                    # EV% at placement
    placed_at        = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Settlement
    status           = Column(String, default="pending")  # pending | won | lost | partial
    hits             = Column(Integer)                    # how many picks actually hit
    actual_payout    = Column(Float)                      # 0 if lost, stake*mult if won
    profit_loss      = Column(Float)                      # actual_payout - stake
    bankroll_after   = Column(Float)                      # bankroll snapshot post-settlement
    settled_at       = Column(DateTime)


class SportsbookLine(Base):
    """Best available line per prop across all sportsbooks."""
    __tablename__ = "sportsbook_lines"

    id          = Column(Integer, primary_key=True)
    player_name = Column(String, nullable=False)
    stat_type   = Column(String, nullable=False)
    line_score  = Column(Float, nullable=False)
    sport       = Column(String, nullable=False)
    direction   = Column(String, nullable=False)   # 'Over' | 'Under'
    is_alt      = Column(Boolean, default=False, nullable=False)  # alternate (15+/20+) line
    best_book   = Column(String, nullable=False)   # book offering the best EV
    best_odds   = Column(Integer, nullable=False)  # American odds at best_book
    market_prob = Column(Float)                    # devigged consensus true probability
    ev_pct      = Column(Float)                    # (true_prob * decimal_odds - 1) * 100
    kelly_pct   = Column(Float)                    # half-Kelly % of bankroll
    n_books     = Column(Integer)                  # how many books posted this prop
    computed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
