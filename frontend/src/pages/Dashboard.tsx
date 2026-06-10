import { useState, useEffect, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchProps, triggerRefresh, pollJob, fetchSportsbookLines, triggerLinesRefresh } from '../api'
import PropTable from '../components/PropTable'
import ParlayOptimizer from '../components/ParlayOptimizer'
import SportsbookTable from '../components/SportsbookTable'
import BetSlip from '../components/BetSlip'
import Toast from '../components/Toast'
import { fetchPaperSummary } from '../api'
import type { Sport, PropResult } from '../types'

type Mode = 'prizepicks' | 'sportsbooks'

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

export default function Dashboard({ onNavigatePortfolio }: { onNavigatePortfolio?: () => void }) {
  const qc = useQueryClient()

  const [sport, setSport]         = useState<Sport>('NBA')
  const [statType, setStatType]   = useState('All')
  const [direction, setDirection] = useState('All')
  const [minEv, setMinEv]         = useState(-100)
  const [jobId, setJobId]         = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<JobStatus>('idle')
  const [jobError, setJobError]   = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<string | null>(null)
  const [toast, setToast]         = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  const [slipPicks, setSlipPicks] = useState<PropResult[]>([])
  const [mode, setMode]           = useState<Mode>('prizepicks')

  const { data: paperSummary } = useQuery({
    queryKey: ['paper-summary'],
    queryFn: fetchPaperSummary,
    staleTime: 30_000,
  })

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

  const { data: sbLines = [], isFetching: sbFetching } = useQuery({
    queryKey: ['sportsbook-lines', sport],
    queryFn: () => fetchSportsbookLines({ sport }),
    staleTime: 60_000,
    enabled: mode === 'sportsbooks',
  })

  // Poll job status until done/failed
  const pollOnce = useCallback(async (id: string) => {
    const job = await pollJob(id)
    setJobStatus(job.status as JobStatus)
    if (job.status === 'done') {
      qc.refetchQueries({ queryKey: mode === 'prizepicks' ? ['props'] : ['sportsbook-lines'] })
      setJobId(null)
      setJobError(null)
      setLastUpdated(new Date().toLocaleTimeString())
      setToast({ message: `${job.sport} props updated successfully`, type: 'success' })
    } else if (job.status === 'failed') {
      const err = job.error ?? 'Unknown error'
      setJobError(err)
      setJobId(null)
      setToast({ message: err, type: 'error' })
    }
  }, [qc])

  useEffect(() => {
    if (!jobId) return
    let polls = 0
    const MAX_POLLS = 72  // 3 minutes at 2.5s intervals
    const interval = setInterval(() => {
      polls++
      if (polls > MAX_POLLS) {
        clearInterval(interval)
        setJobStatus('failed')
        setJobError('Refresh timed out after 3 minutes — the scrape may still be running in the background')
        setJobId(null)
        return
      }
      pollOnce(jobId)
    }, 2500)
    return () => clearInterval(interval)
  }, [jobId, pollOnce])

  const handleRefresh = async () => {
    setJobStatus('pending')
    setJobError(null)
    const job = mode === 'prizepicks'
      ? await triggerRefresh(sport)
      : await triggerLinesRefresh(sport)
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

      {/* Sport selector + controls bar */}
      <div className="border-b border-gray-800 bg-gray-900/60 backdrop-blur sticky top-12 z-10">
        <div className="max-w-screen-xl mx-auto px-6 py-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            {/* Mode toggle */}
            <div className="flex items-center bg-gray-800 rounded-lg p-1 gap-1">
              <button
                onClick={() => setMode('prizepicks')}
                className={`px-3 py-1 rounded-md text-xs font-semibold transition-colors ${
                  mode === 'prizepicks' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
                }`}
              >
                PrizePicks
              </button>
              <button
                onClick={() => setMode('sportsbooks')}
                className={`px-3 py-1 rounded-md text-xs font-semibold transition-colors ${
                  mode === 'sportsbooks' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
                }`}
              >
                Sportsbooks
              </button>
            </div>
            {/* Sport tabs */}
            <div className="flex items-center gap-2">
              {SPORTS.map(s => (
                <SportTab key={s} sport={s} active={sport === s} onClick={() => setSport(s)} />
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            {lastUpdated && (
              <span className="text-xs text-gray-500">Last updated {lastUpdated}</span>
            )}
            {onNavigatePortfolio && (
              <button
                onClick={onNavigatePortfolio}
                className="text-xs text-indigo-400 hover:text-indigo-300 border border-indigo-900 hover:border-indigo-700 px-3 py-1.5 rounded-lg transition-colors"
              >
                Portfolio →
              </button>
            )}
            <RefreshButton status={jobStatus} onClick={handleRefresh} />
          </div>
        </div>
      </div>

      <main className="max-w-screen-xl mx-auto px-6 py-6 space-y-6">

        {/* Summary pills */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatPill label="Total props"    value={props.length} />
          <StatPill label="Strong EV (≥3%)" value={positiveEv}  sub="green rows" />
          <StatPill label="Marginal (1–3%)" value={marginalEv}  sub="yellow rows" />
          <StatPill label="All-signal agree" value={allAgree}  sub={bestEv > 0 ? `Best: +${bestEv.toFixed(1)}%` : '—'} />
        </div>

        {mode === 'prizepicks' ? (
          <>
            {/* Parlay optimizer */}
            <ParlayOptimizer
              props={props}
              currentBankroll={paperSummary?.current_bankroll ?? 100}
              onBetPlaced={() => {
                qc.invalidateQueries({ queryKey: ['paper-summary'] })
                setToast({ message: 'Paper bet placed!', type: 'success' })
              }}
            />

            {/* Filters */}
            <div className="flex flex-wrap items-center gap-3">
              <select value={statType} onChange={e => setStatType(e.target.value)}
                className="bg-gray-900 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500">
                {SPORT_STATS[sport].map(s => <option key={s} value={s}>{s}</option>)}
              </select>
              <select value={direction} onChange={e => setDirection(e.target.value)}
                className="bg-gray-900 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500">
                <option value="All">Over &amp; Under</option>
                <option value="Over">Over only</option>
                <option value="Under">Under only</option>
              </select>
              <div className="flex items-center gap-2">
                <label className="text-xs text-gray-500 whitespace-nowrap">Min EV%</label>
                <input type="number" min={-100} max={20} step={0.5} value={minEv}
                  onChange={e => setMinEv(parseFloat(e.target.value) || 0)}
                  className="w-20 bg-gray-900 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
              </div>
              {isFetching && (
                <span className="text-xs text-gray-500 flex items-center gap-1.5">
                  <span className="inline-block w-3 h-3 border-2 border-gray-700 border-t-indigo-500 rounded-full animate-spin" />
                  Loading…
                </span>
              )}
              {jobStatus === 'failed' && jobError && (
                <span className="text-xs text-red-400 bg-red-500/10 border border-red-500/30 px-3 py-1.5 rounded-lg">✕ {jobError}</span>
              )}
            </div>

            {/* Legend */}
            <div className="flex items-center gap-4 text-xs text-gray-600">
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-emerald-500/30" /> ≥ 3% EV</span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-yellow-500/20" /> 1–3% EV</span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-gray-800" /> &lt; 1% EV</span>
              <span className="text-gray-700">· Click any row to expand details</span>
            </div>

            <PropTable
              props={props}
              slipPicks={slipPicks}
              onAddToSlip={prop => {
                const key = `${prop.player_name}|${prop.stat_type}|${prop.line_score}|${prop.direction}`
                setSlipPicks(prev =>
                  prev.some(p => `${p.player_name}|${p.stat_type}|${p.line_score}|${p.direction}` === key)
                    ? prev : [...prev, prop]
                )
              }}
            />
            {props.length === 0 && !isFetching && (
              <div className="text-center py-20 text-gray-600 space-y-3">
                <p className="text-4xl">📊</p>
                <p className="text-lg font-medium text-gray-500">No data yet</p>
                <p className="text-sm">Hit <span className="text-indigo-400">Refresh</span> to pull live PrizePicks lines and sportsbook odds for {sport}.</p>
              </div>
            )}
          </>
        ) : (
          <>
            {/* Sportsbook filters */}
            <div className="flex flex-wrap items-center gap-3">
              <select value={direction} onChange={e => setDirection(e.target.value)}
                className="bg-gray-900 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500">
                <option value="All">Over &amp; Under</option>
                <option value="Over">Over only</option>
                <option value="Under">Under only</option>
              </select>
              {sbFetching && (
                <span className="text-xs text-gray-500 flex items-center gap-1.5">
                  <span className="inline-block w-3 h-3 border-2 border-gray-700 border-t-indigo-500 rounded-full animate-spin" />
                  Loading…
                </span>
              )}
              {jobStatus === 'failed' && jobError && (
                <span className="text-xs text-red-400 bg-red-500/10 border border-red-500/30 px-3 py-1.5 rounded-lg">✕ {jobError}</span>
              )}
            </div>

            <div className="flex items-center gap-4 text-xs text-gray-600">
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-emerald-500/30" /> ≥ 3% EV</span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-yellow-500/20" /> 1–3% EV</span>
              <span className="text-gray-700">· Straight bet at the listed sportsbook · Click any row to expand</span>
            </div>

            <SportsbookTable
              lines={sbLines.filter(l => direction === 'All' || l.direction === direction)}
            />
            {sbLines.length === 0 && !sbFetching && (
              <div className="text-center py-20 text-gray-600 space-y-3">
                <p className="text-4xl">🏦</p>
                <p className="text-lg font-medium text-gray-500">No sportsbook data yet</p>
                <p className="text-sm">Hit <span className="text-indigo-400">Refresh</span> to scan all sportsbooks for soft lines on {sport}.</p>
              </div>
            )}
          </>
        )}
      </main>

      <BetSlip
        picks={slipPicks}
        bankroll={paperSummary?.current_bankroll ?? 100}
        onRemove={idx => setSlipPicks(prev => prev.filter((_, i) => i !== idx))}
        onClear={() => setSlipPicks([])}
        onBetPlaced={() => {
          qc.invalidateQueries({ queryKey: ['paper-summary'] })
          setToast({ message: 'Paper bet placed!', type: 'success' })
        }}
      />

      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onDismiss={() => setToast(null)}
        />
      )}
    </div>
  )
}
