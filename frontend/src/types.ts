export type OddsType = 'standard' | 'demon' | 'goblin'

export interface PropResult {
  player_name:     string
  stat_type:       string
  line_score:      number
  sport:           string
  direction:       'Over' | 'Under'
  odds_type:       OddsType
  game_date?:      string   // not persisted in DB, only present immediately after scrape
  matchup:         string
  market_prob:     number
  historical_prob: number
  movement_signal: number
  blended_prob:    number
  ev_pct:          number   // percentage points, e.g. 3.4 means 3.4%
  ev_std:          number   // std dev across signals, same units
  kelly_2pick:     number   // percentage of bankroll, e.g. 5.2 means 5.2%
  kelly_3pick:     number
  kelly_4pick:     number
  sample_n:        number
  minutes_flag:    boolean
  roll_l5:         number
  roll_l10:        number
  roll_l20:        number
  breakeven_2pick: number
  breakeven_3pick: number
  breakeven_4pick: number
  computed_at:     string
}

export interface OddsPoint {
  timestamp: string
  avg_odds:  number
}

export interface Job {
  job_id:      string
  sport:       string
  status:      'pending' | 'running' | 'done' | 'failed'
  error?:      string
  started_at?: string
  finished_at?: string
}

export type Sport = 'NBA' | 'NHL' | 'MLB'

export interface SportsbookLine {
  player_name: string
  stat_type:   string
  line_score:  number
  sport:       string
  direction:   'Over' | 'Under'
  is_alt:      boolean  // alternate (15+/20+) line vs the book's main line
  best_book:   string
  best_odds:   number   // American
  market_prob: number
  ev_pct:      number
  kelly_pct:   number
  n_books:     number
  computed_at: string
}
