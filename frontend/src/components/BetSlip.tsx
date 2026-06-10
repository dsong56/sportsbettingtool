import { useState } from 'react'
import type { PropResult } from '../types'
import { placePaperBet } from '../api'

// Mirror backend constants
const POWER_MULTIPLIERS: Record<number, number> = { 2: 3, 3: 5, 4: 10, 5: 20, 6: 25 }
const FLEX_PAYOUTS: Record<number, Record<number, number>> = {
  3: { 3: 2.5, 2: 1.25 },
  4: { 4: 5.0, 3: 1.5 },
  5: { 5: 10.0, 4: 2.0, 3: 0.4 },
  6: { 6: 25.0, 5: 2.0, 4: 0.4 },
}

type PlayType = 'power' | 'flex'

interface Props {
  picks:       PropResult[]
  bankroll:    number
  onRemove:    (idx: number) => void
  onClear:     () => void
  onBetPlaced: () => void
}

// ── math (same as ParlayOptimizer) ───────────────────────────────────────────

function powerEV(probs: number[], n: number): number {
  const mult = POWER_MULTIPLIERS[n]
  if (!mult) return -Infinity
  return probs.reduce((p, q) => p * q, 1) * mult - 1
}

function flexEV(probs: number[], payouts: Record<number, number>): number {
  const n = probs.length
  let ev = -1
  for (let mask = 0; mask < (1 << n); mask++) {
    let prob = 1; let hits = 0
    for (let i = 0; i < n; i++) {
      if (mask & (1 << i)) { prob *= probs[i]; hits++ }
      else                  { prob *= (1 - probs[i]) }
    }
    ev += prob * (payouts[hits] ?? 0)
  }
  return ev
}

function kellyFraction(trueProb: number, multiplier: number): number {
  const b = multiplier - 1
  if (b <= 0) return 0
  const f = (trueProb * (b + 1) - 1) / b
  return Math.max(0, Math.min(f * 0.5, 0.25))
}

// ── component ─────────────────────────────────────────────────────────────────

