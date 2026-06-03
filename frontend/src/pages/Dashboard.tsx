import { useState, useEffect, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchProps, triggerRefresh, pollJob } from '../api'
import PropTable from '../components/PropTable'
import type { Sport, PropResult } from '../types'

const SPORTS: Sport[] = ['NBA', 'NHL', 'MLB']

const SPORT_STATS: Record<Sport, string[]> = {
  NBA: ['All', 'Points', 'Rebounds', 'Assists', '3-PT Made', 'Blocked Shots', 'Steals', 'Pts+Rebs+Asts', 'Pts+Rebs', 'Pts+Asts', 'Rebs+Asts'],
  NHL: ['All', 'Shots on Goal', 'Saves', 'Points', 'Blocked Shots', 'Assists', 'Goals'],
  MLB: ['All', 'Pitcher Strikeouts', 'Total Bases', 'Hits Allowed', 'Pitcher Outs', 'Hits+Runs+RBIs'],
}

type JobStatus = 'idle' | 'pending' | 'running' | 'done' | 'failed'

function StatPill({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-3 text-center">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-xl font-bold text-white">{value}</p>
      {sub && <p className="text-xs text-gray-600 mt-0.5">{sub}</p>}
    </div>
  )
}

function SportTab({ sport, active, onClick }: { sport: Sport; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`px-5 py-2 rounded-lg text-sm font-semibold transition-colors ${
        active
          ? 'bg-indigo-600 text-white'
          : 'text-gray-400 hover:text-white hover:bg-gray-800'
      }`}
    >
      {sport}
    </button>
  )
}

