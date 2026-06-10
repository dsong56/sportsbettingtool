import { useState } from 'react'
import type { PropResult } from '../types'
import { placePaperBet } from '../api'

interface Props {
  props:            PropResult[]
  currentBankroll?: number
  onBetPlaced?:     () => void  // callback to refresh portfolio
}

// Power Play: all picks must hit
const POWER_MULTIPLIERS: Record<number, number> = { 2: 3, 3: 5, 4: 10, 5: 20, 6: 25 }

// Flex Play: partial hits still pay. { n_picks: { hits: multiplier } }
// Verify these against PrizePicks before betting — they change periodically.
const FLEX_PAYOUTS: Record<number, Record<number, number>> = {
  3: { 3: 2.5,  2: 1.25 },
  4: { 4: 5.0,  3: 1.5  },
  5: { 5: 10.0, 4: 2.0, 3: 0.4 },
  6: { 6: 25.0, 5: 2.0, 4: 0.4 },
}

type PlayType = 'power' | 'flex'

interface ParlaySuggestion {
  picks:             PropResult[]
  n_picks:           number
  play_type:         PlayType
  multiplier:        number   // max payout multiplier
  ev_pct:            number   // net EV as % of stake
  kelly_pct:         number   // half-Kelly % of bankroll
  joint_prob?:       number   // power play only
  outcome_probs?:    { hits: number; prob: number; payout: number }[]  // flex only
  same_game_warning: boolean
}

// ── math helpers ─────────────────────────────────────────────────────────────

function powerBreakeven(n: number, mult: number): number {
  return Math.pow(1 / mult, 1 / n)
}

function flexEV(probs: number[], payouts: Record<number, number>): number {
  const n = probs.length
  let ev = -1
  for (let mask = 0; mask < (1 << n); mask++) {
    let prob = 1
    let hits = 0
    for (let i = 0; i < n; i++) {
      if (mask & (1 << i)) { prob *= probs[i]; hits++ }
      else                  { prob *= (1 - probs[i]) }
    }
    ev += prob * (payouts[hits] ?? 0)
  }
  return ev
}

function flexOutcomeProbabilities(
  probs: number[],
  payouts: Record<number, number>,
): { hits: number; prob: number; payout: number }[] {
  const n = probs.length
  const byHits: Record<number, number> = {}
  for (let mask = 0; mask < (1 << n); mask++) {
    let prob = 1; let hits = 0
    for (let i = 0; i < n; i++) {
      if (mask & (1 << i)) { prob *= probs[i]; hits++ }
      else                  { prob *= (1 - probs[i]) }
    }
    byHits[hits] = (byHits[hits] ?? 0) + prob
  }
  return Object.entries(byHits)
    .map(([h, p]) => ({ hits: Number(h), prob: p, payout: payouts[Number(h)] ?? 0 }))
    .sort((a, b) => b.hits - a.hits)
}

// Binary search for Kelly fraction maximising E[log(wealth)]
function flexKelly(probs: number[], payouts: Record<number, number>): number {
  const n = probs.length
  const outcomes: [number, number][] = []
  for (let mask = 0; mask < (1 << n); mask++) {
    let prob = 1; let hits = 0
    for (let i = 0; i < n; i++) {
      if (mask & (1 << i)) { prob *= probs[i]; hits++ }
      else                  { prob *= (1 - probs[i]) }
    }
    outcomes.push([prob, payouts[hits] ?? 0])
  }
  // dG/df = Σ P_k * (X_k - 1) / (1 - f + f*X_k) = 0
  let lo = 0, hi = 0.99
  for (let iter = 0; iter < 60; iter++) {
    const f = (lo + hi) / 2
    const d = outcomes.reduce((s, [p, x]) => {
      const denom = 1 - f + f * x
      return denom > 0 ? s + p * (x - 1) / denom : s
    }, 0)
    if (d > 0) lo = f; else hi = f
  }
  return Math.max(0, Math.min((lo + hi) / 2 * 0.5, 0.25)) // half-Kelly, capped 25%
}

// ── pick selection ────────────────────────────────────────────────────────────

function topPicks(eligible: PropResult[], n: number): PropResult[] {
  const sorted = [...eligible].sort((a, b) => b.blended_prob - a.blended_prob)
  const picks: PropResult[] = []
  const used = new Set<string>()
  for (const p of sorted) {
    if (used.has(p.player_name)) continue
    picks.push(p)
    used.add(p.player_name)
    if (picks.length === n) break
  }
  return picks
}

function hasSameGame(picks: PropResult[]): boolean {
  return picks.some((a, i) =>
    picks.some((b, j) => i !== j && a.matchup && b.matchup && a.matchup === b.matchup)
  )
}

