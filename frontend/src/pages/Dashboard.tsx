import { useState, useEffect, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchProps, fetchSportsbookBooks, fetchSportsbookLines, triggerRefresh, pollJob } from '../api'
import PropTable from '../components/PropTable'
import SportsbookTable from '../components/SportsbookTable'
import BetSlip from '../components/BetSlip'
import Toast from '../components/Toast'
import type { Sport, PropResult, SportsbookLineRow } from '../types'

type Mode = 'prizepicks' | 'sportsbooks'

const SPORTS: Sport[] = ['NBA', 'NHL', 'MLB', 'NFL']

const SPORT_STATS: Record<Sport, string[]> = {
  NBA: ['All', 'Points', 'Rebounds', 'Assists', '3-PT Made', 'Blocked Shots', 'Steals', 'Pts+Rebs+Asts', 'Pts+Rebs', 'Pts+Asts', 'Rebs+Asts'],
  NHL: ['All', 'Shots on Goal', 'Saves', 'Points', 'Blocked Shots', 'Assists', 'Goals'],
  MLB: ['All', 'Pitcher Strikeouts', 'Total Bases', 'Hits Allowed', 'Pitcher Outs', 'Hits+Runs+RBIs'],
  NFL: ['All', 'Pass Yards', 'Rush Yards', 'Receiving Yards', 'Receptions', 'Touchdowns', 'Pass Completions', 'INT'],
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

  const [mode, setMode]           = useState<Mode>('prizepicks')
  const [sport, setSport]         = useState<Sport>('NBA')
  const [statType, setStatType]   = useState('All')
  const [direction, setDirection] = useState('All')
  const [book, setBook]           = useState('All')
  const [minEv, setMinEv]         = useState(-100)
  const [credits, setCredits]     = useState<string | null>(null)
  const [jobId, setJobId]         = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<JobStatus>('idle')
  const [jobError, setJobError]   = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<string | null>(null)
  const [toast, setToast]         = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  const [betProp, setBetProp]     = useState<PropResult | null>(null)

  // Reset stat filter when sport changes
  useEffect(() => { setStatType('All') }, [sport])

  const { data: props = [], isFetching: fetchingProps } = useQuery<PropResult[]>({
    queryKey: ['props', sport, statType, direction, minEv],
    queryFn: () => fetchProps({
      sport,
      stat_type:  statType === 'All' ? undefined : statType,
      direction:  direction === 'All' ? undefined : direction,
      min_ev:     minEv,
    }),
    staleTime: 60_000,
    enabled: mode === 'prizepicks',
  })

  const { data: sbLines = [], isFetching: fetchingLines } = useQuery<SportsbookLineRow[]>({
    queryKey: ['sportsbook', sport, statType, direction, book, minEv],
    queryFn: () => fetchSportsbookLines({
      sport,
      stat_type:  statType === 'All' ? undefined : statType,
      direction:  direction === 'All' ? undefined : direction,
      book:       book === 'All' ? undefined : book,
      min_ev:     minEv,
    }),
    staleTime: 60_000,
    enabled: mode === 'sportsbooks',
  })

  const { data: books = [] } = useQuery<string[]>({
    queryKey: ['sportsbook-books', sport],
    queryFn: () => fetchSportsbookBooks(sport),
    staleTime: 300_000,
    enabled: mode === 'sportsbooks',
  })

  const isFetching = mode === 'prizepicks' ? fetchingProps : fetchingLines

  // Poll job status until done/failed
  const pollOnce = useCallback(async (id: string) => {
    const job = await pollJob(id)
    setJobStatus(job.status as JobStatus)
    if (job.status === 'done') {
      qc.invalidateQueries({ queryKey: ['props'] })
      qc.invalidateQueries({ queryKey: ['sportsbook'] })
      qc.invalidateQueries({ queryKey: ['sportsbook-books'] })
      setJobId(null)
      setJobError(null)
      setLastUpdated(new Date().toLocaleTimeString())
      setCredits(job.credits_remaining ?? null)
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
    const MAX_POLLS = 240  // 10 minutes at 2.5s intervals — the first scrape per
                           // sport fetches game logs per player and can be slow
    const interval = setInterval(() => {
      polls++
      if (polls > MAX_POLLS) {
        clearInterval(interval)
        setJobStatus('failed')
        setJobError('Refresh timed out after 10 minutes — the scrape may still be running; check the backend logs')
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
    const job = await triggerRefresh(sport)
    setJobId(job.job_id)
  }

  // Summary stats (per mode)
  const rows        = mode === 'prizepicks' ? props : sbLines
  const positiveEv  = rows.filter(r => r.ev_pct >= 3).length
  const marginalEv  = rows.filter(r => r.ev_pct >= 1 && r.ev_pct < 3).length
  const bestEv      = rows.length ? Math.max(...rows.map(r => r.ev_pct)) : 0
  const allAgree    = props.filter(p => {
    const isOver = p.direction === 'Over'
    const mkt  = isOver ? p.market_prob > 0.5 : p.market_prob < 0.5
    const hist = isOver ? p.historical_prob > 0.5 : p.historical_prob < 0.5
    const mov  = Math.abs(p.movement_signal) > 0.05
      ? (isOver ? p.movement_signal > 0 : p.movement_signal < 0)
      : null
    return mkt && hist && (mov === null || mov)
  }).length
  const softBooks   = new Set(sbLines.filter(l => l.ev_pct >= 1).map(l => l.book)).size

  return (
    <div>

      {/* Sport bar */}
      <div className="border-b border-gray-800 bg-gray-900/40">
        <div className="max-w-screen-xl mx-auto px-6 py-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="flex items-center bg-gray-800 rounded-lg p-0.5 mr-2">
              {(['prizepicks', 'sportsbooks'] as const).map(m => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
                    mode === m ? 'bg-gray-950 text-white' : 'text-gray-400 hover:text-gray-200'
                  }`}
                >
                  {m === 'prizepicks' ? 'PrizePicks' : 'Sportsbooks'}
                </button>
              ))}
            </div>
            {SPORTS.map(s => (
              <SportTab key={s} sport={s} active={sport === s} onClick={() => setSport(s)} />
            ))}
          </div>
          <div className="flex items-center gap-3">
            {lastUpdated && (
              <span className="text-xs text-gray-500">
                Last updated {lastUpdated}
                {credits !== null && <span className="text-gray-600"> · {credits} credits left</span>}
              </span>
            )}
            <RefreshButton status={jobStatus} onClick={handleRefresh} />
          </div>
        </div>
      </div>

      <main className="max-w-screen-xl mx-auto px-6 py-6 space-y-6">

        {/* Summary pills */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatPill label={mode === 'prizepicks' ? 'Total props' : 'Total lines'} value={rows.length} />
          <StatPill label={mode === 'prizepicks' ? 'Strong EV (≥3%)' : 'Soft lines (≥3%)'} value={positiveEv} sub="green rows" />
          <StatPill label="Marginal (1–3%)" value={marginalEv} sub="yellow rows" />
          {mode === 'prizepicks' ? (
            <StatPill label="All-signal agree" value={allAgree} sub={bestEv > 0 ? `Best: +${bestEv.toFixed(1)}%` : '—'} />
          ) : (
            <StatPill label="Books with an edge" value={softBooks} sub={bestEv > 0 ? `Best: +${bestEv.toFixed(1)}%` : '—'} />
          )}
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

          {/* Book (sportsbook mode only) */}
          {mode === 'sportsbooks' && (
            <select
              value={book}
              onChange={e => setBook(e.target.value)}
              className="bg-gray-900 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="All">All books</option>
              {books.map(b => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>
          )}

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

          {jobStatus === 'failed' && jobError && (
            <span className="text-xs text-red-400 bg-red-500/10 border border-red-500/30 px-3 py-1.5 rounded-lg">
              ✕ {jobError}
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
          {mode === 'prizepicks' ? (
            <span className="text-gray-700">· Click any row to expand details</span>
          ) : (
            <span className="text-gray-700">· Edge = this book's price vs the sharp consensus of the other books</span>
          )}
        </div>

        {/* Main table */}
        {mode === 'prizepicks' ? (
          <PropTable props={props} onLogBet={setBetProp} />
        ) : (
          <SportsbookTable lines={sbLines} />
        )}

        {/* Empty state when no data has been fetched yet */}
        {rows.length === 0 && !isFetching && (
          <div className="text-center py-20 text-gray-600 space-y-3">
            <p className="text-4xl">📊</p>
            <p className="text-lg font-medium text-gray-500">No data yet</p>
            <p className="text-sm">Hit <span className="text-indigo-400">Refresh</span> to pull live PrizePicks lines and sportsbook odds for {sport}.</p>
          </div>
        )}
      </main>

      {betProp && (
        <BetSlip
          prefill={betProp}
          onClose={() => setBetProp(null)}
          onLogged={() => setToast({ message: 'Bet logged — see Portfolio', type: 'success' })}
        />
      )}

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
