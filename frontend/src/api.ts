import axios from 'axios'
import type { PropResult, OddsPoint, Job, Sport } from './types'

const http = axios.create({ baseURL: '/api' })

export async function fetchProps(params: {
  sport?: Sport
  stat_type?: string
  direction?: string
  min_ev?: number
}): Promise<PropResult[]> {
  const { data } = await http.get<PropResult[]>('/props', { params })
  return data
}

export async function fetchOddsHistory(params: {
  player_name: string
  stat_type:   string
  line_score:  number
  sport:       Sport
  direction:   string
}): Promise<OddsPoint[]> {
  const { data } = await http.get<OddsPoint[]>('/props/history', { params })
  return data
}

export async function fetchBreakevens(): Promise<Record<string, number>> {
  const { data } = await http.get<Record<string, number>>('/props/breakevens')
  return data
}

export async function triggerRefresh(sport: Sport): Promise<Job> {
  const { data } = await http.post<Job>(`/refresh/${sport}`)
  return data
}

export async function pollJob(jobId: string): Promise<Job> {
  const { data } = await http.get<Job>(`/jobs/${jobId}`)
  return data
}

export async function fetchSportsbookLines(params: {
  sport?:     string
  stat_type?: string
  direction?: string
  book?:      string
  min_ev?:    number
}): Promise<import('./types').SportsbookLine[]> {
  const { data } = await http.get('/lines', { params })
  return data
}

export async function triggerLinesRefresh(sport: string): Promise<Job> {
  const { data } = await http.post<Job>(`/lines/refresh/${sport}`)
  return data
}

export async function pollLinesJob(jobId: string): Promise<Job> {
  const { data } = await http.get<Job>(`/jobs/${jobId}`)
  return data
}

// ── Paper trading ─────────────────────────────────────────────────────────────

export interface PaperPick {
  player_name:  string
  stat_type:    string
  line_score:   number
  direction:    string
  sport:        string
  odds_type:    string
  blended_prob: number
  game_date?:   string
  matchup:      string
}

export interface PlaceBetPayload {
  play_type:   string
  n_picks:     number
  picks:       PaperPick[]
  stake:       number
  multiplier:  number
  joint_prob:  number
  ev_pct:      number
}

export interface PaperBet {
  id:               number
  play_type:        string
  n_picks:          number
  picks:            PaperPick[]
  stake:            number
  multiplier:       number
  potential_payout: number
  joint_prob:       number | null
  ev_pct:           number | null
  placed_at:        string
  status:           'pending' | 'won' | 'lost' | 'partial' | 'cancelled'
  hits:             number | null
  actual_payout:    number | null
  profit_loss:      number | null
  bankroll_after:   number | null
  settled_at:       string | null
}

export interface PaperSummary {
  current_bankroll:  number
  starting_bankroll: number
  total_pl:          number
  roi_pct:           number
  total_bets:        number
  wins:              number
  losses:            number
  win_rate:          number
  pending_bets:      number
  pending_at_risk:   number
  bankroll_history:  { date: string; bankroll: number }[]
  by_type:           { play_type: string; n_picks: number; bets: number; wins: number; staked: number; payout: number }[]
}

export async function placePaperBet(payload: PlaceBetPayload): Promise<PaperBet & { current_bankroll: number }> {
  const { data } = await http.post('/paper/bets', payload)
  return data
}

export async function fetchPaperBets(status?: string): Promise<PaperBet[]> {
  const { data } = await http.get('/paper/bets', { params: status ? { status } : {} })
  return data
}

export async function cancelPaperBet(id: number): Promise<void> {
  await http.delete(`/paper/bets/${id}`)
}

export async function fetchPaperSummary(): Promise<PaperSummary> {
  const { data } = await http.get('/paper/summary')
  return data
}

export async function resetPaperBankroll(): Promise<void> {
  await http.post('/paper/reset')
}

export async function updatePaperSettings(starting_bankroll: number): Promise<void> {
  await http.put('/paper/settings', { starting_bankroll })
}
