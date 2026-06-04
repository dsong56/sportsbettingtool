# EV Bets — PrizePicks EV Scanner

A web app that identifies +EV betting opportunities on PrizePicks by cross-referencing player prop lines against sharp sportsbook odds, historical hit rates, and line movement signals. Surfaces optimal Power Play and Flex Play parlays sized by the Kelly criterion.

## How it works

1. **PrizePicks scraper** — pulls live projections directly from the PrizePicks API (no Selenium)
2. **Odds API scraper** — fetches player prop odds from major sportsbooks for NBA, NHL, and MLB
3. **EV engine** — for each matching prop:
   - **Shin/power-method devigging** — removes the sportsbook vig to recover the true implied probability, weighted by book sharpness (sharp books like DraftKings/FanDuel weighted by signal quality)
   - **Historical hit rate model** — exponential-decay weighted hit rate against the exact line, with Beta(10,10) prior for regression-to-mean and a minutes filter to exclude injury/blowout games
   - **Steam detection** — fires when ≥3 books move in the same direction within a 30-minute window, with a boost when a sharp book initiates the move
   - **Blended probability** — market signal + historical signal + movement nudge, with weights that scale dynamically with sample size
4. **Parlay optimizer** — recommends optimal Power Play and Flex Play combinations sized by half-Kelly criterion

## Supported sports

- NBA (Points, Rebounds, Assists, 3-PT Made, Blocks, Steals, combo markets)
- NHL (Shots on Goal, Saves, Points, Blocked Shots, Assists, Goals)
- MLB (Hits, Total Bases, RBIs, Runs, Singles, Doubles, Pitcher Strikeouts, Pitcher Outs, Hits+Runs+RBIs)

## Features

- **EV table** — sortable by EV%, color-coded green/yellow/gray, with confidence bands (±σ)
- **Signal badges** — shows whether market, historical, and movement signals agree
- **Demon/Goblin support** — identifies PrizePicks bet types; Under direction suppressed for demon/goblin props
- **Matchup info** — game date and opponent shown per prop
- **Sparklines** — odds movement history per prop
- **Parlay optimizer** — Power Play (2–5 pick) and Flex Play (3–6 pick) recommendations with full outcome breakdowns for Flex
- **Kelly sizing** — half-Kelly bet sizing per parlay tier with breakeven thresholds

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- API keys:
  - [The Odds API](https://the-odds-api.com) (free tier: 500 requests/month)
  - [BallDontLie](https://www.balldontlie.io) (free tier, NBA game logs)

### Backend

```bash
git clone https://github.com/dsong56/sportsbettingtool.git
cd sportsbettingtool

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

pip install -r requirements.txt

copy .env.example .env        # Windows
# cp .env.example .env        # Mac/Linux
# Edit .env and add your API keys

uvicorn backend.main:app --reload
```

Backend runs at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`.

### Environment variables

```env
ODDS_API_KEY=your_odds_api_key
BALLDONTLIE_API_KEY=your_balldontlie_key
DATABASE_URL=sqlite+aiosqlite:///./ev_bets.db
```

## Usage

1. Open `http://localhost:5173`
2. Select a sport (NBA, NHL, MLB)
3. Hit **Refresh** — fetches live PrizePicks lines and sportsbook odds (30–60 seconds)
4. Props populate sorted by EV%, with the Parlay Optimizer above the table
5. Click any row to expand full signal breakdown, sparkline, and Kelly sizing

## Configuration

All model parameters are in [`backend/config.py`](backend/config.py):

- **Book weights** — sharpness-based weighting per sportsbook
- **Blend weights** — α (market), β (historical), γ (movement) and ramp schedule
- **Beta prior** — regression-to-mean strength for hit rate model
- **Steam detection** — minimum books, time window, sharp-book boost
- **Power Play / Flex Play multipliers** — update if PrizePicks changes payouts
- **Kelly** — half-Kelly multiplier and hard cap

## Architecture

```
backend/
├── main.py                 FastAPI app
├── config.py               All tunables in one place
├── scrapers/
│   ├── prizepicks.py       PrizePicks API client (httpx)
│   └── odds_api.py         The Odds API client (async batched)
├── stats/
│   ├── nba.py              BallDontLie game logs
│   ├── nhl.py              NHL Stats API (official, free)
│   └── mlb.py              MLB Stats API (official, free)
├── ev/
│   ├── shin.py             Power-method devigging (scipy brentq)
│   ├── historical.py       Decay-weighted hit rate + Beta prior
│   ├── movement.py         Steam detection
│   ├── blend.py            Signal blending + Kelly + breakevens
│   └── pipeline.py         Full scrape → EV → DB pipeline
├── routers/
│   ├── props.py            GET /api/props
│   ├── jobs.py             POST /api/refresh, GET /api/jobs/{id}
│   └── admin.py            Name corrections, outcome logging
├── db/
│   ├── models.py           SQLAlchemy ORM models
│   └── database.py         Async SQLite engine
├── jobs/
│   └── resolver.py         Nightly auto-resolution of predictions
└── tests/
    └── test_ev.py          Pytest suite for EV math

frontend/
└── src/
    ├── components/
    │   ├── PropTable.tsx        Sortable EV table
    │   ├── PropCard.tsx         Expanded prop detail
    │   ├── ParlayOptimizer.tsx  Power Play + Flex Play optimizer
    │   ├── Sparkline.tsx        Odds history chart
    │   ├── SignalBadge.tsx      Signal agreement indicator
    │   ├── OddsTypeBadge.tsx    Demon / Goblin / Standard badge
    │   ├── KellyDisplay.tsx     Kelly sizing bars
    │   └── Toast.tsx            Notification toasts
    └── pages/
        └── Dashboard.tsx        Main page
```

## Notes

- The Odds API free tier allows ~500 requests/month. Each refresh uses 10–20 requests depending on how many games are active.
- Flex Play payout multipliers in `frontend/src/components/ParlayOptimizer.tsx` should be verified against the current PrizePicks payout table before use — they change periodically.
- The ML layer (LightGBM) activates once the `predictions` table accumulates ~500 resolved outcomes. Until then, fixed blend weights are used. The nightly resolver job automatically logs outcomes by querying the stats APIs.
- Market efficiency is highest on popular players. Edge tends to come from lower-profile props where books price lazily.
