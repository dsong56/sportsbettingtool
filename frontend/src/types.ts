export type OddsType = 'standard' | 'demon' | 'goblin'

export interface PropResult {
  player_name:     string
  stat_type:       string
  line_score:      number
  sport:           string
  direction:       'Over' | 'Under'
  odds_type:       OddsType
  game_date:       string
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
  credits_remaining?: string | null
}

export interface SportsbookLineRow {
  player_name:       string
  stat_type:         string
  line_score:        number
  sport:             string
  direction:         'Over' | 'Under'
  book:              string
  odds:              number
  fair_odds:         number
  consensus_prob:    number
  historical_prob:   number
  ev_pct:            number
  kelly_pct:         number
  n_books_consensus: number
  computed_at:       string
}

export type Sport = 'NBA' | 'NHL' | 'MLB' | 'NFL'

export interface BetLog {
  id:                    number
  player_name:           string
  stat_type:             string
  line_score:            number
  sport:                 string
  direction:             'Over' | 'Under'
  odds_type:             OddsType
  pick_count:            number
  stake_pct:             number
  game_date:             string | null
  ev_pct_at_entry:       number | null
  blended_prob_at_entry: number | null
  actual_result:         'over' | 'under' | null
  settled_at:            string | null
  created_at:            string
}

export interface BetInput {
  player_name: string
  stat_type:   string
  line_score:  number
  sport:       string
  direction:   'Over' | 'Under'
  pick_count:  number
  stake_pct:   number
}

export interface CalibrationBucket {
  prob_bin:      number
  predicted_avg: number
  actual_rate:   number
  count:         number
}

export interface SignalAttribution {
  market_correlation:     number | null
  market_n:               number
  historical_correlation: number | null
  historical_n:           number
  movement_correlation:   number | null
  movement_n:             number
}

export interface RollingAccuracyPoint {
  date:     string
  win_rate: number
  count:    number
}

export interface MlStatus {
  active:       boolean
  model_exists: boolean
  min_required: number
}

export interface PredictionsSummary {
  total_resolved:      number
  win_rate:            number
  brier_score:         number
  calibration_buckets: CalibrationBucket[]
  signal_attribution:  SignalAttribution
  rolling_accuracy:    RollingAccuracyPoint[]
  ml:                  MlStatus
}

export interface UnresolvedPrediction {
  id:             number
  player_name:    string
  stat_type:      string
  line_score:     number
  sport:          string
  direction:      'Over' | 'Under'
  game_date:      string | null
  predicted_prob: number
}

export interface TrainResult {
  trained:   boolean
  n_samples: number
  accuracy:  number
}
