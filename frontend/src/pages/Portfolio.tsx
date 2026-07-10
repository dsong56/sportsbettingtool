import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import { fetchBets } from '../api'
import BetSlip from '../components/BetSlip'
import Toast from '../components/Toast'
import type { BetLog } from '../types'

const SERIES_COLOR = '#6366f1'  // indigo — validated against the gray-950 surface
const GRID_COLOR = '#1f2937'
const TOOLTIP_STYLE = {
  backgroundColor: '#111827',
  border: '1px solid #374151',
  borderRadius: '0.5rem',
  fontSize: '0.75rem',
} as const

function isWin(bet: BetLog): boolean {
  return bet.actual_result === bet.direction.toLowerCase()
}

function usePersistedNumber(key: string, fallback: number): [number, (v: number) => void] {
  const [value, setValue] = useState<number>(() => {
    const raw = localStorage.getItem(key)
    const parsed = raw === null ? NaN : parseFloat(raw)
    return Number.isFinite(parsed) ? parsed : fallback
  })
  const update = (v: number) => {
    setValue(v)
    localStorage.setItem(key, String(v))
  }
  return [value, update]
}

function StatPill({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-3 text-center">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-xl font-bold text-white">{value}</p>
      {sub && <p className="text-xs text-gray-600 mt-0.5">{sub}</p>}
    </div>
  )
}

function ResultChip({ bet }: { bet: BetLog }) {
  if (!bet.actual_result) {
    return <span className="text-xs font-semibold px-1.5 py-0.5 rounded bg-gray-700/50 text-gray-400">Open</span>
  }
  return isWin(bet)
    ? <span className="text-xs font-semibold px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400">Win</span>
    : <span className="text-xs font-semibold px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-400">Loss</span>
}

function BetRows({ bets, settled }: { bets: BetLog[]; settled: boolean }) {
  if (bets.length === 0) {
    return (
      <tr>
        <td colSpan={7} className="px-4 py-8 text-center text-gray-600 text-sm">
          No {settled ? 'settled' : 'open'} bets yet.
        </td>
      </tr>
    )
  }
  return (
    <>
      {bets.map(b => (
        <tr key={b.id} className="hover:bg-gray-800/60 transition-colors">
          <td className="px-3 py-2.5">
            <p className="font-medium text-gray-200">{b.player_name}</p>
            <p className="text-xs text-gray-500">{b.sport}{b.game_date ? ` · ${b.game_date}` : ''}</p>
          </td>
          <td className="px-3 py-2.5 text-gray-400 whitespace-nowrap">
            {b.direction} {b.line_score} {b.stat_type}
          </td>
          <td className="px-3 py-2.5 text-gray-400 text-center">{b.pick_count}-pick</td>
          <td className="px-3 py-2.5 font-mono text-gray-300 text-right">{b.stake_pct.toFixed(1)}%</td>
          <td className="px-3 py-2.5 font-mono text-right">
            {b.ev_pct_at_entry !== null ? (
              <span className={b.ev_pct_at_entry >= 3 ? 'text-emerald-400' : b.ev_pct_at_entry >= 1 ? 'text-yellow-400' : 'text-gray-400'}>
                {b.ev_pct_at_entry > 0 ? '+' : ''}{b.ev_pct_at_entry.toFixed(1)}%
              </span>
            ) : '—'}
          </td>
          <td className="px-3 py-2.5 font-mono text-gray-400 text-right">
            {b.blended_prob_at_entry !== null ? `${(b.blended_prob_at_entry * 100).toFixed(1)}%` : '—'}
          </td>
          <td className="px-3 py-2.5 text-center"><ResultChip bet={b} /></td>
        </tr>
      ))}
    </>
  )
}