function RefreshButton({ status, onClick }: { status: JobStatus; onClick: () => void }) {
  const busy = status === 'pending' || status === 'running'
  return (
    <button
      onClick={onClick}
      disabled={busy}
      className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${
        busy
          ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
          : 'bg-indigo-600 hover:bg-indigo-500 text-white'
      }`}
    >
      {busy ? (
        <>
          <span className="inline-block w-3.5 h-3.5 border-2 border-gray-500 border-t-indigo-400 rounded-full animate-spin" />
          {status === 'pending' ? 'Queued…' : 'Fetching…'}
        </>
      ) : (
        <>
          <span>↻</span> Refresh
        </>
      )}
    </button>
  )
}

export default function Dashboard() {
  const qc = useQueryClient()

  const [sport, setSport]         = useState<Sport>('NBA')
  const [statType, setStatType]   = useState('All')
  const [direction, setDirection] = useState('All')
  const [minEv, setMinEv]         = useState(0)
  const [jobId, setJobId]         = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<JobStatus>('idle')

  // Reset stat filter when sport changes
  useEffect(() => { setStatType('All') }, [sport])

  const { data: props = [], isFetching } = useQuery<PropResult[]>({
    queryKey: ['props', sport, statType, direction, minEv],
    queryFn: () => fetchProps({
      sport,
      stat_type:  statType === 'All' ? undefined : statType,
      direction:  direction === 'All' ? undefined : direction,
      min_ev:     minEv,
    }),
    staleTime: 60_000,
  })

  // Poll job status until done/failed
  const pollOnce = useCallback(async (id: string) => {
    const job = await pollJob(id)
    setJobStatus(job.status as JobStatus)
    if (job.status === 'done') {
      qc.invalidateQueries({ queryKey: ['props'] })
      setJobId(null)
    } else if (job.status === 'failed') {
      setJobId(null)
    }
  }, [qc])

  useEffect(() => {
    if (!jobId) return
    const interval = setInterval(() => pollOnce(jobId), 2500)
    return () => clearInterval(interval)
  }, [jobId, pollOnce])

  const handleRefresh = async () => {
    setJobStatus('pending')
    const job = await triggerRefresh(sport)
    setJobId(job.job_id)
  }

  // Summary stats
  const positiveEv  = props.filter(p => p.ev_pct >= 3).length
  const marginalEv  = props.filter(p => p.ev_pct >= 1 && p.ev_pct < 3).length
  const bestEv      = props.length ? Math.max(...props.map(p => p.ev_pct)) : 0
  const allAgree    = props.filter(p => {
    const isOver = p.direction === 'Over'
    const mkt  = isOver ? p.market_prob > 0.5 : p.market_prob < 0.5
    const hist = isOver ? p.historical_prob > 0.5 : p.historical_prob < 0.5
    const mov  = Math.abs(p.movement_signal) > 0.05
      ? (isOver ? p.movement_signal > 0 : p.movement_signal < 0)
      : null
    return mkt && hist && (mov === null || mov)
  }).length

  return (
    <div className="min-h-screen bg-gray-950 text-gray-200">

      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/60 backdrop-blur sticky top-0 z-10">
        <div className="max-w-screen-xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="text-2xl font-bold text-white tracking-tight">EV Bets</span>
            <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded-full">PrizePicks</span>
          </div>
          <div className="flex items-center gap-2">
            {SPORTS.map(s => (
              <SportTab key={s} sport={s} active={sport === s} onClick={() => setSport(s)} />
            ))}
          </div>
          <RefreshButton status={jobStatus} onClick={handleRefresh} />
        </div>
      </header>

      <main className="max-w-screen-xl mx-auto px-6 py-6 space-y-6">

        {/* Summary pills */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatPill label="Total props"    value={props.length} />
          <StatPill label="Strong EV (≥3%)" value={positiveEv}  sub="green rows" />
          <StatPill label="Marginal (1–3%)" value={marginalEv}  sub="yellow rows" />
          <StatPill label="All-signal agree" value={allAgree}  sub={bestEv > 0 ? `Best: +${bestEv.toFixed(1)}%` : '—'} />
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Stat type */}
          <select
            value={statType}
            onChange={e => setStatType(e.target.value)}
            className="bg-gray-900 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            {SPORT_STATS[sport].map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>

          {/* Direction */}
          <select
            value={direction}
            onChange={e => setDirection(e.target.value)}
            className="bg-gray-900 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="All">Over &amp; Under</option>
            <option value="Over">Over only</option>
            <option value="Under">Under only</option>
          </select>

          {/* Min EV */}
          <div className="flex items-center gap-2">
            <label className="text-xs text-gray-500 whitespace-nowrap">Min EV%</label>
            <input
              type="number"
              min={-20}
              max={20}
              step={0.5}
              value={minEv}
              onChange={e => setMinEv(parseFloat(e.target.value) || 0)}
              className="w-20 bg-gray-900 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          {isFetching && (
            <span className="text-xs text-gray-500 flex items-center gap-1.5">
              <span className="inline-block w-3 h-3 border-2 border-gray-700 border-t-indigo-500 rounded-full animate-spin" />
              Loading…
            </span>
          )}

          {jobStatus === 'failed' && (
            <span className="text-xs text-red-400 bg-red-500/10 border border-red-500/30 px-3 py-1.5 rounded-lg">
              Refresh failed — check your API key
            </span>
          )}
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 text-xs text-gray-600">
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-emerald-500/30" /> ≥ 3% EV
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-yellow-500/20" /> 1–3% EV
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-gray-800" /> &lt; 1% EV
          </span>
          <span className="text-gray-700">· Click any row to expand details</span>
        </div>

        {/* Main table */}
        <PropTable props={props} />

        {/* Empty state when no data has been fetched yet */}
        {props.length === 0 && !isFetching && (
          <div className="text-center py-20 text-gray-600 space-y-3">
            <p className="text-4xl">📊</p>
            <p className="text-lg font-medium text-gray-500">No data yet</p>
            <p className="text-sm">Hit <span className="text-indigo-400">Refresh</span> to pull live PrizePicks lines and sportsbook odds for {sport}.</p>
          </div>
        )}
      </main>
    </div>
  )
}