function computePowerParlay(props: PropResult[], n: number): ParlaySuggestion | null {
  const mult = POWER_MULTIPLIERS[n]
  const be   = powerBreakeven(n, mult)
  const eligible = props.filter(p => p.blended_prob > be)
  const picks = topPicks(eligible, n)
  if (picks.length < n) return null

  const joint = picks.reduce((acc, p) => acc * p.blended_prob, 1)
  const b = mult - 1
  const full_kelly = (joint * mult - 1) / b
  const kelly_pct  = Math.max(0, Math.min(full_kelly * 0.5, 0.25)) * 100
  const ev_pct     = (joint * mult - 1) * 100

  return {
    picks, n_picks: n, play_type: 'power',
    multiplier: mult,
    ev_pct, kelly_pct,
    joint_prob: joint,
    same_game_warning: hasSameGame(picks),
  }
}

function computeFlexParlay(props: PropResult[], n: number): ParlaySuggestion | null {
  const payouts = FLEX_PAYOUTS[n]
  if (!payouts) return null

  // For flex, any pick with blended_prob > 0.5 adds positive EV
  const eligible = props.filter(p => p.blended_prob > 0.5)
  const picks = topPicks(eligible, n)
  if (picks.length < n) return null

  const probs   = picks.map(p => p.blended_prob)
  const ev      = flexEV(probs, payouts)
  if (ev <= -1) return null  // negative EV even at best picks

  const maxMult = Math.max(...Object.values(payouts))
  return {
    picks, n_picks: n, play_type: 'flex',
    multiplier: maxMult,
    ev_pct: ev * 100,
    kelly_pct: flexKelly(probs, payouts) * 100,
    outcome_probs: flexOutcomeProbabilities(probs, payouts),
    same_game_warning: hasSameGame(picks),
  }
}

// ── Bet confirmation modal ────────────────────────────────────────────────────

interface BetModalProps {
  suggestion:      ParlaySuggestion
  bankroll:        number
  onConfirm:       (stake: number) => Promise<void>
  onClose:         () => void
}

