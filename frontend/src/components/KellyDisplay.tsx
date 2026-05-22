import type { PropResult } from '../types'

interface Props {
  prop: PropResult
}

function KellyBar({ value, label }: { value: number; label: string }) {
  const pct = Math.min(value, 25) // cap at 25% for display
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-gray-500 w-8 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full bg-indigo-500"
          style={{ width: `${(pct / 25) * 100}%` }}
        />
      </div>
      <span className="text-xs font-mono text-indigo-300 w-10 text-right">
        {value.toFixed(1)}%
      </span>
    </div>
  )
}

export default function KellyDisplay({ prop }: Props) {
  const { kelly_2pick, kelly_3pick, kelly_4pick, breakeven_2pick, breakeven_3pick, breakeven_4pick } = prop

  return (
    <div className="space-y-1.5">
      <p className="text-xs text-gray-500 font-medium mb-2">Kelly sizing (% of bankroll)</p>
      <KellyBar value={kelly_2pick} label="2-pick" />
      <KellyBar value={kelly_3pick} label="3-pick" />
      <KellyBar value={kelly_4pick} label="4-pick" />
      <div className="mt-3 grid grid-cols-3 gap-1 text-center">
        {[
          { label: '2-pick B/E', value: breakeven_2pick },
          { label: '3-pick B/E', value: breakeven_3pick },
          { label: '4-pick B/E', value: breakeven_4pick },
        ].map(({ label, value }) => (
          <div key={label} className="bg-gray-800 rounded p-1.5">
            <p className="text-gray-500 text-xs">{label}</p>
            <p className="text-gray-300 text-xs font-mono">{value.toFixed(1)}%</p>
          </div>
        ))}
      </div>
    </div>
  )
}
