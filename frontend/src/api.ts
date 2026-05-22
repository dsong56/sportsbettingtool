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