function BetModal({ suggestion: s, bankroll, onConfirm, onClose }: BetModalProps) {
  const defaultStake = Math.min(
    parseFloat((bankroll * s.kelly_pct / 100).toFixed(2)),
    bankroll,
  )
  const [stake, setStake]     = useState(defaultStake > 0 ? defaultStake : 1)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)

  const maxPayout = parseFloat((stake * s.multiplier).toFixed(2))
  const netProfit = parseFloat((maxPayout - stake).toFixed(2))

  async function handleConfirm() {
    if (stake <= 0 || stake > bankroll) return
    setLoading(true)
    setError(null)
    try {
      await onConfirm(stake)
      onClose()
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to place bet')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 w-full max-w-md shadow-2xl space-y-5" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="text-white font-semibold text-lg">
            Place Paper Bet — {s.n_picks}-Pick {s.play_type === 'power' ? 'Power Play' : 'Flex Play'}
          </h3>
          <button onClick={onClose} className="text-gray-500 hover:text-white text-xl leading-none">×</button>
        </div>

        {/* Picks summary */}
        <div className="space-y-1">
          {s.picks.map((p, i) => (
            <div key={i} className="flex justify-between text-sm">
              <span className="text-gray-300">{p.player_name} <span className="text-gray-500">{p.direction} {p.line_score} {p.stat_type}</span></span>
              <span className="text-indigo-300 font-mono">{(p.blended_prob * 100).toFixed(1)}%</span>
            </div>
          ))}
        </div>

        {/* Stake input */}
        <div>
          <label className="text-xs text-gray-500 block mb-1">
            Stake (bankroll: ${bankroll.toFixed(2)})
          </label>
          <div className="flex items-center gap-2">
            <span className="text-gray-400">$</span>
            <input
              type="number"
              min={0.01}
              max={bankroll}
              step={0.01}
              value={stake}
              onChange={e => setStake(parseFloat(e.target.value) || 0)}
              className="flex-1 bg-gray-800 border border-gray-700 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <button
              onClick={() => setStake(parseFloat((bankroll * s.kelly_pct / 100).toFixed(2)))}
              className="text-xs text-indigo-400 hover:text-indigo-300 whitespace-nowrap"
            >
              ½-Kelly
            </button>
          </div>
        </div>

        {/* Payout summary */}
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-gray-800 rounded-lg p-3 text-center">
            <p className="text-xs text-gray-500">Max payout</p>
            <p className="text-sm font-mono text-white">${maxPayout.toFixed(2)}</p>
          </div>
          <div className="bg-gray-800 rounded-lg p-3 text-center">
            <p className="text-xs text-gray-500">Net profit</p>
            <p className="text-sm font-mono text-emerald-400">+${netProfit.toFixed(2)}</p>
          </div>
          <div className="bg-gray-800 rounded-lg p-3 text-center">
            <p className="text-xs text-gray-500">Joint prob</p>
            <p className="text-sm font-mono text-gray-200">
              {s.joint_prob !== undefined ? (s.joint_prob * 100).toFixed(1) : '—'}%
            </p>
          </div>
        </div>

        {error && (
          <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/40 rounded-lg px-3 py-2">
            <span className="text-red-400 shrink-0">✕</span>
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 py-2 rounded-lg text-sm text-gray-400 border border-gray-700 hover:border-gray-500"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading || stake <= 0 || stake > bankroll}
            className="flex-1 py-2 rounded-lg text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Placing…' : 'Confirm Bet'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── UI components ─────────────────────────────────────────────────────────────

function PickRow({ pick }: { pick: PropResult }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-gray-800 last:border-0">
      <div>
        <span className="text-sm text-gray-200 font-medium">{pick.player_name}</span>
        <span className="text-xs text-gray-500 ml-2">
          {pick.direction} {pick.line_score} {pick.stat_type}
        </span>
      </div>
      <div className="flex items-center gap-2 shrink-0 ml-3">
        {pick.matchup && <span className="text-xs text-gray-600">{pick.matchup}</span>}
        <span className="text-xs font-mono text-indigo-300">
          {(pick.blended_prob * 100).toFixed(1)}%
        </span>
      </div>
    </div>
  )
}

function PlaceBetButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-full mt-1 py-2 rounded-lg text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
    >
      Paper Trade
    </button>
  )
}

function PowerCard({ s, onBet }: { s: ParlaySuggestion; onBet: () => void }) {
  const mult = POWER_MULTIPLIERS[s.n_picks]
  const evColor = s.ev_pct >= 5 ? 'text-emerald-400' : s.ev_pct >= 0 ? 'text-yellow-400' : 'text-gray-500'

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <span className="text-white font-semibold">{s.n_picks}-Pick</span>
          <span className="ml-2 text-xs text-gray-500">{mult}x payout</span>
        </div>
        <span className={`text-lg font-bold font-mono ${evColor}`}>
          {s.ev_pct >= 0 ? '+' : ''}{s.ev_pct.toFixed(1)}% EV
        </span>
      </div>
      <div>{s.picks.map((p, i) => <PickRow key={i} pick={p} />)}</div>
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-gray-800 rounded-lg p-2 text-center">
          <p className="text-xs text-gray-500">Joint prob</p>
          <p className="text-sm font-mono text-gray-200">{((s.joint_prob ?? 0) * 100).toFixed(1)}%</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-2 text-center">
          <p className="text-xs text-gray-500">½-Kelly</p>
          <p className="text-sm font-mono text-indigo-300">{s.kelly_pct.toFixed(1)}%</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-2 text-center">
          <p className="text-xs text-gray-500">On $100</p>
          <p className="text-sm font-mono text-gray-200">${s.kelly_pct.toFixed(2)} bet</p>
        </div>
      </div>
      <p className="text-xs text-gray-600">
        Breakeven per pick: {(powerBreakeven(s.n_picks, mult) * 100).toFixed(1)}%
      </p>
      {s.same_game_warning && <SameGameWarning />}
      <PlaceBetButton onClick={onBet} />
    </div>
  )
}

