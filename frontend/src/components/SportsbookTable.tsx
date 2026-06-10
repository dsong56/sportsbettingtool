import { useState } from 'react'
import type { SportsbookLine } from '../types'

interface Props {
  lines: SportsbookLine[]
}

type SortKey = 'ev_pct' | 'kelly_pct' | 'market_prob' | 'player_name' | 'best_book'

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

function formatOdds(odds: number): string {
  return odds > 0 ? `+${odds}` : `${odds}`
}

function DirectionChip({ direction }: { direction: string }) {
  const isOver = direction === 'Over'
  return (
    <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${
      isOver ? 'bg-blue-500/20 text-blue-400' : 'bg-rose-500/20 text-rose-400'
    }`}>
      {direction}
    </span>
  )
}

function SortHeader({ label, sortKey, current, onSort }: {
  label: string; sortKey: SortKey; current: SortKey; onSort: (k: SortKey) => void
}) {
  return (
    <th
      className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer select-none hover:text-gray-300"
      onClick={() => onSort(sortKey)}
    >
      {label}{current === sortKey && <span className="ml-1 text-gray-400">↓</span>}
    </th>
  )
}

function ExpandedRow({ line }: { line: SportsbookLine }) {
  const impliedProb = line.best_odds > 0
    ? 100 / (line.best_odds + 100)
    : Math.abs(line.best_odds) / (Math.abs(line.best_odds) + 100)

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 grid grid-cols-2 md:grid-cols-4 gap-4">
      <div>
        <p className="text-xs text-gray-500 mb-1">True market prob</p>
        <p className="text-lg font-bold font-mono text-white">{(line.market_prob * 100).toFixed(1)}%</p>
        <p className="text-xs text-gray-600">devigged consensus</p>
      </div>
      <div>
        <p className="text-xs text-gray-500 mb-1">{line.best_book} implied prob</p>
        <p className="text-lg font-bold font-mono text-white">{(impliedProb * 100).toFixed(1)}%</p>
        <p className="text-xs text-gray-600">includes vig</p>
      </div>
      <div>
        <p className="text-xs text-gray-500 mb-1">Edge</p>
        <p className={`text-lg font-bold font-mono ${evTextColor(line.ev_pct)}`}>
          +{((line.market_prob - impliedProb) * 100).toFixed(1)}pp
        </p>
        <p className="text-xs text-gray-600">market minus book implied</p>
      </div>
      <div>
        <p className="text-xs text-gray-500 mb-1">Books posting this prop</p>
        <p className="text-lg font-bold font-mono text-white">{line.n_books}</p>
        <p className="text-xs text-gray-600">used for consensus</p>
      </div>
      <div>
        <p className="text-xs text-gray-500 mb-1">½-Kelly bet size</p>
        <p className="text-lg font-bold font-mono text-indigo-300">{line.kelly_pct.toFixed(1)}%</p>
        <p className="text-xs text-gray-600">of bankroll</p>
      </div>
      <div>
        <p className="text-xs text-gray-500 mb-1">On $100 bankroll</p>
        <p className="text-lg font-bold font-mono text-white">${(line.kelly_pct).toFixed(2)}</p>
        <p className="text-xs text-gray-600">straight bet at {line.best_book}</p>
      </div>
      <div>
        <p className="text-xs text-gray-500 mb-1">Best odds</p>
        <p className="text-lg font-bold font-mono text-white">{formatOdds(line.best_odds)}</p>
        <p className="text-xs text-gray-600">at {line.best_book}</p>
      </div>
      <div>
        <p className="text-xs text-gray-500 mb-1">Max return on $100</p>
        <p className="text-lg font-bold font-mono text-white">
          ${line.best_odds > 0
            ? (line.best_odds).toFixed(2)
            : (100 / Math.abs(line.best_odds) * 100).toFixed(2)
          }
        </p>
        <p className="text-xs text-gray-600">profit if correct</p>
      </div>
    </div>
  )
}

export default function SportsbookTable({ lines }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('ev_pct')
  const [expanded, setExpanded] = useState<string | null>(null)

  const sorted = [...lines].sort((a, b) => {
    if (sortKey === 'player_name') return a.player_name.localeCompare(b.player_name)
    if (sortKey === 'best_book')   return a.best_book.localeCompare(b.best_book)
    return (b[sortKey] as number) - (a[sortKey] as number)
  })

  const rowKey = (l: SportsbookLine) =>
    `${l.player_name}|${l.stat_type}|${l.line_score}|${l.direction}|${l.sport}`

  return (
    <div className="w-full overflow-x-auto rounded-xl border border-gray-800">
      <table className="w-full text-sm text-left">
        <thead className="bg-gray-900 border-b border-gray-800">
          <tr>
            <SortHeader label="Player"      sortKey="player_name" current={sortKey} onSort={setSortKey} />
            <th className="px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Prop</th>
            <th className="px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Dir</th>
            <SortHeader label="EV%"         sortKey="ev_pct"      current={sortKey} onSort={setSortKey} />
            <SortHeader label="Best Book"   sortKey="best_book"   current={sortKey} onSort={setSortKey} />
            <th className="px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Odds</th>
            <SortHeader label="Market prob" sortKey="market_prob" current={sortKey} onSort={setSortKey} />
            <SortHeader label="½-Kelly"     sortKey="kelly_pct"   current={sortKey} onSort={setSortKey} />
            <th className="px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Sport</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/50">
          {sorted.map(line => {
            const key    = rowKey(line)
            const isOpen = expanded === key
            return (
              <>
                <tr
                  key={key}
                  className={`transition-colors cursor-pointer ${evColor(line.ev_pct)}`}
                  onClick={() => setExpanded(isOpen ? null : key)}
                >
                  <td className="px-3 py-3 font-medium text-gray-200 whitespace-nowrap">
                    {line.player_name}
                  </td>
                  <td className="px-3 py-3 text-gray-400 whitespace-nowrap">
                    {line.line_score} {line.stat_type}
                  </td>
                  <td className="px-3 py-3">
                    <DirectionChip direction={line.direction} />
                  </td>
                  <td className="px-3 py-3 font-mono font-semibold whitespace-nowrap">
                    <span className={evTextColor(line.ev_pct)}>
                      +{line.ev_pct.toFixed(1)}%
                    </span>
                  </td>
                  <td className="px-3 py-3">
                    <span className="bg-gray-800 text-gray-200 text-xs font-medium px-2 py-1 rounded">
                      {line.best_book}
                    </span>
                  </td>
                  <td className="px-3 py-3 font-mono text-white font-semibold">
                    {formatOdds(line.best_odds)}
                  </td>
                  <td className="px-3 py-3 font-mono text-gray-400">
                    {(line.market_prob * 100).toFixed(1)}%
                  </td>
                  <td className="px-3 py-3 font-mono text-indigo-300">
                    {line.kelly_pct.toFixed(1)}%
                  </td>
                  <td className="px-3 py-3 text-gray-500 text-xs">{line.sport}</td>
                </tr>
                {isOpen && (
                  <tr key={`${key}-exp`}>
                    <td colSpan={9} className="px-4 py-3 bg-gray-900/50">
                      <ExpandedRow line={line} />
                    </td>
                  </tr>
                )}
              </>
            )
          })}
          {sorted.length === 0 && (
            <tr>
              <td colSpan={9} className="px-4 py-10 text-center text-gray-600">
                No lines found. Hit Refresh to scan sportsbooks.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
