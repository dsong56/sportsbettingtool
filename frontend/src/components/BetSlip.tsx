import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { createBet } from '../api'
import type { BetInput, BetLog, PropResult, Sport } from '../types'

const SPORTS: Sport[] = ['NBA', 'NHL', 'MLB', 'NFL']
const PICK_COUNTS = [2, 3, 4] as const

interface Props {
  /** When set, the form is pre-populated from a prop row on the dashboard. */
  prefill?: PropResult | null
  onClose: () => void
  onLogged?: (bet: BetLog) => void
}

function kellyForPickCount(prop: PropResult, pickCount: number): number {
  if (pickCount === 3) return prop.kelly_3pick
  if (pickCount === 4) return prop.kelly_4pick
  return prop.kelly_2pick
}

export default function BetSlip({ prefill, onClose, onLogged }: Props) {
  const qc = useQueryClient()

  const [playerName, setPlayerName] = useState(prefill?.player_name ?? '')
  const [statType, setStatType]     = useState(prefill?.stat_type ?? '')
  const [lineScore, setLineScore]   = useState(prefill?.line_score.toString() ?? '')
  const [sport, setSport]           = useState<Sport>((prefill?.sport as Sport) ?? 'NBA')
  const [direction, setDirection]   = useState<'Over' | 'Under'>(prefill?.direction ?? 'Over')
  const [pickCount, setPickCount]   = useState(2)
  const [stakePct, setStakePct]     = useState(
    prefill ? Math.max(0.1, prefill.kelly_2pick).toFixed(1) : '1.0'
  )
  const [error, setError]           = useState<string | null>(null)

  // On a prefilled slip, changing the pick count re-defaults the stake to that
  // tier's Kelly fraction
  const selectPickCount = (n: number) => {
    setPickCount(n)
    if (prefill) {
      setStakePct(Math.max(0.1, kellyForPickCount(prefill, n)).toFixed(1))
    }
  }

  const mutation = useMutation({
    mutationFn: (bet: BetInput) => createBet(bet),
    onSuccess: (bet) => {
      qc.invalidateQueries({ queryKey: ['bets'] })
      onLogged?.(bet)
      onClose()
    },
    onError: (err: unknown) => {
      if (isAxiosError(err) && typeof err.response?.data?.detail === 'string') {
        setError(err.response.data.detail)
      } else {
        setError('Failed to log bet — is the backend running?')
      }
    },
  })

  const handleSubmit = () => {
    setError(null)
    const line = parseFloat(lineScore)
    const stake = parseFloat(stakePct)
    if (!playerName.trim() || !statType.trim() || Number.isNaN(line)) {
      setError('Player, stat, and line are required')
      return
    }
    if (Number.isNaN(stake) || stake <= 0 || stake > 100) {
      setError('Stake % must be between 0 and 100')
      return
    }
    mutation.mutate({
      player_name: playerName.trim(),
      stat_type:   statType.trim(),
      line_score:  line,
      sport,
      direction,
      pick_count:  pickCount,
      stake_pct:   stake,
    })
  }

  const inputCls =
    'w-full bg-gray-950 border border-gray-700 text-gray-200 text-sm rounded-lg px-3 py-2 ' +
    'focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-60'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-4"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-bold text-white">Log Bet</h2>
            {prefill && (
              <p className="text-xs text-gray-500 mt-0.5">
                {prefill.ev_pct > 0 ? '+' : ''}{prefill.ev_pct.toFixed(1)}% EV ·{' '}
                {(prefill.blended_prob * 100).toFixed(1)}% true prob at entry
              </p>
            )}
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-xl leading-none">✕</button>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <label className="block text-xs text-gray-500 mb-1">Player</label>
            <input className={inputCls} value={playerName} disabled={!!prefill}
                   onChange={e => setPlayerName(e.target.value)} placeholder="Player name" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Stat</label>
            <input className={inputCls} value={statType} disabled={!!prefill}
                   onChange={e => setStatType(e.target.value)} placeholder="Points" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Line</label>
            <input className={inputCls} value={lineScore} disabled={!!prefill}
                   onChange={e => setLineScore(e.target.value)} placeholder="25.5"
                   inputMode="decimal" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Sport</label>
            <select className={inputCls} value={sport} disabled={!!prefill}
                    onChange={e => setSport(e.target.value as Sport)}>
              {SPORTS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Direction</label>
            <div className="flex gap-1">
              {(['Over', 'Under'] as const).map(d => (
                <button
                  key={d}
                  disabled={!!prefill}
                  onClick={() => setDirection(d)}
                  className={`flex-1 py-2 rounded-lg text-sm font-semibold transition-colors disabled:opacity-60 ${
                    direction === d
                      ? d === 'Over' ? 'bg-blue-500/30 text-blue-300' : 'bg-rose-500/30 text-rose-300'
                      : 'bg-gray-800 text-gray-400'
                  }`}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Pick count</label>
            <div className="flex gap-1">
              {PICK_COUNTS.map(n => (
                <button
                  key={n}
                  onClick={() => selectPickCount(n)}
                  className={`flex-1 py-2 rounded-lg text-sm font-semibold transition-colors ${
                    pickCount === n ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-400'
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Stake (% of bankroll)</label>
            <input className={inputCls} value={stakePct} inputMode="decimal"
                   onChange={e => setStakePct(e.target.value)} />
          </div>
        </div>

        {error && (
          <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/30 px-3 py-2 rounded-lg">
            {error}
          </p>
        )}

        <div className="flex gap-2 pt-1">
          <button
            onClick={onClose}
            className="flex-1 py-2 rounded-lg text-sm font-semibold bg-gray-800 text-gray-300 hover:bg-gray-700 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={mutation.isPending}
            className="flex-1 py-2 rounded-lg text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition-colors disabled:opacity-60"
          >
            {mutation.isPending ? 'Logging…' : 'Log Bet'}
          </button>
        </div>
      </div>
    </div>
  )
}
