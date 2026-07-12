import type { SportsbookLineRow } from '../types'

interface Props {
  lines: SportsbookLineRow[]
}

function evColor(ev: number): string {
  if (ev >= 3) return 'bg-emerald-500/10 hover:bg-emerald-500/20'
  if (ev >= 1) return 'bg-yellow-500/10 hover:bg-yellow-500/20'
  return 'hover:bg-gray-800/60'
}

function evTextColor(ev: number): string {
  if (ev >= 3) return 'text-emerald-400'
  if (ev >= 1) return 'text-yellow-400'
  return 'text-gray-400'
}

function fmtAmerican(odds: number): string {
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

export default function SportsbookTable({ lines }: Props) {
  return (
    <div className="w-full overflow-x-auto rounded-xl border border-gray-800">
      <table className="w-full text-sm text-left">
        <thead className="bg-gray-900 border-b border-gray-800">
          <tr>
            {['Player', 'Prop', 'Dir', 'Book', 'Odds', 'Fair odds', 'Edge (EV%)', 'Consensus', 'Historical', 'Kelly', 'Books'].map(h => (
              <th key={h} className="px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/50">
          {lines.map(l => {
            const key = `${l.player_name}|${l.stat_type}|${l.line_score}|${l.direction}|${l.book}`
            return (
              <tr key={key} className={`transition-colors ${evColor(l.ev_pct)}`}>
                <td className="px-3 py-3 whitespace-nowrap">
                  <p className="font-medium text-gray-200">{l.player_name}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{l.sport}</p>
                </td>
                <td className="px-3 py-3 text-gray-400 whitespace-nowrap">
                  {l.line_score} {l.stat_type}
                </td>
                <td className="px-3 py-3">
                  <DirectionChip direction={l.direction} />
                </td>
                <td className="px-3 py-3 text-gray-300 whitespace-nowrap">{l.book}</td>
                <td className="px-3 py-3 font-mono text-gray-200">{fmtAmerican(l.odds)}</td>
                <td className="px-3 py-3 font-mono text-gray-500">{fmtAmerican(l.fair_odds)}</td>
                <td className="px-3 py-3 font-mono font-semibold">
                  <span className={evTextColor(l.ev_pct)}>
                    {l.ev_pct > 0 ? '+' : ''}{l.ev_pct.toFixed(1)}%
                  </span>
                </td>
                <td className="px-3 py-3 font-mono text-gray-400">
                  {(l.consensus_prob * 100).toFixed(1)}%
                </td>
                <td className="px-3 py-3 font-mono text-gray-400">
                  {(l.historical_prob * 100).toFixed(1)}%
                </td>
                <td className="px-3 py-3 font-mono text-indigo-400">
                  {l.kelly_pct.toFixed(1)}%
                </td>
                <td className="px-3 py-3 text-gray-500 text-xs">{l.n_books_consensus}</td>
              </tr>
            )
          })}

          {lines.length === 0 && (
            <tr>
              <td colSpan={11} className="px-4 py-10 text-center text-gray-600">
                No sportsbook lines found. Hit Refresh to fetch latest odds.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