export default function BetSlip({ picks, bankroll, onRemove, onClear, onBetPlaced }: Props) {
  const [open, setOpen]         = useState(false)
  const [playType, setPlayType] = useState<PlayType>('power')
  const [stake, setStake]       = useState<number>(5)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState<string | null>(null)

  const n = picks.length
  const probs = picks.map(p => p.blended_prob)

  // Compute EV + Kelly for current selection
  let evPct = -Infinity
  let mult  = 0
  let kelly = 0

  if (n >= 2) {
    if (playType === 'power' && POWER_MULTIPLIERS[n]) {
      mult  = POWER_MULTIPLIERS[n]
      evPct = powerEV(probs, n) * 100
      const joint = probs.reduce((a, b) => a * b, 1)
      kelly = kellyFraction(joint, mult)
    } else if (playType === 'flex' && FLEX_PAYOUTS[n]) {
      const payouts = FLEX_PAYOUTS[n]
      mult  = Math.max(...Object.values(payouts))
      evPct = flexEV(probs, payouts) * 100
      // Approximate Kelly for flex: use blended prob vs max payout
      const joint = probs.reduce((a, b) => a * b, 1)
      kelly = kellyFraction(joint, mult)
    }
  }

  const kellyStake   = parseFloat((bankroll * kelly).toFixed(2))
  const maxPayout    = parseFloat((stake * mult).toFixed(2))
  const evColor      = evPct >= 3 ? 'text-emerald-400' : evPct >= 0 ? 'text-yellow-400' : 'text-red-400'
  const canPlace     = n >= 2 && n <= 6 && evPct > -Infinity && stake > 0 && stake <= bankroll

  async function handlePlace() {
    if (!canPlace) return
    setLoading(true)
    setError(null)
    try {
      await placePaperBet({
        play_type:  playType,
        n_picks:    n,
        picks:      picks.map(p => ({
          player_name:  p.player_name,
          stat_type:    p.stat_type,
          line_score:   p.line_score,
          direction:    p.direction,
          sport:        p.sport,
          odds_type:    p.odds_type,
          blended_prob: p.blended_prob,
          matchup:      p.matchup ?? '',
        })),
        stake,
        multiplier: mult,
        joint_prob: probs.reduce((a, b) => a * b, 1),
        ev_pct:     evPct,
      })
      onBetPlaced()
      onClear()
      setOpen(false)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to place bet')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed bottom-6 left-6 z-40 flex flex-col items-start gap-2">

      {/* Expanded slip */}
      {open && (
        <div className="bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl w-80 overflow-hidden">

          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
            <span className="text-white font-semibold text-sm">Custom Bet Slip</span>
            <div className="flex items-center gap-2">
              {picks.length > 0 && (
                <button onClick={onClear} className="text-xs text-gray-500 hover:text-red-400 transition-colors">
                  Clear
                </button>
              )}
              <button onClick={() => setOpen(false)} className="text-gray-500 hover:text-white text-lg leading-none">×</button>
            </div>
          </div>

          {/* Picks list */}
          <div className="px-4 py-3 space-y-2 max-h-52 overflow-y-auto">
            {picks.length === 0 ? (
              <p className="text-xs text-gray-600 text-center py-4">
                Click <span className="text-indigo-400">+</span> on any prop row to add picks
              </p>
            ) : (
              picks.map((p, i) => (
                <div key={i} className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-xs text-gray-200 font-medium truncate">{p.player_name}</p>
                    <p className="text-xs text-gray-500">
                      {p.direction} {p.line_score} {p.stat_type}
                      {p.matchup && <span className="ml-1 text-gray-600">({p.matchup})</span>}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs font-mono text-indigo-300">{(p.blended_prob * 100).toFixed(1)}%</span>
                    <button
                      onClick={() => onRemove(i)}
                      className="text-gray-600 hover:text-red-400 transition-colors text-sm leading-none"
                    >
                      ×
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>

          {n >= 2 && (
            <>
              {/* Play type toggle */}
              <div className="px-4 pb-3 flex gap-2">
                {(['power', 'flex'] as PlayType[]).map(pt => (
                  <button
                    key={pt}
                    onClick={() => setPlayType(pt)}
                    disabled={pt === 'flex' && !FLEX_PAYOUTS[n]}
                    className={`flex-1 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                      playType === pt
                        ? 'bg-indigo-600 text-white'
                        : 'text-gray-400 border border-gray-700 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed'
                    }`}
                  >
                    {pt === 'power' ? 'Power Play' : 'Flex Play'}
                  </button>
                ))}
              </div>

              {/* EV display */}
              <div className="px-4 pb-3 grid grid-cols-2 gap-2">
                <div className="bg-gray-800 rounded-lg p-2 text-center">
                  <p className="text-xs text-gray-500">EV%</p>
                  <p className={`text-sm font-bold font-mono ${evColor}`}>
                    {evPct > -Infinity ? `${evPct >= 0 ? '+' : ''}${evPct.toFixed(1)}%` : '—'}
                  </p>
                </div>
                <div className="bg-gray-800 rounded-lg p-2 text-center">
                  <p className="text-xs text-gray-500">Payout</p>
                  <p className="text-sm font-mono text-gray-200">{mult > 0 ? `${mult}x` : '—'}</p>
                </div>
              </div>

              {/* Stake input */}
              <div className="px-4 pb-3 space-y-2">
                <div className="flex items-center gap-2">
                  <span className="text-gray-400 text-sm">$</span>
                  <input
                    type="number"
                    min={0.01}
                    max={bankroll}
                    step={0.01}
                    value={stake}
                    onChange={e => setStake(parseFloat(e.target.value) || 0)}
                    className="flex-1 bg-gray-800 border border-gray-700 text-white rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                  {kellyStake > 0 && (
                    <button
                      onClick={() => setStake(kellyStake)}
                      className="text-xs text-indigo-400 hover:text-indigo-300 whitespace-nowrap"
                    >
                      ½-Kelly
                    </button>
                  )}
                </div>
                {stake > 0 && mult > 0 && (
                  <p className="text-xs text-gray-500">
                    Max payout: <span className="text-gray-300 font-mono">${maxPayout.toFixed(2)}</span>
                    <span className="ml-2 text-gray-600">· Bankroll: ${bankroll.toFixed(2)}</span>
                  </p>
                )}
              </div>

              {error && (
                <div className="mx-4 mb-3 flex gap-2 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
                  <span className="text-red-400 shrink-0">✕</span>
                  <p className="text-xs text-red-400">{error}</p>
                </div>
              )}

              {/* Place button */}
              <div className="px-4 pb-4">
                <button
                  onClick={handlePlace}
                  disabled={!canPlace || loading}
                  className="w-full py-2.5 rounded-xl text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {loading ? 'Placing…' : `Place ${n}-Pick ${playType === 'power' ? 'Power Play' : 'Flex Play'}`}
                </button>
                {n < 2 && <p className="text-xs text-gray-600 text-center mt-2">Add at least 2 picks</p>}
                {n > 6 && <p className="text-xs text-red-400 text-center mt-2">Max 6 picks</p>}
              </div>
            </>
          )}

          {n === 1 && (
            <p className="px-4 pb-4 text-xs text-gray-600 text-center">Add 1 more pick to build a parlay</p>
          )}
        </div>
      )}

      {/* Toggle button */}
      <button
        onClick={() => setOpen(o => !o)}
        className={`flex items-center gap-2 px-4 py-2.5 rounded-xl font-semibold text-sm shadow-lg transition-colors ${
          n > 0
            ? 'bg-indigo-600 hover:bg-indigo-500 text-white'
            : 'bg-gray-800 hover:bg-gray-700 text-gray-400 border border-gray-700'
        }`}
      >
        <span>Bet Slip</span>
        {n > 0 && (
          <span className="bg-white/20 text-white text-xs font-bold px-1.5 py-0.5 rounded-full">{n}</span>
        )}
      </button>
    </div>
  )
}