function FlexCard({ s, onBet }: { s: ParlaySuggestion; onBet: () => void }) {
  const evColor = s.ev_pct >= 5 ? 'text-emerald-400' : s.ev_pct >= 0 ? 'text-yellow-400' : 'text-gray-500'
  const outcomes = s.outcome_probs ?? []

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <span className="text-white font-semibold">{s.n_picks}-Pick</span>
          <span className="ml-2 text-xs text-gray-500">Flex — partial payouts</span>
        </div>
        <span className={`text-lg font-bold font-mono ${evColor}`}>
          {s.ev_pct >= 0 ? '+' : ''}{s.ev_pct.toFixed(1)}% EV
        </span>
      </div>
      <div>{s.picks.map((p, i) => <PickRow key={i} pick={p} />)}</div>

      {/* Outcome breakdown */}
      <div className="space-y-1">
        <p className="text-xs text-gray-500 font-medium">Outcome probabilities</p>
        {outcomes.filter(o => o.payout > 0 || o.prob > 0.05).map(o => (
          <div key={o.hits} className="flex items-center gap-2">
            <span className="text-xs text-gray-400 w-20 shrink-0">
              {o.hits}/{s.n_picks} hit{o.hits !== 1 ? 's' : ''}
            </span>
            <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full bg-indigo-500"
                style={{ width: `${o.prob * 100}%` }}
              />
            </div>
            <span className="text-xs font-mono text-gray-400 w-10 text-right">
              {(o.prob * 100).toFixed(0)}%
            </span>
            <span className={`text-xs font-mono w-12 text-right ${o.payout >= 1 ? 'text-emerald-400' : 'text-gray-600'}`}>
              {o.payout > 0 ? `${o.payout}x` : 'loss'}
            </span>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="bg-gray-800 rounded-lg p-2 text-center">
          <p className="text-xs text-gray-500">½-Kelly</p>
          <p className="text-sm font-mono text-indigo-300">{s.kelly_pct.toFixed(1)}%</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-2 text-center">
          <p className="text-xs text-gray-500">On $100</p>
          <p className="text-sm font-mono text-gray-200">${s.kelly_pct.toFixed(2)} bet</p>
        </div>
      </div>
      {s.same_game_warning && <SameGameWarning />}
      <PlaceBetButton onClick={onBet} />
    </div>
  )
}

function SameGameWarning() {
  return (
    <div className="flex items-start gap-2 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">
      <span className="text-amber-400 shrink-0">⚠</span>
      <p className="text-xs text-amber-400">
        Picks share a matchup — may be correlated. True joint probability could be lower.
      </p>
    </div>
  )
}

// ── main component ────────────────────────────────────────────────────────────

export default function ParlayOptimizer({ props, currentBankroll = 100, onBetPlaced }: Props) {
  const [playType, setPlayType]         = useState<PlayType>('power')
  const [activeBet, setActiveBet]       = useState<ParlaySuggestion | null>(null)

  async function handlePlaceBet(s: ParlaySuggestion, stake: number) {
    const payload: import('../api').PlaceBetPayload = {
      play_type:  s.play_type,
      n_picks:    s.n_picks,
      picks:      s.picks.map(p => ({
        player_name:  p.player_name,
        stat_type:    p.stat_type,
        line_score:   p.line_score,
        direction:    p.direction,
        sport:        p.sport,
        odds_type:    p.odds_type,
        blended_prob: p.blended_prob,
        game_date:    p.game_date,
        matchup:      p.matchup ?? '',
      })),
      stake,
      multiplier:  s.multiplier,
      joint_prob:  s.joint_prob ?? 0,
      ev_pct:      s.ev_pct,
    }
    await placePaperBet(payload)
    onBetPlaced?.()
  }

  const powerSuggestions = ([2, 3, 4, 5] as const)
    .map(n => computePowerParlay(props, n))
    .filter((s): s is ParlaySuggestion => s !== null)

  const flexSuggestions = ([3, 4, 5, 6] as const)
    .map(n => computeFlexParlay(props, n))
    .filter((s): s is ParlaySuggestion => s !== null)

  const suggestions = playType === 'power' ? powerSuggestions : flexSuggestions
  const isEmpty = suggestions.length === 0

  return (
    <div className="space-y-4">
      {/* Header + tabs */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-white font-semibold text-lg">Optimal Parlays</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Best picks for each tier, sized by half-Kelly criterion
          </p>
        </div>
        <div className="flex items-center bg-gray-900 border border-gray-800 rounded-lg p-1 gap-1">
          <button
            onClick={() => setPlayType('power')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              playType === 'power'
                ? 'bg-indigo-600 text-white'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            Power Play
          </button>
          <button
            onClick={() => setPlayType('flex')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              playType === 'flex'
                ? 'bg-indigo-600 text-white'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            Flex Play
          </button>
        </div>
      </div>

      {/* Note for flex */}
      {playType === 'flex' && (
        <p className="text-xs text-amber-400/70 bg-amber-500/5 border border-amber-500/20 rounded-lg px-3 py-2">
          Flex Play payouts are configurable in <code className="text-xs">backend/config.py</code> — verify current rates on PrizePicks before betting.
        </p>
      )}

      {isEmpty ? (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 text-center text-gray-600">
          <p className="text-sm">Not enough +EV props to build a parlay. Hit Refresh to fetch latest data.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {suggestions.map(s =>
            s.play_type === 'power'
              ? <PowerCard key={s.n_picks} s={s} onBet={() => setActiveBet(s)} />
              : <FlexCard  key={s.n_picks} s={s} onBet={() => setActiveBet(s)} />
          )}
        </div>
      )}

      <p className="text-xs text-gray-700">
        Half-Kelly sizing maximizes long-run bankroll growth while protecting against model error.
        {playType === 'flex' && ' Flex EV uses full binomial expansion across all outcome combinations.'}
      </p>

      {activeBet && (
        <BetModal
          suggestion={activeBet}
          bankroll={currentBankroll}
          onConfirm={stake => handlePlaceBet(activeBet, stake)}
          onClose={() => setActiveBet(null)}
        />
      )}
    </div>
  )
}
