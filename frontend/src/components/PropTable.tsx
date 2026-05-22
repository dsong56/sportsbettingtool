import { useState } from 'react'
import type { PropResult } from '../types'
import SignalBadge from './SignalBadge'
import PropCard from './PropCard'

interface Props {
  props: PropResult[]
}

type SortKey = 'ev_pct' | 'blended_prob' | 'market_prob' | 'historical_prob' | 'player_name'

function evColor(ev: number): string {
  if (ev >= 3)  return 'bg-emerald-500/10 hover:bg-emerald-500/20'
  if (ev >= 1)  return 'bg-yellow-500/10 hover:bg-yellow-500/20'
  return 'hover:bg-gray-800/60'
}

function evTextColor(ev: number): string {
  if (ev >= 3) return 'text-emerald-400'
  if (ev >= 1) return 'text-yellow-400'
  return 'text-gray-400'
}

function DirectionChip({ direction }: { direction: string }) {
  const isOver = direction === 'Over'
  return (
    <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${
      isOver
        ? 'bg-blue-500/20 text-blue-400'
        : 'bg-rose-500/20 text-rose-400'
    }`}>
      {direction}
    </span>
  )
}

function SortHeader({
  label, sortKey, current, onSort,
}: {
  label: string
  sortKey: SortKey
  current: SortKey
  onSort: (k: SortKey) => void
}) {
  const active = current === sortKey
  return (
    <th
      className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer select-none hover:text-gray-300"
      onClick={() => onSort(sortKey)}
    >
      {label}
      {active && <span className="ml-1 text-gray-400">↓</span>}
    </th>
  )
}

export default function PropTable({ props }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('ev_pct')
  const [expanded, setExpanded] = useState<string | null>(null)

  const sorted = [...props].sort((a, b) => {
    if (sortKey === 'player_name') return a.player_name.localeCompare(b.player_name)
    return (b[sortKey] as number) - (a[sortKey] as number)
  })

  const rowKey = (p: PropResult) =>
    `${p.player_name}|${p.stat_type}|${p.line_score}|${p.direction}|${p.sport}`

  return (
    <div className="w-full overflow-x-auto rounded-xl border border-gray-800">
      <table className="w-full text-sm text-left">
        <thead className="bg-gray-900 border-b border-gray-800">
          <tr>
            <SortHeader label="Player"      sortKey="player_name"      current={sortKey} onSort={setSortKey} />
            <th className="px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Prop</th>
            <th className="px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Dir</th>
            <SortHeader label="EV%"         sortKey="ev_pct"           current={sortKey} onSort={setSortKey} />
            <SortHeader label="True prob"   sortKey="blended_prob"     current={sortKey} onSort={setSortKey} />
            <SortHeader label="Market"      sortKey="market_prob"      current={sortKey} onSort={setSortKey} />
            <SortHeader label="Historical"  sortKey="historical_prob"  current={sortKey} onSort={setSortKey} />
            <th className="px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Signal</th>
            <th className="px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Kelly 2-pick</th>
            <th className="px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Sport</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/50">
          {sorted.map((prop) => {
            const key = rowKey(prop)
            const isOpen = expanded === key
            return (
              <>
                <tr
                  key={key}
                  className={`transition-colors cursor-pointer ${evColor(prop.ev_pct)}`}
                  onClick={() => setExpanded(isOpen ? null : key)}
                >
                  <td className="px-3 py-3 font-medium text-gray-200 whitespace-nowrap">
                    {prop.player_name}
                    {prop.minutes_flag ? <span className="ml-1.5 text-amber-400 text-xs">⚠</span> : null}
                  </td>
                  <td className="px-3 py-3 text-gray-400 whitespace-nowrap">
                    {prop.line_score} {prop.stat_type}
                  </td>
                  <td className="px-3 py-3">
                    <DirectionChip direction={prop.direction} />
                  </td>
                  <td className="px-3 py-3 font-mono font-semibold whitespace-nowrap">
                    <span className={evTextColor(prop.ev_pct)}>
                      {prop.ev_pct > 0 ? '+' : ''}{prop.ev_pct.toFixed(1)}%
                    </span>
                    <span className="text-gray-600 text-xs ml-1">±{prop.ev_std.toFixed(1)}</span>
                  </td>
                  <td className="px-3 py-3 font-mono text-gray-300">
                    {(prop.blended_prob * 100).toFixed(1)}%
                  </td>
                  <td className="px-3 py-3 font-mono text-gray-400">
                    {(prop.market_prob * 100).toFixed(1)}%
                  </td>
                  <td className="px-3 py-3 font-mono text-gray-400">
                    {prop.sample_n > 0 ? `${(prop.historical_prob * 100).toFixed(1)}%` : '—'}
                  </td>
                  <td className="px-3 py-3">
                    <SignalBadge prop={prop} />
                  </td>
                  <td className="px-3 py-3 font-mono text-indigo-400">
                    {prop.kelly_2pick.toFixed(1)}%
                  </td>
                  <td className="px-3 py-3 text-gray-500 text-xs">{prop.sport}</td>
                </tr>

                {isOpen && (
                  <tr key={`${key}-card`}>
                    <td colSpan={10} className="px-4 py-3 bg-gray-900/50">
                      <PropCard prop={prop} />
                    </td>
                  </tr>
                )}
              </>
            )
          })}

          {sorted.length === 0 && (
            <tr>
              <td colSpan={10} className="px-4 py-10 text-center text-gray-600">
                No props found. Hit Refresh to fetch latest data.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