export default function Portfolio() {
  const [initialBankroll, setInitialBankroll] = usePersistedNumber('ev-bets-initial-bankroll', 1000)
  const [unitSize, setUnitSize] = usePersistedNumber('ev-bets-unit-size', 10)
  const [slipOpen, setSlipOpen] = useState(false)
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)

  const { data: bets = [], isFetching } = useQuery<BetLog[]>({
    queryKey: ['bets'],
    queryFn: () => fetchBets('all'),
    staleTime: 30_000,
  })

  const { openBets, settledBets, curve, roiPct, brier, winRate } = useMemo(() => {
    const open = bets.filter(b => b.actual_result === null)
    const settled = bets
      .filter(b => b.actual_result !== null)
      .sort((a, b) => (a.settled_at ?? '').localeCompare(b.settled_at ?? ''))

    // Flat ±1 unit per settled leg; bankroll = initial + cumulative units × unit size
    let units = 0
    const points = [{ label: 'Start', bankroll: initialBankroll }]
    for (const b of settled) {
      units += isWin(b) ? 1 : -1
      points.push({
        label: b.settled_at ? b.settled_at.slice(0, 10) : `#${b.id}`,
        bankroll: initialBankroll + units * unitSize,
      })
    }

    const wins = settled.filter(isWin).length
    const scored = settled.filter(b => b.blended_prob_at_entry !== null)
    const brierSum = scored.reduce((acc, b) => {
      const hit = isWin(b) ? 1 : 0
      return acc + (b.blended_prob_at_entry! - hit) ** 2
    }, 0)

    return {
      openBets: open,
      settledBets: [...settled].reverse(),
      curve: points,
      roiPct: settled.length ? (units / settled.length) * 100 : 0,
      brier: scored.length ? brierSum / scored.length : null,
      winRate: settled.length ? wins / settled.length : null,
    }
  }, [bets, initialBankroll, unitSize])

  const numInputCls =
    'w-24 bg-gray-900 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-2 ' +
    'focus:outline-none focus:ring-1 focus:ring-indigo-500'

  return (
    <main className="max-w-screen-xl mx-auto px-6 py-6 space-y-6">

      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-bold text-white">Portfolio</h1>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-gray-500">
            Initial bankroll $
            <input
              type="number" min={1} value={initialBankroll} className={numInputCls}
              onChange={e => setInitialBankroll(parseFloat(e.target.value) || 0)}
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-gray-500">
            Unit size $
            <input
              type="number" min={0} step={1} value={unitSize} className={numInputCls}
              onChange={e => setUnitSize(parseFloat(e.target.value) || 0)}
            />
          </label>
          <button
            onClick={() => setSlipOpen(true)}
            className="px-4 py-2 rounded-lg text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
          >
            + Log Bet
          </button>
        </div>
      </div>

      {/* Summary pills */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatPill label="Bets logged" value={String(bets.length)} sub={`${openBets.length} open`} />
        <StatPill label="Win rate" value={winRate !== null ? `${(winRate * 100).toFixed(1)}%` : '—'}
                  sub={`${settledBets.length} settled`} />
        <StatPill label="ROI (units)" value={`${roiPct >= 0 ? '+' : ''}${roiPct.toFixed(1)}%`}
                  sub="±1 unit per leg" />
        <StatPill label="Brier score" value={brier !== null ? brier.toFixed(3) : '—'} sub="lower is better" />
      </div>

      {/* Bankroll curve */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <p className="text-sm font-medium text-gray-300 mb-3">Bankroll</p>
        {settledBets.length === 0 ? (
          <p className="text-sm text-gray-600 py-10 text-center">
            The bankroll curve appears once bets settle.
          </p>
        ) : (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={curve} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: '#6b7280', fontSize: 11 }}
                       tickLine={false} axisLine={{ stroke: GRID_COLOR }} minTickGap={40} />
                <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} tickLine={false}
                       axisLine={false} width={64}
                       tickFormatter={(v: number) => `$${v.toLocaleString()}`} />
                <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: '#9ca3af' }}
                         itemStyle={{ color: '#e5e7eb' }} />
                <ReferenceLine y={initialBankroll} stroke="#4b5563" strokeDasharray="4 4" />
                <Line type="monotone" dataKey="bankroll" name="Bankroll" stroke={SERIES_COLOR}
                      strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Open bets */}
      <div>
        <p className="text-sm font-medium text-gray-300 mb-2">
          Open bets {isFetching && <span className="text-gray-600">· refreshing…</span>}
        </p>
        <div className="w-full overflow-x-auto rounded-xl border border-gray-800">
          <table className="w-full text-sm text-left">
            <thead className="bg-gray-900 border-b border-gray-800">
              <tr>
                {['Player', 'Bet', 'Tier', 'Stake', 'EV @ entry', 'Prob @ entry', 'Result'].map(h => (
                  <th key={h} className="px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/50">
              <BetRows bets={openBets} settled={false} />
            </tbody>
          </table>
        </div>
      </div>

      {/* Settled bets */}
      <div>
        <p className="text-sm font-medium text-gray-300 mb-2">Settled bets</p>
        <div className="w-full overflow-x-auto rounded-xl border border-gray-800">
          <table className="w-full text-sm text-left">
            <thead className="bg-gray-900 border-b border-gray-800">
              <tr>
                {['Player', 'Bet', 'Tier', 'Stake', 'EV @ entry', 'Prob @ entry', 'Result'].map(h => (
                  <th key={h} className="px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/50">
              <BetRows bets={settledBets} settled />
            </tbody>
          </table>
        </div>
      </div>

      {slipOpen && (
        <BetSlip
          onClose={() => setSlipOpen(false)}
          onLogged={() => setToast({ message: 'Bet logged', type: 'success' })}
        />
      )}

      {toast && <Toast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} />}
    </main>
  )
}
