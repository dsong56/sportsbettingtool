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
