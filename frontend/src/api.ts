import axios from 'axios'
import type {
  PropResult, OddsPoint, Job, Sport,
  BetLog, BetInput, PredictionsSummary, UnresolvedPrediction, TrainResult,
} from './types'

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

export async function fetchBets(status: 'all' | 'open' | 'settled' = 'all'): Promise<BetLog[]> {
  const { data } = await http.get<BetLog[]>('/bets', { params: { status } })
  return data
}

export async function createBet(bet: BetInput): Promise<BetLog> {
  const { data } = await http.post<BetLog>('/bets', bet)
  return data
}

export async function fetchPredictionsSummary(): Promise<PredictionsSummary> {
  const { data } = await http.get<PredictionsSummary>('/predictions/summary')
  return data
}

export async function fetchUnresolvedPredictions(): Promise<UnresolvedPrediction[]> {
  const { data } = await http.get<UnresolvedPrediction[]>('/predictions/unresolved')
  return data
}

export async function resolvePrediction(predId: number, actualResult: 'over' | 'under'): Promise<void> {
  await http.post(`/admin/outcomes/${predId}`, { actual_result: actualResult })
}

export async function trainMlModel(): Promise<TrainResult> {
  const { data } = await http.post<TrainResult>('/admin/train')
  return data
}
