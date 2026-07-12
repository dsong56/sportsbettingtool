from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, DateTime, JSON, UniqueConstraint
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
    game_date        = Column(String)                       # YYYY-MM-DD
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
    roll_l5          = Column(Float)   # last-5 hit rate, percent
    roll_l10         = Column(Float)
    roll_l20         = Column(Float)
    breakeven_2pick  = Column(Float)   # breakeven per-pick prob, percent
    breakeven_3pick  = Column(Float)
    breakeven_4pick  = Column(Float)
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
    sample_n       = Column(Integer)   # historical sample size, an ML feature
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


class BetLog(Base):
    """A bet the user actually placed, snapshotted at entry for portfolio tracking."""
    __tablename__ = "bet_logs"

    id                     = Column(Integer, primary_key=True)
    player_name            = Column(String, nullable=False)
    stat_type              = Column(String, nullable=False)
    line_score             = Column(Float, nullable=False)
    sport                  = Column(String, nullable=False)
    direction              = Column(String, nullable=False)   # 'Over' | 'Under'
    odds_type              = Column(String, default="standard")
    pick_count             = Column(Integer, nullable=False)  # 2 | 3 | 4
    stake_pct              = Column(Float, nullable=False)    # Kelly % used
    game_date              = Column(String)                   # YYYY-MM-DD
    ev_pct_at_entry        = Column(Float)
    blended_prob_at_entry  = Column(Float)
    actual_result          = Column(String)    # 'over' | 'under' | None (open)
    settled_at             = Column(DateTime)
    created_at             = Column(DateTime, default=datetime.utcnow, nullable=False)


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
    credits_remaining = Column(String)   # Odds API quota left after this scrape


class SportsbookLine(Base):
    """
    A single book's price on a prop, scored against the sharp consensus of the
    OTHER books at the same line. Positive ev_pct = this book's price is soft.
    """
    __tablename__ = "sportsbook_lines"

    id              = Column(Integer, primary_key=True)
    player_name     = Column(String, nullable=False)
    stat_type       = Column(String, nullable=False)
    line_score      = Column(Float, nullable=False)
    sport           = Column(String, nullable=False)
    direction       = Column(String, nullable=False)   # 'Over' | 'Under'
    book            = Column(String, nullable=False)
    odds            = Column(Integer, nullable=False)  # American odds offered
    consensus_prob  = Column(Float)    # devigged, sharp-weighted, excl. this book
    ev_pct          = Column(Float)    # (consensus_prob × decimal − 1) × 100
    kelly_pct       = Column(Float)    # half-Kelly at the offered price, %
    historical_prob = Column(Float)    # player hit rate at this line, for context
    n_books_consensus = Column(Integer)
    computed_at     = Column(DateTime, default=datetime.utcnow, nullable=False)
