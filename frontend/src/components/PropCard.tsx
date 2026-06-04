import type { PropResult } from '../types'
import Sparkline from './Sparkline'
import KellyDisplay from './KellyDisplay'
import SignalBadge from './SignalBadge'
import OddsTypeBadge from './OddsTypeBadge'

interface Props {
  prop: PropResult
}

function ProbBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-gray-500">{label}</span>
        <span className="font-mono" style={{ color }}>{(value * 100).toFixed(1)}%</span>
      </div>
      <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${value * 100}%`, backgroundColor: color }} />
      </div>
    </div>
  )
}

export default function PropCard({ prop }: Props) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-4">

      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold text-white">{prop.player_name}</p>
          <p className="text-sm text-gray-400">
            {prop.direction} {prop.line_score} {prop.stat_type}
          </p>
          {prop.matchup && (
            <p className="text-xs text-gray-500 mt-0.5">
              {prop.matchup} · {prop.game_date} · {prop.sport}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <OddsTypeBadge oddsType={prop.odds_type} />
          <SignalBadge prop={prop} />
        </div>
      </div>

      {/* EV summary */}
      <div className="flex gap-3">
        <div className="flex-1 bg-gray-800 rounded-lg p-3 text-center">
          <p className="text-xs text-gray-500 mb-0.5">EV%</p>
          <p className="text-2xl font-bold text-white">{prop.ev_pct > 0 ? '+' : ''}{prop.ev_pct.toFixed(1)}%</p>
          <p className="text-xs text-gray-600">±{prop.ev_std.toFixed(1)}%</p>
        </div>
        <div className="flex-1 bg-gray-800 rounded-lg p-3 text-center">
          <p className="text-xs text-gray-500 mb-0.5">True prob</p>
          <p className="text-2xl font-bold text-white">{(prop.blended_prob * 100).toFixed(1)}%</p>
          <p className="text-xs text-gray-600">n={prop.sample_n}</p>
        </div>
      </div>

      {/* Signal breakdown */}
      <div className="space-y-2">
        <p className="text-xs text-gray-500 font-medium">Signal breakdown</p>
        <ProbBar label="Market (Shin-devigged)" value={prop.market_prob}    color="#818cf8" />
        <ProbBar label="Historical hit rate"     value={prop.historical_prob} color="#34d399" />
        <ProbBar label="Steam signal (as prob)"  value={0.5 + prop.movement_signal * 0.1} color="#fb923c" />
      </div>

      {/* Rolling windows */}
      <div className="grid grid-cols-3 gap-2">
        {[
          { label: 'L5',  value: prop.roll_l5  },
          { label: 'L10', value: prop.roll_l10 },
          { label: 'L20', value: prop.roll_l20 },
        ].map(({ label, value }) => (
          <div key={label} className="bg-gray-800 rounded-lg p-2 text-center">
            <p className="text-xs text-gray-500">{label} hit rate</p>
            <p className="text-sm font-mono text-gray-200">{value.toFixed(0)}%</p>
          </div>
        ))}
      </div>

      {/* Minutes warning */}
      {prop.minutes_flag && (
        <div className="flex items-center gap-2 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">
          <span className="text-amber-400 text-sm">⚠</span>
          <p className="text-xs text-amber-400">Recent minutes trending down — historical rate may be stale</p>
        </div>
      )}

      {/* Odds sparkline */}
      <div>
        <p className="text-xs text-gray-500 font-medium mb-2">Odds movement</p>
        <Sparkline prop={prop} />
      </div>

      {/* Kelly sizing */}
      <KellyDisplay prop={prop} />
    </div>
  )
}
